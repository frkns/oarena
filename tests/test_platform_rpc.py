"""The bounded AF_UNIX boundary for the official FCode dashboard tab."""

from __future__ import annotations

import os
import socket
import stat
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from oarena.fcode_platform import PlatformError
from oarena.platform_rpc import (
    SOCKET_ENV,
    UnixPlatformClient,
    _MAX_HEADER_BYTES,
    _MAGIC,
    _PREAMBLE,
    _ProtocolError,
    _json_bytes,
    _recv_frame,
)
from oarena.platform_sidecar import PlatformSidecarServer
from oarena.server import App


MATCH_ID = "123e4567-e89b-42d3-a456-426614174000"
TEAM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OPPONENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class PlatformStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def session(self) -> dict[str, Any]:
        self.calls.append(("session", None))
        return {"authenticated": True, "team": {"id": TEAM_ID, "name": "Alpha"}}

    def scrim_profile(self) -> dict[str, Any]:
        self.calls.append(("scrim_profile", None))
        return {
            "team": {"id": TEAM_ID, "name": "Alpha"},
            "active_submission": {"id": "submission", "version": 7},
        }

    def team_search(self, *, query: str, limit: int) -> dict[str, Any]:
        self.calls.append(("team_search", {"query": query, "limit": limit}))
        return {"teams": [{"id": OPPONENT_ID, "name": "Beta"}]}

    def platform_maps(self) -> dict[str, Any]:
        self.calls.append(("platform_maps", None))
        return {"maps": ["atoll", "crossfire"]}

    def request_unrated(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("request_unrated", kwargs))
        return {"match_id": MATCH_ID}

    def ladder(self, *, limit: int) -> dict[str, Any]:
        self.calls.append(("ladder", limit))
        return {"rankings": [{"rank": 1, "team_name": "Alpha"}], "total": 1}

    def test_runs(self, *, limit: int) -> dict[str, Any]:
        self.calls.append(("test_runs", limit))
        return {"test_runs": [{"id": "test-run-1"}], "total": 1}

    def matches(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("matches", kwargs))
        return {"matches": [{"id": MATCH_ID}], "next_cursor": None}

    def match(self, match_id: str) -> dict[str, Any]:
        self.calls.append(("match", match_id))
        return {"match": {"id": match_id}, "games": [{"number": 1}]}

    def replay(self, match_id: str, game: int) -> bytes:
        self.calls.append(("replay", (match_id, game)))
        return b"\x00REPLAY\xff\x00"


@contextmanager
def running_sidecar(
    path: Path,
    platform: Any,
    **kwargs: Any,
) -> Iterator[PlatformSidecarServer]:
    server = PlatformSidecarServer(path, platform, **kwargs)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_all_allowlisted_operations_round_trip_and_replay_stays_binary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "platform.sock"
    platform = PlatformStub()
    with running_sidecar(path, platform):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        client = UnixPlatformClient(path)
        assert client.session()["team"]["name"] == "Alpha"
        assert client.scrim_profile()["active_submission"]["version"] == 7
        assert client.team_search(" beta ", limit=10)["teams"][0]["name"] == "Beta"
        assert client.platform_maps()["maps"] == ["atoll", "crossfire"]
        assert client.request_unrated(
            OPPONENT_ID,
            source_match_id=MATCH_ID,
            map_names=["atoll"],
        ) == {"match_id": MATCH_ID}
        assert client.ladder(limit=50)["total"] == 1
        assert client.test_runs(limit=25)["test_runs"] == [{"id": "test-run-1"}]
        assert client.matches(
            limit=20,
            match_type="ladder",
            mine=False,
            team_id=TEAM_ID,
            cursor="next-page",
        )["matches"][0]["id"] == MATCH_ID
        assert client.match(MATCH_ID)["games"] == [{"number": 1}]
        assert client.replay(MATCH_ID, 4) == b"\x00REPLAY\xff\x00"

    assert not path.exists()
    assert platform.calls == [
        ("session", None),
        ("scrim_profile", None),
        ("team_search", {"query": "beta", "limit": 10}),
        ("platform_maps", None),
        (
            "request_unrated",
            {
                "opponent_team_id": OPPONENT_ID,
                "source_match_id": MATCH_ID,
                "map_names": ["atoll"],
            },
        ),
        ("ladder", 50),
        ("test_runs", 25),
        (
            "matches",
            {
                "limit": 20,
                "match_type": "ladder",
                "mine": False,
                "team_id": TEAM_ID,
                "cursor": "next-page",
            },
        ),
        ("match", MATCH_ID),
        ("replay", (MATCH_ID, 4)),
    ]


