"""A small, bounded RPC transport for the FCode platform client.

The normal ``oarena serve`` process talks to :class:`FcodePlatform` directly.
Hardened installations can instead run :mod:`oarena.platform_sidecar` outside
the game-worker sandbox and point oarena at its filesystem Unix socket with
``OARENA_PLATFORM_SOCKET``.  This module is deliberately only a transport: the
sidecar still uses ``FcodePlatform`` as the sole implementation of remote
requests, authentication, caching, and response normalization.

Each connection carries exactly one request and one response.  A frame is a
fixed preamble, a small JSON header, and a length-delimited binary body.  Replay
bytes therefore remain bytes on the wire rather than being inflated with
base64.  Both peers reject unknown operations and arguments before dispatch.
"""

from __future__ import annotations

import json
import io
import math
import socket
import struct
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from oarena.fcode_platform import PlatformError

__all__ = ["UnixPlatformClient"]


SOCKET_ENV = "OARENA_PLATFORM_SOCKET"

_MAGIC = b"OARPC\x00\x01\n"
_PREAMBLE = struct.Struct("!8sIQ")
_MAX_HEADER_BYTES = 16 << 10
_MAX_JSON_BODY_BYTES = 4 << 20
_MAX_REPLAY_BODY_BYTES = 64 << 20
_MAX_REQUEST_BODY_BYTES = 0
_MAX_CURSOR_CHARS = 2048
_MAX_ERROR_CHARS = 512
_MAX_TEAM_QUERY_CHARS = 200
_MAX_MAP_NAME_CHARS = 200
_MAX_RETRY_AFTER_S = 7 * 24 * 60 * 60
_MAX_SOCKET_PATH_BYTES = 103
# Replay is two sequential remote calls (signed URL, then object storage), and
# urllib's timeout applies to individual socket operations rather than the whole
# exchange. Sixty seconds is a deliberate user-facing ceiling with enough
# margin that ordinary replay downloads do not hit the previous 20s cutoff.
_DEFAULT_TIMEOUT_S = 60.0

_OPERATIONS = frozenset(
    {
        "session",
        "scrim_profile",
        "team_search",
        "platform_maps",
        "request_unrated",
        "ladder",
        "test_runs",
        "matches",
        "match",
        "replay",
    }
)


class _ProtocolError(Exception):
    """A peer violated the framed protocol; its details stay process-local."""


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _json_loads(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicates,
        )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise _ProtocolError("invalid JSON header or body") from exc


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _ProtocolError("value is not strict JSON") from exc


