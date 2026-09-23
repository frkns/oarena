"""The FCode platform boundary: normalization, privacy, caching and errors."""

from __future__ import annotations

import io
import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from oarena import fcode_platform as platformmod
from oarena.fcode_platform import FcodePlatform, PlatformError


MATCH_ID = "123e4567-e89b-42d3-a456-426614174000"
TEAM_A = "11111111-1111-4111-8111-111111111111"
TEAM_B = "22222222-2222-4222-8222-222222222222"
REPLAY_ORIGIN = (
    "https://florentcode-production-replays.s3.eu-north-1.amazonaws.com"
)


class Response(io.BytesIO):
    def __init__(
        self,
        body: bytes,
        *,
        url: str = "https://api.example.test/",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body)
        self._url = url
        self.headers = headers or {"Content-Length": str(len(body))}

    def geturl(self) -> str:
        return self._url


class FailingResponse(Response):
    def __init__(
        self,
        body: bytes,
        failure: BaseException,
        *,
        phase: str,
        url: str = "https://api.example.test/",
    ) -> None:
        super().__init__(body, url=url)
        self.failure = failure
        self.phase = phase

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        if self.phase == "read":
            raise self.failure
        return super().read(*args, **kwargs)

    def __enter__(self) -> FailingResponse:
        if self.phase == "enter":
            raise self.failure
        return self

    def close(self) -> None:
        super().close()
        if self.phase == "close":
            raise self.failure


class QueueOpener:
    def __init__(self, *responses: Response | BaseException) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[Any, float]] = []

    def __call__(self, request: Any, *, timeout: float) -> Response:
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError(f"unexpected request to {request.full_url}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def encoded(value: Any, *, url: str = "https://api.example.test/") -> Response:
    return Response(json.dumps(value).encode(), url=url)


def auth(
    *, token: str | None = "secret-token", base: str = "https://api.example.test"
):
    credentials = {
        "token": token,
        "expires_at": "tomorrow",
        "user": {"id": "member-pii", "email": "private@example.test"},
        "team": {"id": TEAM_A, "name": "Alpha", "private": "do-not-leak"},
    }
    return lambda: (base, token, credentials)


def write_systemd_credential(directory: Path, raw: bytes | None = None) -> Path:
    directory.mkdir(mode=0o700)
    path = directory / platformmod._SYSTEMD_CREDENTIAL_FILE
    if raw is None:
        raw = json.dumps(
            {
                "token": "credential-token",
                "expires_at": "2026-08-03T00:00:00Z",
                "user": {
                    "id": "private-user-id",
                    "name": "Private User",
                    "email": "private@example.test",
                },
                "team": {"id": TEAM_A, "name": "Alpha"},
            }
        ).encode()
    path.write_bytes(raw)
    path.chmod(0o400)
    return path


def test_systemd_credential_is_strict_bounded_and_privacy_reduced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "credentials"
    write_systemd_credential(directory)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(directory))
    monkeypatch.setenv("FCODE_API_URL", "https://credential-api.example.test")

    base_url, token, credentials = platformmod._default_auth_provider()

    assert base_url == "https://credential-api.example.test"
    assert token == "credential-token"
    assert credentials == {"team": {"id": TEAM_A, "name": "Alpha"}}
    assert "user" not in credentials
    assert "expires_at" not in credentials


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json",
        b'{"token":"one","token":"two"}',
        b'{"token":"ok","unexpected":true}',
        b'{"token":"bad token with spaces"}',
        b'{"token":"ok","team":{"id":3,"name":"Alpha"}}',
        b'{"token":"ok","user":[]}',
        b'{"team":null}',
    ],
)
def test_invalid_systemd_credentials_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    directory = tmp_path / "credentials"
    write_systemd_credential(directory, raw)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(directory))

    with pytest.raises(PlatformError) as raised:
        platformmod._default_auth_provider()
    assert raised.value.code == 502
    assert "credential" in raised.value.message
    assert raw.decode("utf-8", "ignore") not in raised.value.message


def test_systemd_credential_size_symlink_reject_and_missing_is_logged_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "credentials"
    path = write_systemd_credential(
        directory,
        b"x" * (platformmod._MAX_SYSTEMD_CREDENTIAL_BYTES + 1),
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(directory))
    monkeypatch.setenv("FCODE_API_URL", "https://logged-out.example.test")
    with pytest.raises(PlatformError):
        platformmod._default_auth_provider()

    path.unlink()
    target = tmp_path / "real-credential"
    target.write_text('{"token":"do-not-follow"}', encoding="utf-8")
    path.symlink_to(target)
    with pytest.raises(PlatformError):
        platformmod._default_auth_provider()

    path.unlink()
    assert platformmod._default_auth_provider() == (
        "https://logged-out.example.test",
        None,
        None,
    )


