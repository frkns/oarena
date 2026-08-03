"""Narrow, privacy-preserving proxy for the authenticated FCode platform API.

The browser must never receive the CLI bearer token or the signed object-store
URL used to download a replay.  This module therefore owns the entire remote
exchange and returns only small, explicitly whitelisted records to the oarena
HTTP handler.  Importing it does not import :mod:`fcode`; credentials are
resolved lazily for each public operation. Ambient CLI credentials and API URL
changes therefore take effect without restarting oarena. A systemd
``LoadCredential=`` file is intentionally a service-start snapshot instead;
restart the platform sidecar after ``fcode login`` or ``fcode logout``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import http.client
import ipaddress
import json
import math
import os
import socket
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO

__all__ = ["FcodePlatform", "PlatformError"]


_MAX_JSON_BYTES = 4 << 20
_MAX_REPLAY_BYTES = 64 << 20
_DEFAULT_REPLAY_CACHE_BYTES = 64 << 20
_MAX_CACHE_ENTRIES = 128
_MAX_BEARER_CHARS = 8192
_MAX_TEST_RUN_ERROR_CHARS = 1000
_MAX_SYSTEMD_CREDENTIAL_BYTES = 64 << 10
_SYSTEMD_CREDENTIAL_FILE = "fcode_credentials.json"
_REPLAY_HOSTS = frozenset(
    {"florentcode-production-replays.s3.eu-north-1.amazonaws.com"}
)


class PlatformError(Exception):
    """A safe platform failure carrying the status oarena should return."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclasses.dataclass(frozen=True)
class _Auth:
    base_url: str
    token: str | None
    credentials: Mapping[str, Any]
    fingerprint: str


@dataclasses.dataclass
class _Flight:
    event: threading.Event = dataclasses.field(default_factory=threading.Event)
    value: Any = None
    error: BaseException | None = None


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse redirects before urllib can copy an API bearer to a new URL."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        del req, code, msg, headers, newurl
        try:
            fp.close()
        except Exception:
            pass
        raise PlatformError(502, "FCode API redirect refused")


class _ReplayRedirects(urllib.request.HTTPRedirectHandler):
    """Validate every object-store redirect before opening its destination."""

    def __init__(self, validator: Callable[[Any], None]) -> None:
        super().__init__()
        self._validator = validator

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        # This hook runs before HTTPRedirectHandler opens ``newurl``.
        try:
            self._validator(newurl)
        except BaseException:
            try:
                fp.close()
            except Exception:
                pass
            raise
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        # Signed object fetches never need platform authentication. Strip both
        # header maps case-insensitively as defence in depth.
        for mapping in (redirected.headers, redirected.unredirected_hdrs):
            for name in list(mapping):
                if name.lower() in {"authorization", "proxy-authorization"}:
                    del mapping[name]
        return redirected


def _default_auth_provider() -> tuple[str, str | None, Mapping[str, Any] | None]:
    """Load ambient fcode authentication without using its CLI error helpers."""
    credential_directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if credential_directory is not None:
        return _systemd_auth_provider(credential_directory)
    try:
        from fcode.auth import get_api_url, get_token, load_credentials
    except (ImportError, OSError) as exc:
        raise PlatformError(502, "fcode authentication is unavailable") from exc
    try:
        return get_api_url(), get_token(), load_credentials()
    except (OSError, TypeError, ValueError) as exc:
        raise PlatformError(502, "could not read fcode credentials") from exc


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_systemd_credential() -> PlatformError:
    return PlatformError(502, "systemd fcode credential is invalid")