def _exact_keys(
    value: Any,
    *,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
    name: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlatformError(400, f"{name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise PlatformError(400, f"{name} keys must be strings")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise PlatformError(400, f"unsupported {name}: {sorted(unknown)[0]}")
    if missing:
        raise PlatformError(400, f"missing {name}: {sorted(missing)[0]}")
    return value


def _canonical_uuid(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise PlatformError(400, f"{name} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise PlatformError(400, f"{name} must be a canonical UUID") from exc
    if value != str(parsed):
        raise PlatformError(400, f"{name} must be a canonical UUID")
    return value


def _bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlatformError(400, f"{name} must be an integer")
    if not low <= value <= high:
        raise PlatformError(400, f"{name} must be between {low} and {high}")
    return value


def _optional_text(value: Any, name: str, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise PlatformError(400, f"{name} is invalid")
    if any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value):
        raise PlatformError(400, f"{name} is invalid")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PlatformError(400, f"{name} is invalid") from exc
    return value


def _required_text(value: Any, name: str, limit: int) -> str:
    text = _optional_text(value, name, limit)
    if text is None or not text.strip():
        raise PlatformError(400, f"{name} is invalid")
    return text.strip()


def _map_names(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise PlatformError(400, "map_names must be a list")
    if len(value) > 5:
        raise PlatformError(400, "map_names may contain at most 5 maps")
    return [_required_text(item, "map name", _MAX_MAP_NAME_CHARS) for item in value]


def _validate_call(op: Any, raw_args: Any) -> tuple[str, dict[str, Any]]:
    """Return a normalized allowlisted call or raise a safe 400 error."""
    if not isinstance(op, str) or op not in _OPERATIONS:
        raise PlatformError(400, "unsupported platform operation")

    if op in {"session", "scrim_profile", "platform_maps"}:
        args = _exact_keys(raw_args, allowed=frozenset(), name="argument")
        return op, args

    if op == "team_search":
        args = _exact_keys(
            raw_args,
            allowed=frozenset({"query", "limit"}),
            required=frozenset({"query", "limit"}),
            name="argument",
        )
        return op, {
            "query": _required_text(
                args["query"], "query", _MAX_TEAM_QUERY_CHARS
            ),
            "limit": _bounded_int(args["limit"], "limit", 1, 20),
        }

    if op == "request_unrated":
        args = _exact_keys(
            raw_args,
            allowed=frozenset(
                {"opponent_team_id", "source_match_id", "map_names"}
            ),
            required=frozenset(
                {"opponent_team_id", "source_match_id", "map_names"}
            ),
            name="argument",
        )
        source_match_id = args["source_match_id"]
        return op, {
            "opponent_team_id": _canonical_uuid(
                args["opponent_team_id"], "opponent_team_id"
            ),
            "source_match_id": (
                None
                if source_match_id is None
                else _canonical_uuid(source_match_id, "source_match_id")
            ),
            "map_names": _map_names(args["map_names"]),
        }

    if op in {"ladder", "test_runs"}:
        args = _exact_keys(
            raw_args,
            allowed=frozenset({"limit"}),
            required=frozenset({"limit"}),
            name="argument",
        )
        return op, {"limit": _bounded_int(args["limit"], "limit", 1, 100)}

    if op == "match":
        args = _exact_keys(
            raw_args,
            allowed=frozenset({"match_id"}),
            required=frozenset({"match_id"}),
            name="argument",
        )
        return op, {"match_id": _canonical_uuid(args["match_id"], "match_id")}

    if op == "replay":
        args = _exact_keys(
            raw_args,
            allowed=frozenset({"match_id", "game"}),
            required=frozenset({"match_id", "game"}),
            name="argument",
        )
        return op, {
            "match_id": _canonical_uuid(args["match_id"], "match_id"),
            "game": _bounded_int(args["game"], "game", 1, 5),
        }

    args = _exact_keys(
        raw_args,
        allowed=frozenset(
            {"limit", "match_type", "mine", "team_id", "cursor"}
        ),
        required=frozenset(
            {"limit", "match_type", "mine", "team_id", "cursor"}
        ),
        name="argument",
    )
    limit = _bounded_int(args["limit"], "limit", 1, 100)
    match_type = args["match_type"]
    if match_type is not None and (
        not isinstance(match_type, str)
        or match_type not in {"ladder", "unrated"}
    ):
        raise PlatformError(400, "match_type must be 'ladder' or 'unrated'")
    mine = args["mine"]
    if not isinstance(mine, bool):
        raise PlatformError(400, "mine must be a boolean")
    raw_team_id = args["team_id"]
    team_id = (
        None
        if raw_team_id is None
        else _canonical_uuid(raw_team_id, "team_id")
    )
    if mine and team_id is not None:
        raise PlatformError(400, "mine and team_id cannot be combined")
    cursor = _optional_text(args["cursor"], "cursor", _MAX_CURSOR_CHARS)
    return op, {
        "limit": limit,
        "match_type": match_type,
        "mine": mine,
        "team_id": team_id,
        "cursor": cursor,
    }


def _socket_path(value: str | Path) -> str:
    text = str(value)
    if not text or "\x00" in text:
        raise ValueError("platform socket path is empty or contains NUL")
    path = Path(text)
    if not path.is_absolute():
        raise ValueError("platform socket path must be absolute")
    if len(text.encode()) > _MAX_SOCKET_PATH_BYTES:
        raise ValueError("platform socket path is too long")
    return text


def _set_deadline_timeout(peer: socket.socket, deadline: float | None) -> None:
    if deadline is None:
        return
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("RPC deadline expired")
    peer.settimeout(remaining)


def _recv_exact(
    peer: socket.socket,
    length: int,
    *,
    deadline: float | None = None,
) -> bytes:
    # BytesIO retains one growing body buffer instead of keeping every recv()
    # chunk alive and then joining a second body-sized allocation.
    output = io.BytesIO()
    remaining = length
    while remaining:
        _set_deadline_timeout(peer, deadline)
        try:
            chunk = peer.recv(min(remaining, 128 << 10))
        except socket.timeout as exc:
            raise TimeoutError("RPC read timed out") from exc
        if not chunk:
            raise _ProtocolError("truncated RPC frame")
        output.write(chunk)
        remaining -= len(chunk)
    return output.getvalue()


def _recv_eof(peer: socket.socket, *, deadline: float | None = None) -> None:
    _set_deadline_timeout(peer, deadline)
    try:
        extra = peer.recv(1)
    except socket.timeout as exc:
        raise TimeoutError("RPC read timed out") from exc
    if extra:
        raise _ProtocolError("trailing bytes after RPC frame")


def _recv_frame(
    peer: socket.socket,
    *,
    max_body_bytes: int,
    body_limit: Callable[[dict[str, Any]], int] | None = None,
    deadline: float | None = None,
) -> tuple[dict[str, Any], bytes]:
    raw_preamble = _recv_exact(peer, _PREAMBLE.size, deadline=deadline)
    magic, header_length, body_length = _PREAMBLE.unpack(raw_preamble)
    if magic != _MAGIC:
        raise _ProtocolError("invalid RPC magic or version")
    if not 2 <= header_length <= _MAX_HEADER_BYTES:
        raise _ProtocolError("RPC header length is out of bounds")
    if body_length > max_body_bytes:
        raise _ProtocolError("RPC body length is out of bounds")
    header = _json_loads(_recv_exact(peer, header_length, deadline=deadline))
    if not isinstance(header, dict):
        raise _ProtocolError("RPC header must be an object")
    if body_limit is not None:
        selected_limit = body_limit(header)
        if not 0 <= selected_limit <= max_body_bytes or body_length > selected_limit:
            raise _ProtocolError("RPC body length does not match its response kind")
    return header, _recv_exact(peer, body_length, deadline=deadline)


def _send_frame(peer: socket.socket, header: Mapping[str, Any], body: bytes) -> None:
    raw_header = _json_bytes(header)
    if not 2 <= len(raw_header) <= _MAX_HEADER_BYTES:
        raise _ProtocolError("RPC header length is out of bounds")
    peer.sendall(_PREAMBLE.pack(_MAGIC, len(raw_header), len(body)))
    peer.sendall(raw_header)
    if body:
        peer.sendall(body)


def _safe_error_message(value: Any) -> str:
    if not isinstance(value, str):
        raise _ProtocolError("RPC error message must be text")
    value = value.strip()
    if not value or len(value) > _MAX_ERROR_CHARS:
        raise _ProtocolError("RPC error message is out of bounds")
    if any(ord(char) < 0x20 and char not in "\t" for char in value):
        raise _ProtocolError("RPC error message contains control characters")
    return value


class UnixPlatformClient:
    """Thread-safe one-connection-per-call client for the platform sidecar."""

    def __init__(
        self,
        socket_path: str | Path,
        *,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.socket_path = _socket_path(socket_path)
        timeout = float(timeout_s)
        if not math.isfinite(timeout) or not 0.1 <= timeout <= 120.0:
            raise ValueError("platform RPC timeout must be between 0.1 and 120 seconds")
        self.timeout_s = timeout

    def session(self) -> dict[str, Any]:
        return self._json_call("session", {})

    def scrim_profile(self) -> dict[str, Any]:
        return self._json_call("scrim_profile", {})

    def team_search(self, query: str, *, limit: int = 20) -> dict[str, Any]:
        return self._json_call("team_search", {"query": query, "limit": limit})

    def platform_maps(self) -> dict[str, Any]:
        return self._json_call("platform_maps", {})

    def request_unrated(
        self,
        opponent_team_id: str,
        *,
        source_match_id: str | None = None,
        map_names: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return self._json_call(
            "request_unrated",
            {
                "opponent_team_id": opponent_team_id,
                "source_match_id": source_match_id,
                "map_names": map_names,
            },
        )

    def ladder(self, *, limit: int) -> dict[str, Any]:
        return self._json_call("ladder", {"limit": limit})

    def test_runs(self, *, limit: int) -> dict[str, Any]:
        return self._json_call("test_runs", {"limit": limit})

    def matches(
        self,
        *,
        limit: int,
        match_type: str | None = None,
        mine: bool = False,
        team_id: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._json_call(
            "matches",
            {
                "limit": limit,
                "match_type": match_type,
                "mine": mine,
                "team_id": team_id,
                "cursor": cursor,
            },
        )

    def match(self, match_id: str) -> dict[str, Any]:
        return self._json_call("match", {"match_id": match_id})

    def replay(self, match_id: str, game: int) -> bytes:
        result = self._call("replay", {"match_id": match_id, "game": game})
        if not isinstance(result, bytes):  # defence against a confused peer
            raise PlatformError(502, "invalid response from FCode platform sidecar")
        return result

    def _json_call(self, op: str, args: dict[str, Any]) -> dict[str, Any]:
        result = self._call(op, args)
        if not isinstance(result, dict):
            raise PlatformError(
                502,
                "invalid response from FCode platform sidecar",
                outcome_unknown=op == "request_unrated",
            )
        return result

    def _call(self, op: str, args: dict[str, Any]) -> dict[str, Any] | bytes:
        # Validate on both sides: local validation gives immediate feedback,
        # while server validation is the actual sandbox trust boundary.
        op, args = _validate_call(op, args)
        request_sent = False
        try:
            deadline = time.monotonic() + self.timeout_s
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.settimeout(self.timeout_s)
                peer.connect(self.socket_path)
                _set_deadline_timeout(peer, deadline)
                _send_frame(peer, {"op": op, "args": args}, b"")
                request_sent = True
                peer.shutdown(socket.SHUT_WR)

                def response_body_limit(header: dict[str, Any]) -> int:
                    if header.get("ok") is False:
                        return 0
                    return (
                        _MAX_REPLAY_BODY_BYTES
                        if op == "replay" and header.get("kind") == "replay"
                        else _MAX_JSON_BODY_BYTES
                    )

                header, body = _recv_frame(
                    peer,
                    max_body_bytes=_MAX_REPLAY_BODY_BYTES,
                    body_limit=response_body_limit,
                    deadline=deadline,
                )
                try:
                    _recv_eof(peer, deadline=deadline)
                except ConnectionResetError:
                    # A saturated sidecar rejects without draining our already
                    # bounded request, so AF_UNIX may report reset after the
                    # complete error frame. It is still an unambiguous close.
                    pass
        except PlatformError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise PlatformError(
                504,
                "FCode platform sidecar timed out",
                outcome_unknown=op == "request_unrated" and request_sent,
            ) from exc
        except (OSError, _ProtocolError) as exc:
            raise PlatformError(
                502,
                "FCode platform sidecar is unavailable",
                outcome_unknown=op == "request_unrated" and request_sent,
            ) from exc

        try:
            allowed_fields = {
                "ok",
                "kind",
                "code",
                "message",
                "retry_after_s",
                "outcome_unknown",
            }
            if "ok" not in header or set(header) - allowed_fields:
                raise _ProtocolError("invalid RPC response fields")
            top = header
            ok = top["ok"]
            if not isinstance(ok, bool):
                raise _ProtocolError("RPC ok field must be a boolean")
            if not ok:
                required = {"ok", "code", "message"}
                error_fields = required | {"retry_after_s", "outcome_unknown"}
                if not required <= set(top) or set(top) - error_fields or body:
                    raise _ProtocolError("invalid RPC error response")
                code = top["code"]
                if (
                    isinstance(code, bool)
                    or not isinstance(code, int)
                    or not 400 <= code <= 599
                ):
                    raise _ProtocolError("RPC error status is invalid")
                retry_after_s = top.get("retry_after_s")
                if retry_after_s is not None and (
                    isinstance(retry_after_s, bool)
                    or not isinstance(retry_after_s, int)
                    or not 0 <= retry_after_s <= _MAX_RETRY_AFTER_S
                ):
                    raise _ProtocolError("RPC retry delay is invalid")
                outcome_unknown = top.get("outcome_unknown", False)
                if not isinstance(outcome_unknown, bool):
                    raise _ProtocolError("RPC outcome marker is invalid")
                raise PlatformError(
                    code,
                    _safe_error_message(top["message"]),
                    retry_after_s=retry_after_s,
                    outcome_unknown=outcome_unknown,
                )

            if set(top) != {"ok", "kind"}:
                raise _ProtocolError("invalid RPC success response")
            expected_kind = "replay" if op == "replay" else "json"
            if top["kind"] != expected_kind:
                raise _ProtocolError("RPC response kind does not match request")
            if expected_kind == "replay":
                if len(body) > _MAX_REPLAY_BODY_BYTES:
                    raise _ProtocolError("RPC replay body is too large")
                return body
            if len(body) > _MAX_JSON_BODY_BYTES:
                raise _ProtocolError("RPC JSON body is too large")
            value = _json_loads(body)
            if not isinstance(value, dict):
                raise _ProtocolError("RPC JSON response must be an object")
            return value
        except PlatformError:
            raise
        except _ProtocolError as exc:
            raise PlatformError(
                502,
                "invalid response from FCode platform sidecar",
                outcome_unknown=op == "request_unrated" and request_sent,
            ) from exc


# The server module intentionally imports these private helpers. Keeping the
# framing implementation in one place prevents client/server drift without
# exposing a general-purpose RPC API to the rest of oarena.