def test_missing_systemd_fcode_directory_is_logged_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "credentials"
    directory.mkdir(mode=0o700)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(directory))
    monkeypatch.setenv("FCODE_API_URL", "https://logged-out.example.test")

    assert platformmod._default_auth_provider() == (
        "https://logged-out.example.test",
        None,
        None,
    )


def test_empty_setcredential_fallback_is_logged_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "credentials"
    write_systemd_credential(directory, b"{}")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(directory))
    monkeypatch.setenv("FCODE_API_URL", "https://logged-out.example.test")

    assert platformmod._default_auth_provider() == (
        "https://logged-out.example.test",
        None,
        None,
    )


def test_ambient_auth_remains_the_fallback_outside_systemd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fcode.auth

    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(fcode.auth, "get_api_url", lambda: "https://ambient.test")
    monkeypatch.setattr(fcode.auth, "get_token", lambda: "ambient-token")
    monkeypatch.setattr(
        fcode.auth,
        "load_credentials",
        lambda: {"team": {"id": TEAM_B, "name": "Beta"}},
    )

    assert platformmod._default_auth_provider() == (
        "https://ambient.test",
        "ambient-token",
        {"team": {"id": TEAM_B, "name": "Beta"}},
    )


def upstream_match(*, status: str = "complete") -> dict[str, Any]:
    return {
        "id": MATCH_ID,
        "status": status,
        "stage": None,
        "winnerId": TEAM_A,
        "scoreA": 3,
        "scoreB": 1,
        "rated": True,
        "triggeredBy": "ladder",
        "eloDeltaA": 4.25,
        "eloDeltaB": -4.25,
        "createdAt": "2026-08-01T12:00:00Z",
        "completedAt": "2026-08-01T12:01:00Z",
        "teamAId": TEAM_A,
        "teamAName": "Alpha",
        "teamAVersion": 7,
        "teamARating": 1512.5,
        "teamAMatchesPlayed": 42,
        "teamBId": TEAM_B,
        "teamBName": "Beta",
        "teamBVersion": 4,
        "teamBRating": 1491.0,
        "teamBMatchesPlayed": 38,
        "sourceMatchAId": None,
        "sourceMatchBId": MATCH_ID,
        "submissionAS3Key": "private/submission-a.zip",
        "errorMessage": "potentially private bot output",
        "members": [{"email": "private@example.test"}],
    }


def test_session_exposes_only_authentication_and_team_identity() -> None:
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener())

    assert client.session() == {
        "authenticated": True,
        "team": {"id": TEAM_A, "name": "Alpha"},
    }
    serialized = json.dumps(client.session())
    assert "secret-token" not in serialized
    assert "private@example.test" not in serialized
    assert "tomorrow" not in serialized


def test_scrim_profile_normalizes_only_the_active_submission() -> None:
    upstream = {
        "submissions": [
            {
                "id": "inactive-submission",
                "version": 6,
                "status": "ready",
                "isActive": False,
            },
            {
                "id": "active-submission",
                "version": 7,
                "name": "current",
                "status": "ready",
                "uploadedAt": "2026-08-05T12:00:00Z",
                "submittedByName": "private-member",
                "downloadUrl": "https://signed.example/private",
                "isActive": True,
            },
        ]
    }
    opener = QueueOpener(encoded(upstream))
    client = FcodePlatform(auth_provider=auth(), opener=opener)

    result = client.scrim_profile()
    assert result == {
        "team": {"id": TEAM_A, "name": "Alpha"},
        "active_submission": {
            "id": "active-submission",
            "version": 7,
            "name": "current",
            "status": "ready",
            "uploaded_at": "2026-08-05T12:00:00Z",
        },
    }
    request = opener.requests[0][0]
    assert urllib.parse.urlsplit(request.full_url).path == "/api/submissions"
    assert request.get_header("Authorization") == "Bearer secret-token"
    serialized = json.dumps(result)
    assert "private-member" not in serialized
    assert "signed.example" not in serialized
    assert "secret-token" not in serialized


def test_scrim_profile_supports_no_active_submission_and_rejects_bad_response() -> None:
    client = FcodePlatform(
        auth_provider=auth(),
        opener=QueueOpener(encoded({"submissions": []})),
    )
    assert client.scrim_profile()["active_submission"] is None

    malformed = FcodePlatform(
        auth_provider=auth(),
        opener=QueueOpener(encoded({"submissions": {}})),
    )
    with pytest.raises(PlatformError, match="invalid submissions response") as caught:
        malformed.scrim_profile()
    assert caught.value.code == 502