def _read_systemd_credential(directory: str) -> Mapping[str, Any] | None:
    """Read one fixed, bounded systemd credential without following a symlink."""
    if not directory or "\x00" in directory:
        raise _invalid_systemd_credential()
    root = Path(directory)
    if not root.is_absolute():
        raise _invalid_systemd_credential()
    path = root / _SYSTEMD_CREDENTIAL_FILE
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PlatformError(502, "could not read systemd fcode credential") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_SYSTEMD_CREDENTIAL_BYTES:
            raise _invalid_systemd_credential()
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(_MAX_SYSTEMD_CREDENTIAL_BYTES + 1)
    except PlatformError:
        raise
    except OSError as exc:
        raise PlatformError(502, "could not read systemd fcode credential") from exc
    finally:
        os.close(descriptor)
    if not raw or len(raw) > _MAX_SYSTEMD_CREDENTIAL_BYTES:
        raise _invalid_systemd_credential()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as exc:
        raise _invalid_systemd_credential() from exc
    if not isinstance(value, Mapping):
        raise _invalid_systemd_credential()
    return value


def _systemd_auth_provider(
    credential_directory: str,
) -> tuple[str, str | None, Mapping[str, Any] | None]:
    """Load systemd's flattened ``fcode_credentials.json`` or report logged out."""
    try:
        from fcode.auth import get_api_url

        base_url = get_api_url()
    except (ImportError, OSError, TypeError, ValueError) as exc:
        raise PlatformError(502, "fcode authentication is unavailable") from exc
    raw = _read_systemd_credential(credential_directory)
    if raw is None:
        return base_url, None, None
    # ``SetCredential=fcode_credentials:{}`` is the explicit logged-out
    # fallback when ~/.fcode/credentials.json does not exist at service start.
    # No other tokenless object is accepted.
    if not raw:
        return base_url, None, None
    allowed = {"token", "expires_at", "user", "team"}
    if set(raw) - allowed or "token" not in raw:
        raise _invalid_systemd_credential()
    token = _bearer_token(raw.get("token"))
    if token is None:
        raise _invalid_systemd_credential()
    expires_at = raw.get("expires_at")
    if expires_at is not None and (
        not isinstance(expires_at, str) or len(expires_at) > 256
    ):
        raise _invalid_systemd_credential()
    user = raw.get("user")
    if user is not None:
        if not isinstance(user, Mapping) or set(user) - {"id", "name", "email"}:
            raise _invalid_systemd_credential()
        if any(not isinstance(value, str) or len(value) > 512 for value in user.values()):
            raise _invalid_systemd_credential()
    raw_team = raw.get("team")
    team: dict[str, str] | None = None
    if raw_team is not None:
        if (
            not isinstance(raw_team, Mapping)
            or set(raw_team) != {"id", "name"}
            or not isinstance(raw_team.get("id"), str)
            or not isinstance(raw_team.get("name"), str)
            or not 1 <= len(raw_team["id"]) <= 128
            or not 1 <= len(raw_team["name"]) <= 200
        ):
            raise _invalid_systemd_credential()
        team = {"id": raw_team["id"], "name": raw_team["name"]}
    return base_url, token, {"team": team}


def _safe_text(value: Any, *, limit: int = 256) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return value[:limit]


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _safe_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _bearer_token(value: Any) -> str | None:
    """Return a header-safe bearer, never attempting to repair credentials."""
    if not isinstance(value, str) or not value or len(value) > _MAX_BEARER_CHARS:
        return None
    # OAuth bearer values do not contain whitespace. Restricting to visible
    # ASCII also prevents CRLF injection and late latin-1 encoding failures.
    if any(not 0x21 <= ord(char) <= 0x7E for char in value):
        return None
    return value


def _is_loopback_host(hostname: str) -> bool:
    if hostname.rstrip(".").lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _team(raw: Mapping[str, Any], side: str) -> dict[str, Any]:
    return {
        "id": _safe_text(raw.get(f"team{side}Id"), limit=128),
        "name": _safe_text(raw.get(f"team{side}Name"), limit=200),
        "version": _safe_int(raw.get(f"team{side}Version")),
        "rating": _safe_number(raw.get(f"team{side}Rating")),
        "matches_played": _safe_int(raw.get(f"team{side}MatchesPlayed")),
    }