def test_platform_errors_cross_with_only_their_safe_status_and_message(
    tmp_path: Path,
) -> None:
    class Limited(PlatformStub):
        def ladder(self, *, limit: int) -> dict[str, Any]:
            del limit
            raise PlatformError(429, "FCode platform rate limit reached")

    with running_sidecar(tmp_path / "platform.sock", Limited()) as server:
        client = UnixPlatformClient(server.server_address)
        with pytest.raises(PlatformError) as raised:
            client.ladder(limit=10)
    assert raised.value.code == 429
    assert raised.value.message == "FCode platform rate limit reached"


def test_scrim_retry_and_unknown_outcome_metadata_crosses_sidecar(
    tmp_path: Path,
) -> None:
    class Uncertain(PlatformStub):
        def request_unrated(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise PlatformError(
                429,
                "Rate limit exceeded",
                retry_after_s=83,
                outcome_unknown=True,
            )

    with running_sidecar(tmp_path / "platform.sock", Uncertain()) as server:
        client = UnixPlatformClient(server.server_address)
        with pytest.raises(PlatformError) as raised:
            client.request_unrated(OPPONENT_ID)

    assert raised.value.code == 429
    assert raised.value.message == "Rate limit exceeded"
    assert raised.value.retry_after_s == 83
    assert raised.value.outcome_unknown is True


def test_unexpected_backend_errors_are_not_disclosed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class Broken(PlatformStub):
        def session(self) -> dict[str, Any]:
            raise RuntimeError("secret backend detail")

    with running_sidecar(tmp_path / "platform.sock", Broken()) as server:
        with pytest.raises(PlatformError) as raised:
            UnixPlatformClient(server.server_address).session()
    assert raised.value.code == 502
    assert raised.value.message == "FCode platform request failed"
    assert "secret" not in raised.value.message
    assert "secret backend detail" not in caplog.text


def test_malformed_backend_results_are_reported_as_upstream_failures(
    tmp_path: Path,
) -> None:
    class Broken(PlatformStub):
        def session(self) -> dict[str, Any]:
            return {"bad": object()}

    with running_sidecar(tmp_path / "platform.sock", Broken()) as server:
        with pytest.raises(PlatformError) as raised:
            UnixPlatformClient(server.server_address).session()
    assert raised.value.code == 502
    assert raised.value.message == "FCode platform request failed"


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda client: client.ladder(limit=0), "limit"),
        (lambda client: client.test_runs(limit=101), "limit"),
        (lambda client: client.team_search("bad\nquery"), "query"),
        (lambda client: client.team_search("team", limit=21), "limit"),
        (lambda client: client.match(MATCH_ID.upper()), "canonical UUID"),
        (lambda client: client.replay(MATCH_ID, 6), "game"),
        (
            lambda client: client.request_unrated(OPPONENT_ID, map_names=["map"] * 6),
            "at most 5",
        ),
        (
            lambda client: client.request_unrated(
                OPPONENT_ID, map_names=["bad\nmap"]
            ),
            "map name",
        ),
        (
            lambda client: client.request_unrated("not-a-team"),
            "canonical UUID",
        ),
        (
            lambda client: client.matches(
                limit=20, mine=True, team_id=TEAM_ID
            ),
            "cannot be combined",
        ),
        (
            lambda client: client.matches(limit=20, cursor="x\nheader"),
            "cursor",
        ),
    ],
)
def test_client_rejects_invalid_bounded_arguments_before_connecting(
    tmp_path: Path, call: Any, message: str
) -> None:
    client = UnixPlatformClient(tmp_path / "missing.sock")
    with pytest.raises(PlatformError, match=message) as raised:
        call(client)
    assert raised.value.code == 400


def _raw_call(path: str, header: dict[str, Any], body: bytes = b"") -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(path)
        raw_header = _json_bytes(header)
        packet = _PREAMBLE.pack(_MAGIC, len(raw_header), len(body)) + raw_header + body
        try:
            # One small write removes an avoidable race where the server can
            # reject the preamble's nonzero body length before the helper sends
            # the separately framed header/body.
            peer.sendall(packet)
        except BrokenPipeError:
            if not body:
                raise
        try:
            peer.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        response, response_body = _recv_frame(peer, max_body_bytes=1024)
    assert response_body == b""
    return response


@pytest.mark.parametrize(
    "header",
    [
        {"op": "delete_team", "args": {}},
        {"op": "session", "args": {"extra": True}},
        {"op": "scrim_profile", "args": {"extra": True}},
        {"op": "platform_maps", "args": {"extra": True}},
        {"op": "team_search", "args": {"query": "team"}},
        {"op": "team_search", "args": {"query": "team", "limit": 21}},
        {
            "op": "request_unrated",
            "args": {
                "opponent_team_id": OPPONENT_ID,
                "source_match_id": None,
                "map_names": ["map"] * 6,
            },
        },
        {"op": "test_runs", "args": {}},
        {"op": "test_runs", "args": {"limit": True}},
        {"op": "test_runs", "args": {"limit": 101}},
        {"op": "test_runs", "args": {"limit": 10, "extra": True}},
        {"op": "match", "args": {"match_id": MATCH_ID.upper()}},
        {"op": "replay", "args": {"match_id": MATCH_ID, "game": 50}},
        {"op": "session", "args": {}, "extra": "field"},
    ],
)
def test_server_independently_rejects_non_allowlisted_raw_requests(
    tmp_path: Path, header: dict[str, Any]
) -> None:
    platform = PlatformStub()
    with running_sidecar(tmp_path / "platform.sock", platform) as server:
        response = _raw_call(server.server_address, header)
    assert response["ok"] is False
    assert response["code"] == 400
    assert platform.calls == []