def test_team_search_and_platform_maps_are_normalized_and_bounded() -> None:
    opener = QueueOpener(
        encoded(
            {
                "teams": [
                    {
                        "teamId": TEAM_B,
                        "teamName": "Beta",
                        "rating": 1491.5,
                        "matchesPlayed": 38,
                        "members": [{"email": "private@example.test"}],
                    },
                    {"teamId": TEAM_A, "teamName": "Alpha"},
                ]
            }
        ),
        encoded(
            {
                "maps": [
                    {"name": "atoll", "s3Key": "private/map"},
                    {"name": "crossfire", "sha256": "private-hash"},
                    {"name": 3},
                ]
            }
        ),
    )
    client = FcodePlatform(auth_provider=auth(), opener=opener)

    assert client.team_search(" beta ", limit=1) == {
        "teams": [
            {
                "id": TEAM_B,
                "name": "Beta",
                "rating": 1491.5,
                "matches_played": 38,
            }
        ]
    }
    assert client.platform_maps() == {"maps": ["atoll", "crossfire"]}
    query = urllib.parse.parse_qs(
        urllib.parse.urlsplit(opener.requests[0][0].full_url).query
    )
    assert query == {"q": ["beta"]}
    serialized = json.dumps(
        {"search": client.team_search("beta", limit=1), "maps": client.platform_maps()}
    )
    assert "private" not in serialized


def test_request_unrated_posts_exact_bounded_payload_and_normalizes_id() -> None:
    opener = QueueOpener(encoded({"matchId": MATCH_ID}))
    client = FcodePlatform(auth_provider=auth(), opener=opener)

    assert client.request_unrated(
        TEAM_B,
        source_match_id=MATCH_ID,
        map_names=[" atoll ", "crossfire"],
    ) == {"match_id": MATCH_ID}
    request = opener.requests[0][0]
    assert request.method == "POST"
    assert urllib.parse.urlsplit(request.full_url).path == "/api/matches/unrated"
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {
        "opponentTeamId": TEAM_B,
        "sourceMatchId": MATCH_ID,
        "mapNames": ["atoll", "crossfire"],
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"opponent_team_id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
            "canonical UUID",
        ),
        ({"opponent_team_id": TEAM_B, "source_match_id": "bad"}, "canonical UUID"),
        ({"opponent_team_id": TEAM_B, "map_names": "atoll"}, "must be a list"),
        ({"opponent_team_id": TEAM_B, "map_names": ["map"] * 6}, "at most 5"),
        ({"opponent_team_id": TEAM_B, "map_names": ["bad\nmap"]}, "map name"),
    ],
)
def test_request_unrated_rejects_invalid_inputs_before_network(
    kwargs: dict[str, Any], message: str
) -> None:
    opener = QueueOpener()
    client = FcodePlatform(auth_provider=auth(), opener=opener)
    with pytest.raises(PlatformError, match=message) as caught:
        client.request_unrated(**kwargs)
    assert caught.value.code == 400
    assert opener.requests == []


def test_match_list_is_normalized_filtered_and_short_cached() -> None:
    match_error = "validation failed: " + ("x" * 1200) + " PRIVATE-ERROR-TAIL"
    raw_match = upstream_match()
    raw_match["errorMessage"] = match_error
    raw = {"matches": [raw_match], "nextCursor": "next-page"}
    opener = QueueOpener(encoded(raw))
    client = FcodePlatform(auth_provider=auth(), opener=opener)

    result = client.matches(
        limit=20,
        match_type="ladder",
        team_id=TEAM_B,
        cursor="oldest",
    )
    assert client.matches(
        limit=20,
        match_type="ladder",
        team_id=TEAM_B,
        cursor="oldest",
    ) is result
    assert len(opener.requests) == 1
    request = opener.requests[0][0]
    assert request.get_header("Authorization") == "Bearer secret-token"
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
    assert query == {
        "limit": ["20"],
        "type": ["ladder"],
        "teamIds": [TEAM_B],
        "cursor": ["oldest"],
    }
    assert result["next_cursor"] == "next-page"
    match = result["matches"][0]
    assert match["team_a"] == {
        "id": TEAM_A,
        "name": "Alpha",
        "version": 7,
        "rating": 1512.5,
        "matches_played": 42,
    }
    assert match["rating_delta_b"] == -4.25
    assert match["error"] == match_error[: platformmod._MAX_TEST_RUN_ERROR_CHARS]
    serialized = json.dumps(result)
    assert "S3" not in serialized
    assert "submission-a" not in serialized
    assert "PRIVATE-ERROR-TAIL" not in serialized
    assert "private@example.test" not in serialized