def _match(raw: Mapping[str, Any]) -> dict[str, Any]:
    match_type = _safe_text(raw.get("triggeredBy"), limit=32)
    rated = _safe_bool(raw.get("rated"))
    if rated is None:
        rated = match_type == "ladder"
    return {
        "id": _safe_text(raw.get("id"), limit=128),
        "status": _safe_text(raw.get("status"), limit=32),
        "stage": _safe_text(raw.get("stage"), limit=64),
        "type": match_type,
        "rated": rated,
        "team_a": _team(raw, "A"),
        "team_b": _team(raw, "B"),
        "winner_id": _safe_text(raw.get("winnerId"), limit=128),
        "score_a": _safe_int(raw.get("scoreA")),
        "score_b": _safe_int(raw.get("scoreB")),
        "rating_delta_a": _safe_number(raw.get("eloDeltaA")),
        "rating_delta_b": _safe_number(raw.get("eloDeltaB")),
        "source_match_a_id": _safe_text(raw.get("sourceMatchAId"), limit=128),
        "source_match_b_id": _safe_text(raw.get("sourceMatchBId"), limit=128),
        "created_at": _safe_text(raw.get("createdAt"), limit=64),
        "completed_at": _safe_text(raw.get("completedAt"), limit=64),
        "error": _safe_text(
            raw.get("errorMessage"), limit=_MAX_TEST_RUN_ERROR_CHARS
        ),
    }


def _test_bot(raw: Mapping[str, Any], side: str) -> dict[str, Any]:
    """Return a test upload in the same public shape as a match team."""
    return {
        "id": None,
        "name": _safe_text(raw.get(f"testBot{side}Name"), limit=200),
        "version": None,
        "rating": None,
        "matches_played": None,
    }