def test_server_rejects_request_bodies_and_oversized_headers(tmp_path: Path) -> None:
    platform = PlatformStub()
    with running_sidecar(tmp_path / "platform.sock", platform) as server:
        try:
            body_response = _raw_call(
                server.server_address,
                {"op": "session", "args": {}},
                b"not-allowed",
            )
        except (BrokenPipeError, ConnectionResetError, _ProtocolError):
            # The body length alone is sufficient to reject. A strict server
            # may close before draining the deliberately invalid body, in
            # which case AF_UNIX reports reset instead of preserving its 400.
            body_response = None
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(2)
            peer.connect(server.server_address)
            peer.sendall(_PREAMBLE.pack(_MAGIC, _MAX_HEADER_BYTES + 1, 0))
            peer.shutdown(socket.SHUT_WR)
            header_response, response_body = _recv_frame(peer, max_body_bytes=1024)

    if body_response is not None:
        assert body_response == {
            "ok": False,
            "code": 400,
            "message": "invalid platform RPC request",
        }
    assert header_response["code"] == 400
    assert response_body == b""
    assert platform.calls == []


def test_handler_concurrency_is_bounded_and_excess_calls_get_503(
    tmp_path: Path,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    class Blocking(PlatformStub):
        def session(self) -> dict[str, Any]:
            entered.set()
            assert release.wait(3)
            return super().session()

    result: list[dict[str, Any]] = []
    with running_sidecar(
        tmp_path / "platform.sock", Blocking(), max_workers=1
    ) as server:
        client = UnixPlatformClient(server.server_address, timeout_s=3)
        thread = threading.Thread(target=lambda: result.append(client.session()))
        thread.start()
        assert entered.wait(2)
        with pytest.raises(PlatformError) as raised:
            client.session()
        release.set()
        thread.join(timeout=3)

    assert raised.value.code == 503
    assert result[0]["authenticated"] is True


def test_existing_non_socket_path_is_never_replaced(tmp_path: Path) -> None:
    path = tmp_path / "platform.sock"
    path.write_text("keep me", encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-socket"):
        PlatformSidecarServer(path, PlatformStub())
    assert path.read_text(encoding="utf-8") == "keep me"


def test_app_uses_unix_client_only_when_socket_environment_is_present(
    project: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "platform.sock"
    monkeypatch.setenv(SOCKET_ENV, str(path))
    app = App(project.cfg, project.store, project.bus, project.league, project.rater)
    try:
        assert isinstance(app.platform, UnixPlatformClient)
        assert app.platform.socket_path == str(path)
    finally:
        app.close()

    injected = PlatformStub()
    app = App(
        project.cfg,
        project.store,
        project.bus,
        project.league,
        project.rater,
        platform_client=injected,  # type: ignore[arg-type]
    )
    try:
        assert app.platform is injected
    finally:
        app.close()


def test_relative_socket_paths_are_refused() -> None:
    with pytest.raises(ValueError, match="absolute"):
        UnixPlatformClient("relative.sock")


def test_socket_path_has_no_group_or_other_permissions(tmp_path: Path) -> None:
    path = tmp_path / "platform.sock"
    server = PlatformSidecarServer(path, PlatformStub())
    try:
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        assert mode == 0o600
    finally:
        server.server_close()


def test_explicit_primary_socket_group_gets_only_group_connect_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "platform.sock"
    # Primary group membership must be accepted even if getgroups() omits it.
    monkeypatch.setattr(os, "getgroups", lambda: [])
    server = PlatformSidecarServer(
        path,
        PlatformStub(),
        socket_group=os.getegid(),
    )
    try:
        info = os.lstat(path)
        assert info.st_gid == os.getegid()
        assert stat.S_IMODE(info.st_mode) == 0o660
    finally:
        server.server_close()


def test_socket_parent_must_be_owned_real_and_not_shared_writable(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o770)
    with pytest.raises(RuntimeError, match="group/world writable"):
        PlatformSidecarServer(shared / "platform.sock", PlatformStub())

    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError, match="real directory"):
        PlatformSidecarServer(linked / "platform.sock", PlatformStub())