def test_test_runs_use_fixed_path_share_full_cache_and_hide_private_fields() -> None:
    now = [10.0]
    private_requester = "private-requester-account-id"
    private_a_key = "test/private-account/bot-a.zip"
    private_b_key = "test/private-account/bot-b.zip"
    long_error = "engine failure: " + ("x" * 1200) + " PRIVATE-ERROR-TAIL"
    first = {
        "id": MATCH_ID,
        "status": "error",
        "stage": "validating",
        "scoreA": 0,
        "scoreB": 1,
        "winnerId": TEAM_B,
        "testBotAName": "syntax",
        "testBotBName": "starter",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "completedAt": "2026-01-01T00:01:00.000Z",
        "requestedBy": private_requester,
        "requestedByName": "Example User",
        "errorMessage": long_error,
        "testBotAS3Key": private_a_key,
        "testBotBS3Key": private_b_key,
        # Test runs are always represented as unrated uploaded bots even if a
        # future or malformed upstream row contains ordinary match fields.
        "rated": True,
        "triggeredBy": "ladder",
        "teamAId": TEAM_A,
        "teamAName": "Private team name",
        "members": [{"email": "private@example.test"}],
    }
    second = {
        "id": "second-test-run",
        "status": "complete",
        "scoreA": 1,
        "scoreB": 0,
        "testBotAName": "candidate",
        "testBotBName": "starter",
        "requestedByName": "Example User",
    }
    upstream = {"matches": [first, second], "nextCursor": "not-applicable"}
    opener = QueueOpener(encoded(upstream), encoded(upstream))
    client = FcodePlatform(
        auth_provider=auth(),
        opener=opener,
        clock=lambda: now[0],
        json_ttl_s=5,
    )

    one = client.test_runs(limit=1)
    both = client.test_runs(limit=100)

    assert len(opener.requests) == 1
    request = opener.requests[0][0]
    split = urllib.parse.urlsplit(request.full_url)
    assert split.path == "/api/matches/test-runs"
    assert split.query == ""
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert one["total"] == 2
    assert len(one["test_runs"]) == 1
    assert len(both["test_runs"]) == 2

    row = one["test_runs"][0]
    assert row == {
        "id": MATCH_ID,
        "status": "error",
        "stage": "validating",
        "type": "test",
        "rated": False,
        "team_a": {
            "id": None,
            "name": "syntax",
            "version": None,
            "rating": None,
            "matches_played": None,
        },
        "team_b": {
            "id": None,
            "name": "starter",
            "version": None,
            "rating": None,
            "matches_played": None,
        },
        "winner_id": TEAM_B,
        "score_a": 0,
        "score_b": 1,
        "rating_delta_a": None,
        "rating_delta_b": None,
        "source_match_a_id": None,
        "source_match_b_id": None,
        "created_at": "2026-01-01T00:00:00.000Z",
        "completed_at": "2026-01-01T00:01:00.000Z",
        "requested_by_name": "Example User",
        "error": long_error[: platformmod._MAX_TEST_RUN_ERROR_CHARS],
    }
    serialized = json.dumps(both)
    assert private_requester not in serialized
    assert private_a_key not in serialized
    assert private_b_key not in serialized
    assert "private@example.test" not in serialized
    assert "PRIVATE-ERROR-TAIL" not in serialized

    # Expiry uses the normal short JSON TTL, not the immutable match-detail
    # cache. Different requested limits still address the same full response.
    now[0] += 6
    client.test_runs(limit=2)
    assert len(opener.requests) == 2


@pytest.mark.parametrize("raw", [None, [], {}, {"matches": None}, {"matches": {}}])
def test_test_runs_reject_malformed_top_level_responses(raw: Any) -> None:
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(encoded(raw)))

    with pytest.raises(PlatformError, match="invalid test runs response") as caught:
        client.test_runs(limit=20)

    assert caught.value.code == 502


def test_test_runs_skip_non_records_and_reduce_malformed_fields_to_null() -> None:
    malformed = {
        "id": 123,
        "status": ["complete"],
        "stage": False,
        "scoreA": True,
        "scoreB": 1.5,
        "winnerId": {"private": "id"},
        "testBotAName": ["private", "name"],
        "testBotBName": "  starter  ",
        "requestedByName": 123,
        "errorMessage": ["private error"],
        "createdAt": False,
    }
    opener = QueueOpener(encoded({"matches": ["private", malformed, None]}))
    client = FcodePlatform(auth_provider=auth(), opener=opener)

    payload = client.test_runs(limit=0)
    assert payload == {"test_runs": [], "total": 1}

    row = client.test_runs(limit=1)["test_runs"][0]
    assert row["id"] is None
    assert row["status"] is None
    assert row["stage"] is None
    assert row["score_a"] is None
    assert row["score_b"] is None
    assert row["winner_id"] is None
    assert row["team_a"]["name"] is None
    assert row["team_b"]["name"] == "starter"
    assert row["requested_by_name"] is None
    assert row["error"] is None
    assert row["created_at"] is None
    assert len(opener.requests) == 1