def _test_run(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Privacy-reduce an official remote test run to a match-like record."""
    return {
        "id": _safe_text(raw.get("id"), limit=128),
        "status": _safe_text(raw.get("status"), limit=32),
        "stage": _safe_text(raw.get("stage"), limit=64),
        "type": "test",
        "rated": False,
        "team_a": _test_bot(raw, "A"),
        "team_b": _test_bot(raw, "B"),
        "winner_id": _safe_text(raw.get("winnerId"), limit=128),
        "score_a": _safe_int(raw.get("scoreA")),
        "score_b": _safe_int(raw.get("scoreB")),
        "rating_delta_a": None,
        "rating_delta_b": None,
        "source_match_a_id": None,
        "source_match_b_id": None,
        "created_at": _safe_text(raw.get("createdAt"), limit=64),
        "completed_at": _safe_text(raw.get("completedAt"), limit=64),
        "requested_by_name": _safe_text(raw.get("requestedByName"), limit=200),
        "error": _safe_text(
            raw.get("errorMessage"), limit=_MAX_TEST_RUN_ERROR_CHARS
        ),
    }


def _game(raw: Mapping[str, Any]) -> dict[str, Any]:
    # replayS3Key is deliberately reduced to a boolean.  Object keys and the
    # subsequently issued signed URL never cross the local API boundary.
    return {
        "number": _safe_int(raw.get("gameNumber")),
        "map_name": _safe_text(raw.get("mapName"), limit=200),
        "map_seed": _safe_int(raw.get("mapSeed")),
        "winner_id": _safe_text(raw.get("winnerId"), limit=128),
        "winner_side": _safe_text(raw.get("winnerSide"), limit=8),
        "win_condition": _safe_text(raw.get("winCondition"), limit=64),
        "turns": _safe_int(raw.get("turnsPlayed")),
        "has_replay": bool(_safe_text(raw.get("replayS3Key"), limit=1024)),
        "created_at": _safe_text(raw.get("createdAt"), limit=64),
    }


class FcodePlatform:
    """Thread-safe authenticated client used by the local oarena server.

    ``auth_provider`` and ``opener`` are injectable so the remote boundary can
    be tested deterministically without touching the user's real credentials or
    the network.  The opener has the same call shape as ``urlopen``. Production
    calls use separate redirect-safe urllib openers when it is omitted.
    """

    def __init__(
        self,
        *,
        auth_provider: Callable[
            [], tuple[str, str | None, Mapping[str, Any] | None]
        ] = _default_auth_provider,
        opener: Callable[..., BinaryIO] | None = None,
        clock: Callable[[], float] = time.monotonic,
        json_ttl_s: float = 5.0,
        ladder_ttl_s: float = 60.0,
        complete_detail_ttl_s: float = 300.0,
        replay_cache_bytes: int = _DEFAULT_REPLAY_CACHE_BYTES,
        timeout_s: float = 15.0,
    ) -> None:
        self._auth_provider = auth_provider
        self._opener = opener
        self._json_opener = urllib.request.build_opener(_RejectRedirects())
        self._replay_opener = urllib.request.build_opener(
            _ReplayRedirects(self._validate_signed_url)
        )
        self._clock = clock
        self._json_ttl_s = max(0.0, float(json_ttl_s))
        self._ladder_ttl_s = max(0.0, float(ladder_ttl_s))
        self._complete_detail_ttl_s = max(
            self._json_ttl_s, float(complete_detail_ttl_s)
        )
        self._replay_cache_limit = max(0, int(replay_cache_bytes))
        self._timeout_s = max(0.1, float(timeout_s))
        self._lock = threading.RLock()
        self._json_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._replay_cache: OrderedDict[str, bytes] = OrderedDict()
        self._replay_cache_size = 0
        self._flights: dict[str, _Flight] = {}

    # -- public normalized operations ---------------------------------

    def session(self) -> dict[str, Any]:
        base_url, token, credentials = self._load_raw_auth()
        del base_url
        credentials = credentials if isinstance(credentials, Mapping) else {}
        raw_team = credentials.get("team")
        team = None
        if isinstance(raw_team, Mapping):
            team_id = _safe_text(raw_team.get("id"), limit=128)
            team_name = _safe_text(raw_team.get("name"), limit=200)
            if team_id or team_name:
                team = {"id": team_id, "name": team_name}
        return {"authenticated": _bearer_token(token) is not None, "team": team}

    def matches(
        self,
        *,
        limit: int,
        match_type: str | None = None,
        mine: bool = False,
        team_id: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        auth = self._require_auth()
        params: dict[str, str] = {"limit": str(limit)}
        if match_type:
            params["type"] = match_type
        if team_id:
            params["teamIds"] = team_id
        elif mine:
            raw_team = auth.credentials.get("team")
            own_id = raw_team.get("id") if isinstance(raw_team, Mapping) else None
            own_id = _safe_text(own_id, limit=128)
            if not own_id:
                raise PlatformError(400, "the fcode account is not on a team")
            params["teamIds"] = own_id
        if cursor:
            params["cursor"] = cursor

        path = "/api/matches?" + urllib.parse.urlencode(params)
        key = f"json:{auth.fingerprint}:{path}"

        def load() -> dict[str, Any]:
            raw = self._request_json(auth, path)
            raw_matches = raw.get("matches") if isinstance(raw, Mapping) else None
            if not isinstance(raw_matches, list):
                raise PlatformError(502, "invalid matches response from FCode")
            normalized = [
                _match(item) for item in raw_matches if isinstance(item, Mapping)
            ]
            next_cursor = _safe_text(
                raw.get("nextCursor") if isinstance(raw, Mapping) else None,
                limit=2048,
            )
            return {"matches": normalized, "next_cursor": next_cursor}

        return self._cached_json(key, self._json_ttl_s, load)

    def match(self, match_id: str) -> dict[str, Any]:
        auth = self._require_auth()
        path = f"/api/matches/{match_id}"
        key = f"detail:{auth.fingerprint}:{match_id}"

        # Running details intentionally expire quickly. Complete/error matches
        # are immutable and are promoted to the longer cache after loading.
        cached = self._json_cache_get(key)
        if cached is not None:
            return cached

        def load() -> dict[str, Any]:
            raw = self._request_json(auth, path)
            raw_match = raw.get("match") if isinstance(raw, Mapping) else None
            raw_games = raw.get("games") if isinstance(raw, Mapping) else None
            if not isinstance(raw_match, Mapping) or not isinstance(raw_games, list):
                raise PlatformError(502, "invalid match response from FCode")
            result = {
                "match": _match(raw_match),
                "games": [_game(item) for item in raw_games if isinstance(item, Mapping)],
            }
            status = result["match"]["status"]
            ttl = (
                self._complete_detail_ttl_s
                if status in {"complete", "error"}
                else self._json_ttl_s
            )
            self._json_cache_put(key, result, ttl)
            return result

        return self._single_flight(key, load)

    def test_runs(self, *, limit: int) -> dict[str, Any]:
        """List official uploaded-bot test runs without leaking upload keys.

        The upstream route has no pagination or limit parameter. Cache its
        complete privacy-reduced response once, then apply each caller's limit
        locally so differently sized dashboard requests share one short-lived
        cache entry.
        """
        auth = self._require_auth()
        path = "/api/matches/test-runs"
        key = f"test-runs:{auth.fingerprint}:{path}"

        def load() -> dict[str, Any]:
            raw = self._request_json(auth, path)
            raw_matches = raw.get("matches") if isinstance(raw, Mapping) else None
            if not isinstance(raw_matches, list):
                raise PlatformError(502, "invalid test runs response from FCode")
            normalized = [
                _test_run(item) for item in raw_matches if isinstance(item, Mapping)
            ]
            return {"test_runs": normalized, "total": len(normalized)}

        result = self._cached_json(key, self._json_ttl_s, load)
        local_limit = max(0, int(limit))
        return {
            "test_runs": result["test_runs"][:local_limit],
            "total": result["total"],
        }

    def ladder(self, *, limit: int) -> dict[str, Any]:
        # The official ladder is public. Keeping this available while logged
        # out also makes the session error actionable instead of blanking the
        # entire platform tab.
        auth = self._auth(require_token=False, send_token=False)
        path = "/api/ladder"
        key = f"ladder:{auth.fingerprint}:{limit}"

        def load() -> dict[str, Any]:
            raw = self._request_json(auth, path)
            rows: Any = raw
            if isinstance(raw, Mapping):
                rows = raw.get("rankings")
            if not isinstance(rows, list):
                raise PlatformError(502, "invalid ladder response from FCode")
            rankings: list[dict[str, Any]] = []
            for rank, item in enumerate(rows[:limit], start=1):
                if not isinstance(item, Mapping):
                    continue
                rankings.append(
                    {
                        "rank": rank,
                        "team_id": _safe_text(item.get("teamId"), limit=128),
                        "team_name": _safe_text(item.get("teamName"), limit=200),
                        "rating": _safe_number(item.get("rating")),
                        "matches_played": _safe_int(item.get("matchesPlayed")),
                    }
                )
            return {"rankings": rankings, "total": len(rows)}

        return self._cached_json(key, self._ladder_ttl_s, load)

    def replay(self, match_id: str, game: int) -> bytes:
        auth = self._require_auth()
        key = f"replay:{auth.fingerprint}:{match_id}:{game}"
        cached = self._replay_cache_get(key)
        if cached is not None:
            return cached

        def load() -> bytes:
            query = urllib.parse.urlencode({"matchId": match_id, "game": str(game)})
            raw = self._request_json(auth, f"/api/matches/replay?{query}")
            signed_url = raw.get("url") if isinstance(raw, Mapping) else None
            if not isinstance(signed_url, str) or not signed_url:
                raise PlatformError(404, "replay is not available")
            self._validate_signed_url(signed_url)
            request = urllib.request.Request(signed_url, method="GET")
            response = self._open(
                request,
                timeout=max(30.0, self._timeout_s),
                redirect_policy="signed_replay",
            )
            body = self._read_response(
                response,
                limit=_MAX_REPLAY_BYTES,
                large_message="FCode replay is unexpectedly large",
                before_read=lambda opened: self._validate_signed_url(
                    getattr(opened, "geturl", lambda: signed_url)()
                ),
            )
            if len(body) > _MAX_REPLAY_BYTES:
                raise PlatformError(502, "FCode replay is unexpectedly large")
            if not body:
                raise PlatformError(502, "FCode returned an empty replay")
            self._replay_cache_put(key, body)
            return body

        return self._single_flight(key, load)

    # -- auth and remote transport -------------------------------------

    def _load_raw_auth(
        self,
    ) -> tuple[str, str | None, Mapping[str, Any] | None]:
        try:
            base_url, token, credentials = self._auth_provider()
        except PlatformError:
            raise
        except Exception as exc:
            raise PlatformError(502, "could not read fcode credentials") from exc
        if not isinstance(base_url, str):
            raise PlatformError(502, "fcode API URL is invalid")
        return base_url, token if isinstance(token, str) else None, credentials

    def _require_auth(self) -> _Auth:
        return self._auth(require_token=True)

    def _auth(self, *, require_token: bool, send_token: bool = True) -> _Auth:
        base_url, token, credentials = self._load_raw_auth()
        valid_token = _bearer_token(token)
        if require_token and valid_token is None:
            raise PlatformError(401, "not logged in to FCode; run `fcode login`")
        try:
            split = urllib.parse.urlsplit(base_url)
            hostname = split.hostname
            split.port  # Force validation of a malformed/non-numeric port.
        except ValueError as exc:
            raise PlatformError(502, "fcode API URL is invalid") from exc
        if split.scheme not in {"http", "https"} or not split.netloc or not hostname:
            raise PlatformError(502, "fcode API URL is invalid")
        if split.username is not None or split.password is not None:
            raise PlatformError(502, "fcode API URL must not contain credentials")
        if split.scheme == "http" and not _is_loopback_host(hostname):
            raise PlatformError(502, "fcode API URL must use HTTPS")
        clean_base = urllib.parse.urlunsplit(
            (split.scheme, split.netloc, split.path.rstrip("/"), "", "")
        )
        request_token = valid_token if send_token else None
        # Include the origin as well as the credential so changing
        # FCODE_API_URL cannot return data cached from the previous platform.
        fingerprint = hashlib.sha256(
            (clean_base + "\0" + (request_token or "")).encode("utf-8")
        ).hexdigest()[:20]
        return _Auth(
            clean_base,
            request_token,
            credentials if send_token and isinstance(credentials, Mapping) else {},
            fingerprint,
        )

    def _request_json(self, auth: _Auth, path: str) -> Any:
        headers = {
            "Accept": "application/json",
            "User-Agent": "oarena-platform-proxy/1",
        }
        if auth.token:
            headers["Authorization"] = f"Bearer {auth.token}"
        request = urllib.request.Request(
            auth.base_url + path, headers=headers, method="GET"
        )
        response = self._open(request, timeout=self._timeout_s)
        body = self._read_response(
            response,
            limit=_MAX_JSON_BYTES,
            large_message="FCode JSON response is unexpectedly large",
        )
        if len(body) > _MAX_JSON_BYTES:
            raise PlatformError(502, "FCode JSON response is unexpectedly large")
        try:
            return json.loads(body, parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise PlatformError(502, "invalid JSON response from FCode") from exc

    def _open(
        self,
        request: urllib.request.Request,
        *,
        timeout: float,
        redirect_policy: str = "reject",
    ) -> BinaryIO:
        try:
            if self._opener is not None:
                return self._opener(request, timeout=timeout)
            opener = (
                self._replay_opener
                if redirect_policy == "signed_replay"
                else self._json_opener
            )
            return opener.open(request, timeout=timeout)
        except PlatformError:
            raise
        except urllib.error.HTTPError as exc:
            # Do not echo the upstream body: errors may include platform or bot
            # internals and are not needed by the dashboard.
            try:
                exc.close()
            except Exception:
                pass
            if exc.code == 401:
                raise PlatformError(
                    401, "FCode session expired; run `fcode login`"
                ) from exc
            if exc.code == 404:
                raise PlatformError(404, "FCode resource not found") from exc
            if exc.code == 429:
                raise PlatformError(429, "FCode platform rate limit reached") from exc
            if exc.code in {408, 504}:
                raise PlatformError(504, "FCode platform request timed out") from exc
            raise PlatformError(502, "FCode platform request failed") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise PlatformError(504, "FCode platform request timed out") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise PlatformError(504, "FCode platform request timed out") from exc
            raise PlatformError(502, "could not reach the FCode platform") from exc
        except OSError as exc:
            raise PlatformError(502, "could not reach the FCode platform") from exc

    def _read_response(
        self,
        response: BinaryIO,
        *,
        limit: int,
        large_message: str,
        before_read: Callable[[BinaryIO], None] | None = None,
    ) -> bytes:
        """Read and close a remote response without leaking transport details."""
        try:
            with response:
                if before_read is not None:
                    before_read(response)
                length = self._content_length(response)
                if length is not None and length > limit:
                    raise PlatformError(502, large_message)
                return response.read(limit + 1)
        except PlatformError:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise PlatformError(504, "FCode response timed out") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise PlatformError(504, "FCode response timed out") from exc
            raise PlatformError(502, "FCode response failed") from exc
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise PlatformError(502, "FCode response failed") from exc

    @staticmethod
    def _content_length(response: Any) -> int | None:
        headers = getattr(response, "headers", None)
        raw = headers.get("Content-Length") if headers is not None else None
        if raw is None:
            return None
        try:
            length = int(raw)
        except (TypeError, ValueError):
            return None
        return max(0, length)

    @staticmethod
    def _validate_signed_url(url: Any) -> None:
        if not isinstance(url, str):
            raise PlatformError(502, "FCode returned an invalid replay URL")
        try:
            split = urllib.parse.urlsplit(url)
            hostname = split.hostname.lower() if split.hostname else None
            port = split.port
        except ValueError as exc:
            raise PlatformError(502, "FCode returned an invalid replay URL") from exc
        if split.scheme != "https" or hostname not in _REPLAY_HOSTS:
            raise PlatformError(502, "FCode returned an invalid replay URL")
        if (
            split.username is not None
            or split.password is not None
            or port not in {None, 443}
        ):
            raise PlatformError(502, "FCode returned an invalid replay URL")

    # -- caches and request coalescing ---------------------------------

    def _cached_json(
        self, key: str, ttl: float, loader: Callable[[], Any]
    ) -> Any:
        cached = self._json_cache_get(key)
        if cached is not None:
            return cached

        def load_and_store() -> Any:
            value = loader()
            self._json_cache_put(key, value, ttl)
            return value

        return self._single_flight(key, load_and_store)

    def _json_cache_get(self, key: str) -> Any | None:
        now = self._clock()
        with self._lock:
            item = self._json_cache.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= now:
                del self._json_cache[key]
                return None
            self._json_cache.move_to_end(key)
            return value

    def _json_cache_put(self, key: str, value: Any, ttl: float) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._json_cache[key] = (self._clock() + ttl, value)
            self._json_cache.move_to_end(key)
            while len(self._json_cache) > _MAX_CACHE_ENTRIES:
                self._json_cache.popitem(last=False)

    def _replay_cache_get(self, key: str) -> bytes | None:
        with self._lock:
            body = self._replay_cache.get(key)
            if body is not None:
                self._replay_cache.move_to_end(key)
            return body

    def _replay_cache_put(self, key: str, body: bytes) -> None:
        if self._replay_cache_limit <= 0 or len(body) > self._replay_cache_limit:
            return
        with self._lock:
            old = self._replay_cache.pop(key, None)
            if old is not None:
                self._replay_cache_size -= len(old)
            self._replay_cache[key] = body
            self._replay_cache_size += len(body)
            while (
                self._replay_cache
                and self._replay_cache_size > self._replay_cache_limit
            ):
                _, evicted = self._replay_cache.popitem(last=False)
                self._replay_cache_size -= len(evicted)

    def _single_flight(self, key: str, loader: Callable[[], Any]) -> Any:
        with self._lock:
            flight = self._flights.get(key)
            owner = flight is None
            if flight is None:
                flight = _Flight()
                self._flights[key] = flight
        if owner:
            try:
                flight.value = loader()
            except BaseException as exc:
                flight.error = exc
            finally:
                with self._lock:
                    self._flights.pop(key, None)
                    flight.event.set()
        else:
            flight.event.wait()
        if flight.error is not None:
            raise flight.error
        return flight.value