def test_mine_uses_only_the_credential_team_id() -> None:
    opener = QueueOpener(encoded({"matches": [], "nextCursor": None}))
    client = FcodePlatform(auth_provider=auth(), opener=opener)
    client.matches(limit=5, mine=True)
    query = urllib.parse.parse_qs(
        urllib.parse.urlsplit(opener.requests[0][0].full_url).query
    )
    assert query["teamIds"] == [TEAM_A]


def test_mine_without_a_team_is_a_safe_400() -> None:
    provider = lambda: ("https://api.example.test", "token", {"user": {}})
    client = FcodePlatform(auth_provider=provider, opener=QueueOpener())
    with pytest.raises(PlatformError, match="not on a team") as caught:
        client.matches(limit=5, mine=True)
    assert caught.value.code == 400


def test_complete_detail_has_long_cache_and_hides_object_keys() -> None:
    now = [100.0]
    game = {
        "id": "game-row-id",
        "matchId": MATCH_ID,
        "gameNumber": 1,
        "mapName": "Spiral",
        "mapSeed": 123,
        "winnerId": TEAM_A,
        "winnerSide": "A",
        "winCondition": "core_destroyed",
        "turnsPlayed": 310,
        "replayS3Key": "private/replays/game.replay26",
        "createdAt": "2026-08-01T12:00:00Z",
        "resignMessage": "untrusted bot output",
    }
    opener = QueueOpener(
        encoded({"match": upstream_match(), "games": [game]})
    )
    client = FcodePlatform(
        auth_provider=auth(),
        opener=opener,
        clock=lambda: now[0],
        json_ttl_s=5,
        complete_detail_ttl_s=300,
    )

    detail = client.match(MATCH_ID)
    now[0] += 200
    assert client.match(MATCH_ID) is detail
    assert len(opener.requests) == 1
    assert detail["match"]["error"] == "potentially private bot output"
    assert detail["games"] == [
        {
            "number": 1,
            "map_name": "Spiral",
            "map_seed": 123,
            "winner_id": TEAM_A,
            "winner_side": "A",
            "win_condition": "core_destroyed",
            "turns": 310,
            "has_replay": True,
            "created_at": "2026-08-01T12:00:00Z",
        }
    ]
    serialized = json.dumps(detail)
    assert "replayS3Key" not in serialized
    assert "private/replays" not in serialized
    assert "untrusted bot output" not in serialized


def test_public_ladder_never_sends_logged_in_bearer_and_has_own_cache_ttl() -> None:
    now = [0.0]
    row = {
        "teamId": TEAM_A,
        "teamName": "Alpha",
        "rating": 1550.0,
        "matchesPlayed": 99,
        "members": [{"email": "private@example.test"}],
        "bio": "private biography",
    }
    opener = QueueOpener(encoded([row]), encoded([row]))
    client = FcodePlatform(
        auth_provider=auth(token="must-not-be-sent"),
        opener=opener,
        clock=lambda: now[0],
        json_ttl_s=1,
        ladder_ttl_s=60,
    )

    result = client.ladder(limit=50)
    now[0] = 30
    assert client.ladder(limit=50) is result
    assert len(opener.requests) == 1
    assert opener.requests[0][0].get_header("Authorization") is None
    assert result == {
        "rankings": [
            {
                "rank": 1,
                "team_id": TEAM_A,
                "team_name": "Alpha",
                "rating": 1550.0,
                "matches_played": 99,
            }
        ],
        "total": 1,
    }
    assert "private" not in json.dumps(result)
    now[0] = 61
    client.ladder(limit=50)
    assert len(opener.requests) == 2


def test_authenticated_json_redirect_is_refused_before_cross_origin_token_leak() -> None:
    target_requests: list[str | None] = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            target_requests.append(self.headers.get("Authorization"))
            body = b'{"matches":[],"nextCursor":null}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    target_thread = threading.Thread(target=target.serve_forever, daemon=True)
    target_thread.start()
    target_url = f"http://127.0.0.1:{target.server_address[1]}/stolen"

    class Source(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header("Location", target_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), Source)
    source_thread = threading.Thread(target=source.serve_forever, daemon=True)
    source_thread.start()
    source_url = f"http://127.0.0.1:{source.server_address[1]}"
    try:
        client = FcodePlatform(auth_provider=auth(base=source_url))
        with pytest.raises(PlatformError, match="redirect refused") as caught:
            client.matches(limit=1)
        assert caught.value.code == 502
        assert target_requests == []
    finally:
        source.shutdown()
        source.server_close()
        target.shutdown()
        target.server_close()
        source_thread.join(timeout=2)
        target_thread.join(timeout=2)


def test_private_replay_redirect_is_validated_before_following() -> None:
    handler = platformmod._ReplayRedirects(FcodePlatform._validate_signed_url)
    original = urllib.request.Request(f"{REPLAY_ORIGIN}/replay")
    response = Response(b"")

    with pytest.raises(PlatformError, match="invalid replay URL") as caught:
        handler.redirect_request(
            original,
            response,
            302,
            "Found",
            Message(),
            "https://127.0.0.1/private",
        )

    assert caught.value.code == 502
    assert response.closed


def test_safe_replay_redirect_strips_any_auth_headers() -> None:
    handler = platformmod._ReplayRedirects(FcodePlatform._validate_signed_url)
    original = urllib.request.Request(
        f"{REPLAY_ORIGIN}/replay",
        headers={
            "Authorization": "Bearer never-forward",
            "Proxy-Authorization": "Basic never-forward",
        },
    )
    redirected = handler.redirect_request(
        original,
        Response(b""),
        302,
        "Found",
        Message(),
        f"{REPLAY_ORIGIN}/redirected-replay",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") is None
    assert redirected.get_header("Proxy-authorization") is None


def test_cache_identity_includes_api_origin() -> None:
    current_base = ["https://first.example.test"]
    provider = lambda: (current_base[0], "token", {})
    opener = QueueOpener(
        encoded({"matches": [], "nextCursor": "first"}),
        encoded({"matches": [], "nextCursor": "second"}),
    )
    client = FcodePlatform(auth_provider=provider, opener=opener)
    assert client.matches(limit=1)["next_cursor"] == "first"
    current_base[0] = "https://second.example.test"
    assert client.matches(limit=1)["next_cursor"] == "second"
    assert len(opener.requests) == 2


def test_replay_is_proxied_without_forwarding_auth_and_cached() -> None:
    signed = f"{REPLAY_ORIGIN}/replay?X-Amz-Signature=private"
    replay = b"REPLAY26\x00bytes"
    opener = QueueOpener(
        encoded({"url": signed}),
        Response(replay, url=signed),
    )
    client = FcodePlatform(auth_provider=auth(), opener=opener)

    assert client.replay(MATCH_ID, 2) == replay
    assert client.replay(MATCH_ID, 2) == replay
    assert len(opener.requests) == 2
    metadata_request, object_request = [item[0] for item in opener.requests]
    assert metadata_request.get_header("Authorization") == "Bearer secret-token"
    assert object_request.full_url == signed
    assert object_request.get_header("Authorization") is None


def test_parallel_replay_requests_are_single_flight() -> None:
    signed = f"{REPLAY_ORIGIN}/replay?signature=private"
    entered = threading.Event()
    release = threading.Event()
    calls: list[Any] = []

    def opener(request: Any, *, timeout: float) -> Response:
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=2)
            return encoded({"url": signed})
        return Response(b"same replay", url=signed)

    client = FcodePlatform(auth_provider=auth(), opener=opener)
    results: list[bytes] = []
    threads = [
        threading.Thread(target=lambda: results.append(client.replay(MATCH_ID, 1)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=2)
    release.set()
    for thread in threads:
        thread.join(timeout=2)
    assert results == [b"same replay", b"same replay"]
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, 401), (404, 404), (429, 429), (500, 502), (504, 504)],
)
def test_remote_http_errors_are_typed_and_do_not_echo_body(
    status: int, expected: int
) -> None:
    body = io.BytesIO(b'{"error":"signed-url-or-private-upstream-detail"}')
    error = urllib.error.HTTPError(
        "https://api.example.test/api/matches",
        status,
        "upstream",
        Message(),
        body,
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(error))
    with pytest.raises(PlatformError) as caught:
        client.matches(limit=1)
    assert caught.value.code == expected
    assert "private-upstream-detail" not in caught.value.message


def test_unrated_live_400_rate_limit_is_reclassified_and_retry_is_preserved() -> None:
    headers = Message()
    headers["Retry-After"] = "37"
    body = io.BytesIO(
        json.dumps(
            {
                "error": (
                    "Rate limit exceeded: max 5 test/unrated matches "
                    "per 10 minutes"
                )
            }
        ).encode()
    )
    error = urllib.error.HTTPError(
        "https://api.example.test/api/matches/unrated",
        400,
        "upstream",
        headers,
        body,
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(error))

    with pytest.raises(PlatformError) as caught:
        client.request_unrated(TEAM_B)

    assert caught.value.code == 429
    assert caught.value.retry_after_s == 37
    assert caught.value.outcome_unknown is False
    assert caught.value.message == (
        "Rate limit exceeded: max 5 test/unrated matches per 10 minutes"
    )


def test_retry_after_http_date_is_parsed_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = platformmod.parsedate_to_datetime(
        "Wed, 05 Aug 2026 12:00:00 GMT"
    ).timestamp()
    monkeypatch.setattr(platformmod.time, "time", lambda: now)
    headers = Message()
    headers["Retry-After"] = "Wed, 05 Aug 2026 12:01:00 GMT"
    assert platformmod._retry_after_seconds(headers) == 60

    headers.replace_header("Retry-After", str(platformmod._MAX_RETRY_AFTER_S + 1))
    assert platformmod._retry_after_seconds(headers) == platformmod._MAX_RETRY_AFTER_S


@pytest.mark.parametrize(
    ("status", "expected_message"),
    [
        (400, "FCode rejected unrated match request"),
        (401, "FCode session expired; run `fcode login`"),
        (403, "FCode rejected unrated match request"),
        (404, "FCode resource not found"),
        (409, "FCode rejected unrated match request"),
        (422, "FCode rejected unrated match request"),
        (429, "FCode platform rate limit reached"),
    ],
)
def test_unrated_4xx_errors_never_expose_arbitrary_upstream_text(
    status: int, expected_message: str
) -> None:
    private_detail = "private\nvalidation\tdetail " + ("x" * 1000)
    headers = Message()
    headers["Retry-After"] = "19"
    error = urllib.error.HTTPError(
        "https://api.example.test/api/matches/unrated",
        status,
        "upstream",
        headers,
        io.BytesIO(json.dumps({"error": private_detail}).encode()),
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(error))

    with pytest.raises(PlatformError) as caught:
        client.request_unrated(TEAM_B)

    assert caught.value.code == status
    assert caught.value.message == expected_message
    assert "private" not in caught.value.message
    assert len(caught.value.message) < 100
    assert caught.value.retry_after_s == 19
    assert caught.value.outcome_unknown is False


def test_unrated_rate_limit_is_recognized_without_echoing_upstream_text() -> None:
    body = {
        "error": (
            "Rate limit exceeded: max 5 test/unrated matches per 10 minutes "
            "private-detail"
        )
    }
    error = urllib.error.HTTPError(
        "https://api.example.test/api/matches/unrated",
        400,
        "upstream",
        Message(),
        io.BytesIO(json.dumps(body).encode()),
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(error))

    with pytest.raises(PlatformError) as caught:
        client.request_unrated(TEAM_B)

    # A quota message is a cooldown, not a rejection, even when upstream pads it.
    assert caught.value.code == 429
    # The reply is rebuilt from the parsed numbers, so padding cannot leak.
    assert caught.value.message == (
        "Rate limit exceeded: max 5 test/unrated matches per 10 minutes"
    )
    assert "private-detail" not in caught.value.message
    assert caught.value.retry_after_s == 600


def test_unrated_rate_limit_tracks_a_retuned_upstream_quota() -> None:
    body = {"error": "Rate limit exceeded: max 3 unrated matches per 5 minutes"}
    error = urllib.error.HTTPError(
        "https://api.example.test/api/matches/unrated",
        400,
        "upstream",
        Message(),
        io.BytesIO(json.dumps(body).encode()),
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(error))

    with pytest.raises(PlatformError) as caught:
        client.request_unrated(TEAM_B)

    assert caught.value.code == 429
    assert "max 3" in caught.value.message
    assert caught.value.retry_after_s == 300
    assert caught.value.outcome_unknown is False


def test_unrecognized_unrated_rejection_stays_a_plain_rejection() -> None:
    body = {"error": "Opponent has no active submission"}
    error = urllib.error.HTTPError(
        "https://api.example.test/api/matches/unrated",
        400,
        "upstream",
        Message(),
        io.BytesIO(json.dumps(body).encode()),
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(error))

    with pytest.raises(PlatformError) as caught:
        client.request_unrated(TEAM_B)

    assert caught.value.code == 400
    assert caught.value.message == "FCode rejected unrated match request"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (socket.timeout("private timeout"), 504),
        (urllib.error.URLError("private network failure"), 502),
        (
            urllib.error.HTTPError(
                "https://api.example.test/api/matches/unrated",
                500,
                "upstream",
                Message(),
                io.BytesIO(b'{"error":"private server detail"}'),
            ),
            502,
        ),
    ],
)
def test_unrated_transport_and_server_failures_have_unknown_outcome(
    failure: BaseException, code: int
) -> None:
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(failure))

    with pytest.raises(PlatformError) as caught:
        client.request_unrated(TEAM_B)

    assert caught.value.code == code
    assert caught.value.outcome_unknown is True
    assert "private" not in caught.value.message


@pytest.mark.parametrize("response", [encoded([]), encoded({}), encoded({"matchId": "bad"})])
def test_unrated_malformed_success_has_unknown_outcome(response: Response) -> None:
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(response))

    with pytest.raises(PlatformError, match="invalid unrated match response") as caught:
        client.request_unrated(TEAM_B)

    assert caught.value.code == 502
    assert caught.value.outcome_unknown is True


def test_timeout_is_reported_as_gateway_timeout() -> None:
    client = FcodePlatform(
        auth_provider=auth(), opener=QueueOpener(socket.timeout("slow"))
    )
    with pytest.raises(PlatformError) as caught:
        client.matches(limit=1)
    assert caught.value.code == 504


@pytest.mark.parametrize(
    ("phase", "failure", "expected"),
    [
        ("read", socket.timeout("private timeout detail"), 504),
        ("enter", socket.timeout("private enter timeout"), 504),
        ("close", socket.timeout("private close timeout"), 504),
        ("read", OSError("private read failure"), 502),
        ("enter", OSError("private enter failure"), 502),
        ("close", OSError("private close failure"), 502),
    ],
)
def test_response_read_and_close_failures_are_sanitized(
    phase: str, failure: BaseException, expected: int
) -> None:
    response = FailingResponse(
        b'{"matches":[],"nextCursor":null}', failure, phase=phase
    )
    client = FcodePlatform(auth_provider=auth(), opener=QueueOpener(response))

    with pytest.raises(PlatformError) as caught:
        client.matches(limit=1)

    assert caught.value.code == expected
    assert "private" not in caught.value.message


def test_replay_read_failure_is_sanitized() -> None:
    signed = f"{REPLAY_ORIGIN}/replay?signature=private"
    replay_response = FailingResponse(
        b"", OSError("private object store detail"), phase="read", url=signed
    )
    client = FcodePlatform(
        auth_provider=auth(),
        opener=QueueOpener(encoded({"url": signed}), replay_response),
    )

    with pytest.raises(PlatformError) as caught:
        client.replay(MATCH_ID, 1)

    assert caught.value.code == 502
    assert "private" not in caught.value.message


@pytest.mark.parametrize(
    "token",
    [
        "   ",
        "token\r\nX-Leaked: yes",
        "token with spaces",
        "unicode-\N{SNOWMAN}",
        "x" * (platformmod._MAX_BEARER_CHARS + 1),
    ],
)
def test_invalid_bearer_is_rejected_before_header_construction(token: str) -> None:
    opener = QueueOpener()
    client = FcodePlatform(auth_provider=auth(token=token), opener=opener)

    assert client.session()["authenticated"] is False
    with pytest.raises(PlatformError) as caught:
        client.matches(limit=1)

    assert caught.value.code == 401
    assert token not in caught.value.message
    assert opener.requests == []


@pytest.mark.parametrize(
    "base",
    [
        "http://api.example.test",
        "http://192.168.1.4:8080",
        "http://0.0.0.0:8080",
        "ftp://api.example.test",
    ],
)
def test_non_https_non_loopback_api_origins_are_rejected(base: str) -> None:
    client = FcodePlatform(auth_provider=auth(base=base), opener=QueueOpener())
    with pytest.raises(PlatformError) as caught:
        client.matches(limit=1)
    assert caught.value.code == 502
    assert "HTTPS" in caught.value.message or "invalid" in caught.value.message


@pytest.mark.parametrize("base", ["http://127.0.0.1:9999", "http://localhost:9999"])
def test_explicit_loopback_http_api_origin_is_allowed(base: str) -> None:
    opener = QueueOpener(encoded({"matches": [], "nextCursor": None}))
    client = FcodePlatform(auth_provider=auth(base=base), opener=opener)
    assert client.matches(limit=1)["matches"] == []
    assert opener.requests[0][0].full_url.startswith(base)


@pytest.mark.parametrize(
    "signed_url",
    [
        f"http://{urllib.parse.urlsplit(REPLAY_ORIGIN).hostname}/replay",
        "https://localhost/replay",
        "https://127.0.0.1/replay",
        (
            "https://user:password@florentcode-production-replays.s3."
            "eu-north-1.amazonaws.com/replay"
        ),
        "https://florentcode-production-replays.s3.amazonaws.com/replay",
        (
            "https://florentcode-production-replays.s3.eu-north-1."
            "amazonaws.com.attacker.example/replay"
        ),
        (
            "https://florentcode-production-replays.s3.eu-north-1."
            "amazonaws.com./replay"
        ),
    ],
)
def test_unsafe_signed_replay_urls_are_rejected(signed_url: str) -> None:
    client = FcodePlatform(
        auth_provider=auth(), opener=QueueOpener(encoded({"url": signed_url}))
    )
    with pytest.raises(PlatformError) as caught:
        client.replay(MATCH_ID, 1)
    assert caught.value.code == 502


def test_missing_token_is_a_401_without_making_a_request() -> None:
    client = FcodePlatform(auth_provider=auth(token=None), opener=QueueOpener())
    with pytest.raises(PlatformError) as caught:
        client.matches(limit=1)
    assert caught.value.code == 401
