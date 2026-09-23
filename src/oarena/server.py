"""The oarena HTTP server: JSON API, SSE feed, dashboard and replay viewer.

Standard library only — :class:`http.server.ThreadingHTTPServer` with
``daemon_threads`` — because the dashboard is a local power tool, not a
deployment.  Exactly one :class:`~oarena.league.League`, :class:`~oarena.store.Store`
and :class:`~oarena.events.EventBus` are shared by every handler thread; the
league owns all DB writes that come out of a run, and the store's own lock covers
the reads the handlers do.

Four things are less obvious than the route table suggests:

* **/api/events is a real SSE stream.**  A client reconnects with the sequence
  number it last saw; the stream answers with ``hello``, replays the gap out of
  the bus ring buffer and only then switches to its live subscription, so no
  event can slip through the seam.  The bus lock is never held while writing to a
  socket — events are handed over through a bounded queue.
* **/viz/ serves the visualiser bundled with fcode.**  Its ``index.html``
  references ``/assets/...`` absolutely, so the three references are rewritten to
  ``/viz/assets/...`` on the way out.  Nothing else in the bundle is touched.
* **/square-viz/ serves oarena's vendored Square visualiser.**  It is packaged
  with oarena and therefore remains available when the installed ``fcode`` has
  no visualiser data directory.
* **Replays are ~500 KB.**  They are streamed with a real ``Content-Length``
  rather than buffered, which also lets the visualiser show a progress bar.

The server binds ``127.0.0.1`` and has no authentication; that is deliberate and
the startup banner says so.
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import ipaddress
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from collections.abc import Callable, Sequence
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from oarena import __version__, bots, config, maps, reporting
from oarena.bots import BotError, discover_names
from oarena.config import Config, ConfigError
from oarena.events import Event, EventBus
from oarena.fcode_platform import FcodePlatform, PlatformError
from oarena.league import MAX_GAME_SEED, MIN_GAME_SEED, League
from oarena.maps import MapError
from oarena.platform_history import PlatformVersionHistory
from oarena.platform_rpc import SOCKET_ENV, UnixPlatformClient
from oarena.platform_scrims import ScrimCoordinator
from oarena.ratings import Rater
from oarena.store import Bot, Store, StoreBusyError

__all__ = ["App", "Handler", "HttpError", "Server", "make_server", "serve"]

# --------------------------------------------------------------------------- #
# tunables
# --------------------------------------------------------------------------- #

HEARTBEAT_S = 15.0
"""Seconds of silence after which the SSE stream writes a ``: ping`` comment."""

SSE_TICK_S = 1.0
"""How often the SSE loop wakes up to check for heartbeats and disconnects."""

SSE_RETRY_MS = 3000
"""Reconnect delay advertised to EventSource clients."""

MAX_BODY = 1 << 20
"""Largest accepted request body (1 MiB); every real POST here is tiny."""

LOG_TAIL_CHARS = 4000
"""How much of a game's captured stderr ``/api/games/<id>`` inlines."""

DEFAULT_GAME_LIMIT = 100
MAX_GAME_LIMIT = 500

MAX_SCRIM_MAPS = 5
MAX_SCRIM_TARGETS = 100
MAX_PLATFORM_NAME_CHARS = 200

_SCRIM_MUTATION_PATHS = frozenset(
    {
        "/api/platform/scrims",
        "/api/platform/scrims/autoscrim",
        "/api/platform/scrims/refresh",
    }
)
_TRUSTED_HOSTS_ENV = "OARENA_TRUSTED_HOSTS"

_JSON_GZIP_MIN_BYTES = 1024
"""Small JSON responses cost more to compress than they save on the wire."""

_CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".wasm": "application/wasm",
}

_STATIC_SUFFIXES = frozenset(
    {".css", ".js", ".mjs", ".html", ".json", ".map", ".svg", ".png", ".webp",
     ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".txt"}
)

_IMMUTABLE = "public, max-age=31536000, immutable"
_PRIVATE_IMMUTABLE = "private, max-age=31536000, immutable"
_NO_STORE = "no-store"

_SQUARE_SPRITE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
_SQUARE_GZIP_SUFFIXES = frozenset(
    {".css", ".html", ".js", ".json", ".map", ".mjs", ".svg", ".txt"}
)
_WEB_REVISION_SUFFIXES = frozenset({".css", ".html", ".js", ".mjs"})

_RE_GAME = re.compile(r"/games/(\d+)(?:/(replay|log))?")
_RE_BOT = re.compile(r"/bots/([^/]+)")
_RE_BOT_ACTION = re.compile(r"/bots/([^/]+)/(active|note)")
_RE_MAP_FILE = re.compile(r"/maps/([^/]+)/file")

_CANONICAL_UUID_RE = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
_RE_PLATFORM_MATCH = re.compile(rf"/platform/matches/({_CANONICAL_UUID_RE})")
_RE_PLATFORM_REPLAY = re.compile(
    rf"/platform/matches/({_CANONICAL_UUID_RE})/games/([1-5])/replay"
)

_ARENA_KINDS = ("ladder", "top", "vs", "rr")


class HttpError(Exception):
    """An error that maps straight onto a JSON response with a status code."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# application state
# --------------------------------------------------------------------------- #


def _web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"


def _web_revision(root: Path) -> str:
    """Stable fingerprint of browser code that requires a page reload."""
    digest = hashlib.sha256()
    for path in sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in _WEB_REVISION_SUFFIXES
    ):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(128 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _square_visualiser_dir() -> Path:
    return Path(__file__).resolve().parent / "square_visualiser"


@dataclasses.dataclass(frozen=True)
class _SquareVisualiserRevisions:
    """Independent immutable namespaces for viewer code and large sprites."""

    legacy: str
    code: str
    sprites: str


def _square_visualiser_asset_kind(root: Path, path: Path) -> str | None:
    """Return the split namespace for one browser-servable Square file.

    Phaser's Square sprite set is deliberately flat. Keeping that constraint in
    the server means a code URL can never accidentally become a second long-
    lived alias for a sprite (or vice versa).
    """
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    suffix = path.suffix.lower()
    if suffix not in _STATIC_SUFFIXES:
        return None
    # The entry document is rewritten per request and is never served from an
    # immutable namespace, so editing it must not evict the code bundle.
    if relative == Path("index.html"):
        return None
    if suffix in _SQUARE_SPRITE_SUFFIXES:
        return "sprites" if len(relative.parts) == 1 else None
    return "code"


@lru_cache(maxsize=4)
def _square_visualiser_revisions(root: Path) -> _SquareVisualiserRevisions:
    """Fingerprint all Square assets once, retaining independent namespaces.

    ``legacy`` preserves the original combined ``_assets`` route for an iframe
    that was already open during an oarena upgrade. New entry documents use
    only ``code`` and ``sprites``: editing JavaScript therefore cannot evict
    roughly 7.5 MiB of unchanged artwork from the browser cache.
    """
    digests = {
        "legacy": hashlib.sha256(),
        "code": hashlib.sha256(),
        "sprites": hashlib.sha256(),
    }
    for path in sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in _STATIC_SUFFIXES
    ):
        kind = _square_visualiser_asset_kind(root, path)
        selected = [digests["legacy"]]
        if kind is not None:
            selected.append(digests[kind])
        relative = path.relative_to(root).as_posix().encode("utf-8")
        for digest in selected:
            digest.update(relative)
            digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(128 * 1024):
                for digest in selected:
                    digest.update(chunk)
        for digest in selected:
            digest.update(b"\0")
    return _SquareVisualiserRevisions(
        legacy=digests["legacy"].hexdigest()[:16],
        code=digests["code"].hexdigest()[:16],
        sprites=digests["sprites"].hexdigest()[:16],
    )


def _square_visualiser_revision(root: Path) -> str:
    """Backward-compatible accessor for the original combined revision."""
    return _square_visualiser_revisions(root).legacy


@lru_cache(maxsize=24)
def _gzip_file_bytes(path: Path, mtime_ns: int, size: int) -> bytes:
    """A deterministic in-memory gzip variant keyed by the file's stat data."""
    del mtime_ns, size  # They intentionally participate in the cache key.
    return gzip.compress(path.read_bytes(), compresslevel=6, mtime=0)


def _accepts_gzip(value: str | None) -> bool:
    """Whether an HTTP Accept-Encoding value permits a gzip representation."""
    if not value:
        return False
    wildcard: float | None = None
    gzip_quality: float | None = None
    for item in value.split(","):
        parts = [part.strip() for part in item.split(";")]
        coding = parts[0].lower()
        if not coding:
            continue
        quality = 1.0
        for parameter in parts[1:]:
            name, separator, raw = parameter.partition("=")
            if separator and name.strip().lower() == "q":
                try:
                    quality = float(raw.strip())
                except ValueError:
                    quality = 0.0
        if not 0.0 <= quality <= 1.0:
            quality = 0.0
        if coding == "gzip":
            gzip_quality = quality
        elif coding == "*":
            wildcard = quality
    return (gzip_quality if gzip_quality is not None else wildcard or 0.0) > 0


class App:
    """Everything the handlers share. One instance per server."""

    def __init__(
        self,
        cfg: Config,
        store: Store,
        bus: EventBus,
        league: League,
        rater: Rater,
        *,
        web_dir: Path | None = None,
        platform_client: FcodePlatform | UnixPlatformClient | None = None,
        scrim_coordinator: ScrimCoordinator | None = None,
        platform_history: PlatformVersionHistory | None = None,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.league = league
        self.rater = rater
        self.instance_id = uuid.uuid4().hex
        if platform_client is not None:
            self.platform = platform_client
        elif SOCKET_ENV in os.environ:
            # A hardened service cannot read ~/.fcode or reach the Internet.
            # Only its narrow read-only sidecar gets those privileges.
            self.platform = UnixPlatformClient(os.environ[SOCKET_ENV])
        else:
            self.platform = FcodePlatform()
        self.web_dir = Path(web_dir) if web_dir is not None else _web_dir()
        self.web_revision = _web_revision(self.web_dir)
        self.square_visualiser_dir = _square_visualiser_dir()
        square_revisions = _square_visualiser_revisions(self.square_visualiser_dir)
        self.square_visualiser_revision = square_revisions.legacy
        self.square_visualiser_code_revision = square_revisions.code
        self.square_visualiser_sprite_revision = square_revisions.sprites
        self._viz_dir: Path | None = None
        try:
            self.fcode_version: str | None = config.check_fcode()
        except RuntimeError:
            self.fcode_version = None
        self.scrims = (
            scrim_coordinator
            if scrim_coordinator is not None
            else ScrimCoordinator(
                cfg.state_dir / "platform-scrims.db",
                self.platform,
                bus=bus,
            )
        )
        self.platform_history = (
            platform_history
            if platform_history is not None
            else PlatformVersionHistory(
                cfg.state_dir / "platform-history.db",
                self.platform,
            )
        )

    @property
    def viz_dir(self) -> Path | None:
        """The bundled visualiser, looked up lazily and cached once it is found.

        Resolving it needs ``import fcode``; retrying until that works means a
        hiccup at startup does not disable the replay viewer for the whole
        session.
        """
        if self._viz_dir is None:
            self._viz_dir = config.visualiser_dist()
        return self._viz_dir

    @classmethod
    def create(cls, cfg: Config, *, workers: int | None = None) -> App:
        """Build the whole stack from a config, overriding the worker count."""
        if workers:
            cfg = dataclasses.replace(cfg, workers=int(workers))
        config.ensure_dirs(cfg)
        if not cfg.owns_state_dir:
            owner_path = cfg.state_dir.parent / config.CONFIG_NAME
            if owner_path.is_file():
                owner = config.from_file(owner_path)
                if owner.trueskill != cfg.trueskill:
                    raise ConfigError(
                        f"shared state {cfg.state_dir} belongs to a project with "
                        "different TrueSkill settings"
                    )
        store = Store(cfg.db_path)
        bus = EventBus()
        rater = Rater(cfg.trueskill)
        try:
            store.ensure_rating_config(cfg.trueskill)
            league = League(cfg, store, bus, rater)
            return cls(cfg, store, bus, league, rater)
        except BaseException:
            store.close()
            raise

    def close(self) -> None:
        """Abort an active run, reap its workers, then close the database.

        Closing the dashboard is an explicit end to a local arena session.  It
        must not leave a handful of engine processes finishing games after the
        server has disappeared (or race those workers against a closed SQLite
        connection), so shutdown uses the same immediate cancellation path as
        the dashboard's Force stop action.
        """
        # Both platform helpers own a small database and may currently be
        # waiting on the credentialed sidecar. Stop their workers before any
        # application database is closed.
        try:
            self.platform_history.close()
        except Exception:  # pragma: no cover - shutdown remains best-effort
            pass
        try:
            self.scrims.close()
        except Exception:  # pragma: no cover - shutdown remains best-effort
            pass

        reaped = False
        try:
            # A reload is a source-version boundary, not a played game. Do not
            # clutter history with workers killed solely by server shutdown.
            self.league.force_stop(discard_cancelled=True)
        except Exception:  # pragma: no cover - shutdown must preserve the real error
            pass
        while not reaped:
            try:
                reaped = self.league.wait(timeout=0.25)
            except KeyboardInterrupt:
                # A second interrupt reasserts cancellation without allowing a
                # live league thread to race a closed SQLite connection.
                try:
                    self.league.force_stop()
                except Exception:  # pragma: no cover
                    pass
            except Exception:  # pragma: no cover - leave the store open if reaping failed
                return
        try:
            self.store.close()
        except Exception:  # pragma: no cover
            pass

    def config_json(self) -> dict[str, Any]:
        """The slice of the config the dashboard displays."""
        cfg = self.cfg
        return {
            "name": cfg.root.name,
            "root": str(cfg.root),
            "bots_dir": str(cfg.bots_dir),
            "maps_dir": str(cfg.maps_dir),
            "extra_maps_dir": str(cfg.extra_maps_dir),
            "workers": cfg.n_workers,
            "tle_ms": cfg.tle_ms,
            "game_timeout_s": cfg.game_timeout_s,
            "maps": list(cfg.maps),
            "mirror": cfg.mirror,
            "seed_policy": cfg.seed_policy,
            "seed": cfg.seed,
            # JSON numbers lose integer precision in browsers above 2**53 - 1.
            # Keep the numeric field for API compatibility and expose an exact
            # decimal for controls that must reproduce a configured seed.
            "seed_exact": str(cfg.seed),
            "coinflip_is_draw": cfg.coinflip_is_draw,
            "replay_budget_mb": cfg.replay_budget_mb,
            "sigma_reinflate": cfg.sigma_reinflate,
            "ui_theme": cfg.ui_theme,
            "version": __version__,
            "visualiser": self.viz_dir is not None,
        }

    def maps_json(self) -> list[dict[str, Any]]:
        """Every map with its tiles (base64) and how often it has been played."""
        return reporting.maps_json(
            self.store,
            maps.discover(self.cfg.maps_dir, self.cfg.extra_maps_dir),
        )

    def ladder_json(self, rows: Sequence[reporting.LadderRow]) -> list[dict[str, Any]]:
        """Ladder rows annotated against this project's current bot catalog."""
        present = set(discover_names(self.cfg.bots_dir))
        payload = reporting.ladder_json(rows)
        for row in payload:
            row["source_present"] = row["name"] in present
        return payload

    def storage_json(self) -> dict[str, Any]:
        """Disk use for the dashboard's space-management view."""
        cfg = self.cfg
        replay_files = self.store.replay_files()
        return {
            "replays": {
                "bytes": _directory_size(cfg.replay_dir),
                "files": _file_count(cfg.replay_dir),
                "retained": len(replay_files),
                "budget_bytes": cfg.replay_budget_bytes,
                "budget_mb": cfg.replay_budget_mb,
            },
            "logs": {"bytes": _directory_size(cfg.log_dir), "files": _file_count(cfg.log_dir)},
            "temporary": {"bytes": _directory_size(cfg.tmp_dir), "files": _file_count(cfg.tmp_dir)},
            "database": {"bytes": _path_size(cfg.db_path)},
        }


# --------------------------------------------------------------------------- #
# small parsing helpers
# --------------------------------------------------------------------------- #

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}


def _path_size(path: Path) -> int:
    try:
        return max(0, path.stat().st_size)
    except OSError:
        return 0


def _directory_size(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(_path_size(path) for path in directory.rglob("*") if path.is_file())


def _file_count(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.rglob("*") if path.is_file())


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if values is not None and len(values) > 1:
        raise HttpError(400, f"{key!r} may only be provided once")
    return values[0] if values else None


def _qs_int(query: dict[str, list[str]], key: str, default: int) -> int:
    raw = _one(query, key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise HttpError(400, f"{key!r} must be an integer, got {raw!r}") from exc


def _qs_bool(query: dict[str, list[str]], key: str, default: bool = False) -> bool:
    raw = _one(query, key)
    if raw is None:
        return default
    text = raw.strip().lower()
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    raise HttpError(400, f"{key!r} must be a boolean, got {raw!r}")


def _qs_str(query: dict[str, list[str]], key: str) -> str | None:
    raw = _one(query, key)
    text = (raw or "").strip()
    return text or None


def _only_query(query: dict[str, list[str]], allowed: set[str]) -> None:
    """Reject misspelled platform parameters instead of silently widening a query."""
    unknown = sorted(set(query) - allowed)
    if unknown:
        rendered = ", ".join(repr(key) for key in unknown)
        raise HttpError(400, f"unsupported query parameter(s): {rendered}")


def _unavailable_version_tracking() -> dict[str, Any]:
    return {
        "started": False,
        "syncing": False,
        "refreshing": False,
        "due": False,
        "initialized": False,
        "initial_sync_complete": False,
        "last_sync_at": None,
        "last_attempt_at": None,
        "next_refresh_at": None,
        "last_error": "Version tracking is unavailable",
        "error": "Version tracking is unavailable",
    }


def _only_body(
    payload: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str] | None = None,
) -> None:
    """Require an exact, deliberately small JSON request shape."""

    unknown = sorted(set(payload) - allowed)
    if unknown:
        rendered = ", ".join(repr(key) for key in unknown)
        raise HttpError(400, f"unsupported request field(s): {rendered}")
    missing = sorted((required or set()) - set(payload))
    if missing:
        rendered = ", ".join(repr(key) for key in missing)
        raise HttpError(400, f"missing request field(s): {rendered}")


def _http_authority(value: str) -> tuple[str, int | None] | None:
    """Parse a Host-style authority without accepting URL syntax or controls."""

    if not value or value != value.strip():
        return None
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return None
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return None
    parsed = urlsplit(f"//{value}")
    if (
        not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.hostname is None
        or parsed.netloc.endswith(":")
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname.rstrip(".").lower()
    return (hostname, port) if hostname else None


def _trusted_mutation_host(hostname: str, port: int | None) -> bool:
    """Allow non-rebindable local/Tailscale hosts and explicit proxy hosts."""

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        # Literal addresses cannot be swapped by DNS rebinding. Oarena still
        # warns against binding its unauthenticated server to a network.
        return True

    local_names = {
        name.rstrip(".").lower()
        for name in (socket.gethostname(), socket.getfqdn())
        if name
    }
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname in local_names
        or hostname.endswith(".ts.net")
    ):
        return True

    for configured in os.environ.get(_TRUSTED_HOSTS_ENV, "").split(","):
        authority = _http_authority(configured.strip())
        if authority is None:
            continue
        configured_host, configured_port = authority
        if hostname == configured_host and (
            configured_port is None or configured_port == port
        ):
            return True
    return False


def _bounded_text(
    value: Any,
    name: str,
    *,
    limit: int,
    optional: bool = False,
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise HttpError(400, f"{name!r} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HttpError(400, f"{name!r} must be valid UTF-8 text") from exc
    if any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value):
        raise HttpError(400, f"{name!r} contains unsupported control characters")
    text = value.strip()
    if not text or len(text) > limit:
        raise HttpError(400, f"{name!r} must contain 1 to {limit} characters")
    return text


def _body_uuid(
    payload: dict[str, Any], key: str, *, optional: bool = False
) -> str | None:
    if key not in payload or payload[key] is None:
        if optional:
            return None
        raise HttpError(400, f"{key!r} is required")
    value = payload[key]
    if not isinstance(value, str):
        raise HttpError(400, f"{key!r} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise HttpError(400, f"{key!r} must be a canonical UUID") from exc
    if value != str(parsed):
        raise HttpError(400, f"{key!r} must be a canonical UUID")
    return value


def _body_map_names(payload: dict[str, Any]) -> tuple[str, ...]:
    if "map_names" not in payload or payload["map_names"] is None:
        return ()
    raw = payload["map_names"]
    if not isinstance(raw, list):
        raise HttpError(400, "'map_names' must be a list of strings")
    if len(raw) > MAX_SCRIM_MAPS:
        raise HttpError(400, f"'map_names' may contain at most {MAX_SCRIM_MAPS} maps")
    names: list[str] = []
    for value in raw:
        name = _bounded_text(
            value,
            "map_names",
            limit=MAX_PLATFORM_NAME_CHARS,
        )
        assert name is not None
        if name in names:
            raise HttpError(400, "'map_names' must not contain duplicates")
        names.append(name)
    return tuple(names)


def _body_target_ids(payload: dict[str, Any]) -> tuple[str, ...]:
    if "target_team_ids" not in payload or payload["target_team_ids"] is None:
        return ()
    raw = payload["target_team_ids"]
    if not isinstance(raw, list):
        raise HttpError(400, "'target_team_ids' must be a list of canonical UUIDs")
    if len(raw) > MAX_SCRIM_TARGETS:
        raise HttpError(
            400,
            f"'target_team_ids' may contain at most {MAX_SCRIM_TARGETS} teams",
        )
    target_ids: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            raise HttpError(400, "'target_team_ids' must contain canonical UUIDs")
        try:
            parsed = uuid.UUID(value)
        except ValueError as exc:
            raise HttpError(
                400, "'target_team_ids' must contain canonical UUIDs"
            ) from exc
        if value != str(parsed):
            raise HttpError(400, "'target_team_ids' must contain canonical UUIDs")
        if value in target_ids:
            raise HttpError(400, "'target_team_ids' must not contain duplicates")
        target_ids.append(value)
    return tuple(target_ids)


def _body_target_names(
    payload: dict[str, Any], target_ids: tuple[str, ...]
) -> dict[str, str] | None:
    raw = payload.get("target_team_names")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HttpError(400, "'target_team_names' must be an object keyed by team ID")
    if len(raw) > MAX_SCRIM_TARGETS:
        raise HttpError(
            400,
            f"'target_team_names' may contain at most {MAX_SCRIM_TARGETS} teams",
        )
    target_set = set(target_ids)
    names: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):  # JSON itself guarantees this, for direct tests.
            raise HttpError(400, "'target_team_names' keys must be canonical UUIDs")
        try:
            parsed = uuid.UUID(key)
        except ValueError as exc:
            raise HttpError(
                400, "'target_team_names' keys must be canonical UUIDs"
            ) from exc
        if key != str(parsed) or key not in target_set:
            raise HttpError(
                400,
                "'target_team_names' keys must name selected target_team_ids",
            )
        name = _bounded_text(
            value,
            "target_team_names",
            limit=MAX_PLATFORM_NAME_CHARS,
        )
        assert name is not None
        names[key] = name
    return names


def _body_bounded_int(
    payload: dict[str, Any], key: str, default: int, *, low: int, high: int
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HttpError(400, f"{key!r} must be an integer")
    if not low <= value <= high:
        raise HttpError(400, f"{key!r} must be between {low} and {high}")
    return value


def _qs_bounded_int(
    query: dict[str, list[str]], key: str, default: int, *, low: int, high: int
) -> int:
    value = _qs_int(query, key, default)
    if not low <= value <= high:
        raise HttpError(400, f"{key!r} must be between {low} and {high}")
    return value


def _scrim_validation_error(exc: ValueError) -> HttpError:
    """Turn coordinator input rejection into a bounded browser-safe 400."""

    text = str(exc).strip()
    if (
        not text
        or len(text) > 300
        or any(ord(char) < 0x20 and char not in "\t" for char in text)
    ):
        text = "invalid scrim request"
    return HttpError(400, text)


def _qs_uuid(query: dict[str, list[str]], key: str) -> str | None:
    text = _qs_str(query, key)
    if text is None:
        return None
    try:
        parsed = uuid.UUID(text)
    except ValueError as exc:
        raise HttpError(400, f"{key!r} must be a canonical UUID") from exc
    if text != str(parsed):
        raise HttpError(400, f"{key!r} must be a canonical UUID")
    return text


def _body_bool(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
    raise HttpError(400, f"{key!r} must be true or false, got {value!r}")


def _parsed_body_int(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise HttpError(400, f"{key!r} must be an integer, got {value!r}")
    try:
        return int(value)
    except ValueError as exc:
        raise HttpError(400, f"{key!r} must be an integer, got {value!r}") from exc


def _body_int(payload: dict[str, Any], key: str, default: int, *, minimum: int = 0) -> int:
    value = payload.get(key, default)
    if value is None:
        return default
    number = _parsed_body_int(value, key)
    return max(minimum, number)


def _body_seed(payload: dict[str, Any], key: str) -> int:
    number = _parsed_body_int(payload.get(key), key)
    if not MIN_GAME_SEED <= number <= MAX_GAME_SEED:
        raise HttpError(
            400,
            f"{key!r} must be between {MIN_GAME_SEED} and {MAX_GAME_SEED}",
        )
    return number


def _body_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise HttpError(400, f"{key!r} must be a string, got {value!r}")
    return value.strip()


def _body_names(payload: dict[str, Any], key: str) -> list[str] | None:
    """A list-of-strings field; ``None`` when absent or empty (meaning "default")."""
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise HttpError(400, f"{key!r} must be a list of strings")
    names = [v.strip() for v in value if v.strip()]
    return names or None


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _safe_join(base: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``base``, refusing anything that escapes it."""
    cleaned = relative.lstrip("/")
    if not cleaned or "\x00" in cleaned:
        return None
    try:
        root = base.resolve()
        target = (root / cleaned).resolve()
    except OSError:
        return None
    if target != root and root not in target.parents:
        return None
    return target


def _tail(path: Path, limit: int = LOG_TAIL_CHARS) -> str:
    """The last ``limit`` characters of a text file, or ``""`` if unreadable."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > limit * 4:
                handle.seek(size - limit * 4)
            raw = handle.read()
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")[-limit:]


# --------------------------------------------------------------------------- #
# request handler
# --------------------------------------------------------------------------- #


class Handler(BaseHTTPRequestHandler):
    """One HTTP request. Thread-per-connection, so keep every handler re-entrant."""

    protocol_version = "HTTP/1.1"
    server_version = f"oarena/{__version__}"
    sys_version = ""

    _sent: bool = False
    """True once response headers are on the wire; guards the error path."""

    # BaseHTTPRequestHandler logs every request to stderr; the arena prints only
    # its banner and real failures.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def log_error(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    # -- verbs -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        self._request(self._get)

    def do_POST(self) -> None:  # noqa: N802
        self._request(self._post)

    def do_DELETE(self) -> None:  # noqa: N802
        self._request(self._delete)

    def _request(self, route: Callable[[str, dict[str, list[str]], dict[str, Any]], None]) -> None:
        """Parse the request line, dispatch, and turn failures into JSON."""
        self._sent = False
        split = urlsplit(self.path)
        try:
            path = unquote(split.path)
            query = parse_qs(split.query, keep_blank_values=True)
        except (UnicodeDecodeError, ValueError):
            self._fail(400, "malformed request URI")
            return
        try:
            if (
                self.command == "POST"
                and path.rstrip("/") in _SCRIM_MUTATION_PATHS
            ):
                self._require_scrim_mutation_headers()
            payload = {} if self.command == "GET" else self._read_body()
            route(path, query, payload)
        except HttpError as exc:
            self._fail(exc.code, exc.message)
        except PlatformError as exc:
            self._fail(exc.code, exc.message)
        except (BotError, MapError, ConfigError) as exc:
            self._fail(400, str(exc))
        except StoreBusyError as exc:
            self._fail(409, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as exc:  # a bug in oarena, not in the request
            traceback.print_exc()
            self._fail(500, f"{type(exc).__name__}: {exc}")

    def _require_scrim_mutation_headers(self) -> None:
        """Reject browser cross-site/rebinding writes before reading their body."""

        def reject(code: int, message: str) -> None:
            # The body has deliberately not been consumed, so this connection
            # cannot safely carry another HTTP request after the error response.
            self.close_connection = True
            raise HttpError(code, message)

        content_types = self.headers.get_all("Content-Type", failobj=[])
        if len(content_types) != 1:
            reject(415, "scrim mutations require Content-Type: application/json")
        media_type = content_types[0].split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            reject(415, "scrim mutations require Content-Type: application/json")

        hosts = self.headers.get_all("Host", failobj=[])
        if len(hosts) != 1:
            reject(403, "forbidden request origin")
        authority = _http_authority(hosts[0])
        if authority is None or not _trusted_mutation_host(*authority):
            reject(403, "forbidden request origin")
        hostname, host_port = authority

        forwarded = self.headers.get_all("X-Forwarded-Proto", failobj=[])
        if len(forwarded) > 1:
            reject(403, "forbidden request origin")
        scheme = forwarded[0].strip().lower() if forwarded else "http"
        if scheme not in {"http", "https"}:
            reject(403, "forbidden request origin")

        origins = self.headers.get_all("Origin", failobj=[])
        if len(origins) != 1:
            reject(403, "forbidden request origin")
        try:
            origin = urlsplit(origins[0])
            origin_port = origin.port
        except ValueError:
            reject(403, "forbidden request origin")
        if (
            origin.scheme.lower() != scheme
            or origin.username is not None
            or origin.password is not None
            or origin.hostname is None
            or origin.path
            or origin.query
            or origin.fragment
        ):
            reject(403, "forbidden request origin")
        origin_hostname = origin.hostname.rstrip(".").lower()
        default_port = 443 if scheme == "https" else 80
        effective_origin_port = (
            origin_port if origin_port is not None else default_port
        )
        effective_host_port = host_port if host_port is not None else default_port
        if (
            origin_hostname != hostname
            or effective_origin_port != effective_host_port
        ):
            reject(403, "forbidden request origin")

    def _read_body(self) -> dict[str, Any]:
        """Read and JSON-decode the request body; an empty body is ``{}``."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            self.close_connection = True
            raise HttpError(400, "invalid Content-Length") from exc
        if length <= 0:
            return {}
        if length > MAX_BODY:
            self.close_connection = True
            raise HttpError(400, f"request body too large ({length} bytes)")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(400, f"invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise HttpError(400, "body must be a JSON object")
        return data

    # -- responses ---------------------------------------------------------

    def _send(
        self,
        code: int,
        body: bytes,
        content_type: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._sent = True
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if code != 204:  # a 204 must not carry Content-Length
            self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        body = json.dumps(obj, default=str).encode("utf-8")
        headers = {"Cache-Control": _NO_STORE}
        if len(body) >= _JSON_GZIP_MIN_BYTES:
            # An identity response still varies by Accept-Encoding: another
            # request for this URL may receive gzip.  Small responses have no
            # compressed representation and therefore need no Vary header.
            headers["Vary"] = "Accept-Encoding"
            if _accepts_gzip(self.headers.get("Accept-Encoding")):
                body = gzip.compress(body, compresslevel=6, mtime=0)
                headers["Content-Encoding"] = "gzip"
        self._send(code, body, "application/json; charset=utf-8", headers=headers)

    def _fail(self, code: int, message: str) -> None:
        """Emit ``{"error": ...}``, unless a response is already on the wire."""
        if self._sent:
            self.close_connection = True
            return
        try:
            self._json({"error": message}, code=code)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _redirect(self, location: str) -> None:
        self._send(301, b"", "text/plain; charset=utf-8", headers={"Location": location})

    def _send_file(
        self,
        path: Path,
        content_type: str,
        cache: str = _NO_STORE,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Stream a file with a real Content-Length; never reads it twice."""
        try:
            handle = path.open("rb")
        except OSError as exc:
            raise HttpError(404, f"cannot read {path.name}: {exc}") from exc
        with handle:
            try:
                size = os.fstat(handle.fileno()).st_size
            except OSError:  # pragma: no cover - exotic filesystems
                size = path.stat().st_size
            self._sent = True
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", cache)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            shutil.copyfileobj(handle, self.wfile, 64 * 1024)

    def _send_square_body(
        self,
        body: bytes,
        content_type: str,
        *,
        cache: str,
    ) -> None:
        """Send generated Square text with an explicitly negotiated variant."""
        headers = {"Cache-Control": cache, "Vary": "Accept-Encoding"}
        if _accepts_gzip(self.headers.get("Accept-Encoding")):
            body = gzip.compress(body, compresslevel=6, mtime=0)
            headers["Content-Encoding"] = "gzip"
        self._send(200, body, content_type, headers=headers)

    def _send_square_file(self, path: Path, *, cache: str) -> None:
        """Serve one Square asset, gzip-compressing only textual formats."""
        content_type = _content_type(path)
        if path.suffix.lower() not in _SQUARE_GZIP_SUFFIXES:
            self._send_file(path, content_type, cache=cache)
            return

        if not _accepts_gzip(self.headers.get("Accept-Encoding")):
            self._send_file(
                path,
                content_type,
                cache=cache,
                headers={"Vary": "Accept-Encoding"},
            )
            return

        try:
            stat = path.stat()
            body = _gzip_file_bytes(path, stat.st_mtime_ns, stat.st_size)
        except OSError as exc:
            raise HttpError(404, f"cannot read {path.name}: {exc}") from exc
        self._send(
            200,
            body,
            content_type,
            headers={
                "Cache-Control": cache,
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
            },
        )

    # -- GET ---------------------------------------------------------------

    def _get(self, path: str, query: dict[str, list[str]], _payload: dict[str, Any]) -> None:
        if path in ("/", "/index.html"):
            return self._index()
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/square-viz":
            return self._redirect("/square-viz/")
        if path.startswith("/square-viz/"):
            return self._square_viz(path[len("/square-viz/"):])
        if path == "/map-editor":
            return self._redirect("/map-editor/")
        if path.startswith("/map-editor/"):
            return self._map_editor(path[len("/map-editor/"):], query)
        if path == "/viz":
            return self._redirect("/viz/")
        if path.startswith("/viz/"):
            return self._viz(path[len("/viz/"):], query)
        if path.startswith("/fonts/"):
            # The visualiser honours assetBaseUrl for its sprites but requests its
            # webfonts from the site root regardless, so the bundle has to be
            # reachable there too or every label falls back to a system face.
            return self._viz(path.lstrip("/"), query)
        if path == "/favicon.ico":
            return self._favicon()
        if not path.startswith("/api/"):
            raise HttpError(404, f"no such path: {path}")

        route = path[len("/api"):].rstrip("/") or "/"
        if route == "/platform/session":
            return self._api_platform_session(query)
        if route == "/platform/matches":
            return self._api_platform_matches(query)
        if route == "/platform/ladder":
            return self._api_platform_ladder(query)
        if route == "/platform/version-history":
            return self._api_platform_version_history(query)
        if route == "/platform/version-history/games":
            return self._api_platform_version_run_games(query)
        if route == "/platform/version-history/match":
            return self._api_platform_version_match_runs(query)
        if route == "/platform/version-tracking":
            return self._api_platform_version_tracking(query)
        if route == "/platform/test-runs":
            return self._api_platform_test_runs(query)
        if route == "/platform/scrims":
            return self._api_platform_scrims(query)
        if route == "/platform/teams":
            return self._api_platform_teams(query)
        if route == "/platform/maps":
            return self._api_platform_maps(query)

        platform_replay = _RE_PLATFORM_REPLAY.fullmatch(route)
        if platform_replay is not None:
            return self._api_platform_replay(
                platform_replay.group(1), int(platform_replay.group(2)), query
            )

        platform_match = _RE_PLATFORM_MATCH.fullmatch(route)
        if platform_match is not None:
            return self._api_platform_match(platform_match.group(1), query)

        if route == "/state":
            return self._api_state()
        if route == "/fcode-metadata":
            try:
                return self._json(config.fcode_metadata())
            except RuntimeError as exc:
                raise HttpError(503, f"fcode metadata unavailable: {exc}") from exc
        if route == "/ladder":
            return self._api_ladder(query)
        if route == "/matrix":
            return self._api_matrix(query)
        if route == "/pair-matrix":
            return self._api_pair_matrix(query)
        if route == "/timeline":
            return self._api_timeline(query)
        if route == "/storage":
            return self._json(self.app.storage_json())
        if route == "/maps":
            return self._json(self.app.maps_json())
        if route == "/batch":
            return self._api_batch(query)
        if route == "/games":
            return self._api_games(query)
        if route == "/events":
            return self._api_events(query)

        map_file = _RE_MAP_FILE.fullmatch(route)
        if map_file is not None:
            return self._api_map_file(map_file.group(1))

        game = _RE_GAME.fullmatch(route)
        if game is not None:
            gid, kind = int(game.group(1)), game.group(2)
            if kind == "replay":
                return self._api_replay(gid)
            if kind == "log":
                return self._api_log(gid)
            return self._api_game(gid)

        bot = _RE_BOT.fullmatch(route)
        if bot is not None:
            return self._api_bot(bot.group(1))

        raise HttpError(404, f"no such path: {path}")

    def _index(self) -> None:
        index = self.app.web_dir / "index.html"
        if not index.is_file():
            body = (
                b"<!doctype html><meta charset=utf-8><title>oarena</title>"
                b"<body style='font:14px ui-monospace,monospace;padding:2rem'>"
                b"<h1>oarena</h1><p>The dashboard files are missing from "
                b"<code>oarena/web/</code>. The JSON API at <code>/api/state</code> "
                b"still works.</p>"
            )
            self._send(503, body, "text/html; charset=utf-8",
                       headers={"Cache-Control": _NO_STORE})
            return
        # Stamp the project fallback into the response. A tiny inline script
        # applies this browser origin's saved preference before CSS loads.
        try:
            body = index.read_text(encoding="utf-8")
        except OSError as exc:
            raise HttpError(500, f"cannot read dashboard: {exc}") from exc
        body = body.replace(
            'data-theme="dark"', f'data-theme="{self.app.cfg.ui_theme}"', 1
        )
        body = body.replace(
            '<meta charset="utf-8">',
            '<meta charset="utf-8">\n'
            f'<meta name="oarena-web-revision" content="{self.app.web_revision}">',
            1,
        )
        self._send(
            200,
            body.encode("utf-8"),
            "text/html; charset=utf-8",
            headers={"Cache-Control": _NO_STORE},
        )

    def _favicon(self) -> None:
        for name in ("favicon.ico", "favicon.svg", "favicon.png"):
            candidate = self.app.web_dir / name
            if candidate.is_file():
                self._send_file(candidate, _content_type(candidate), cache="max-age=3600")
                return
        self._send(204, b"", "image/x-icon")

    def _static(self, relative: str) -> None:
        target = _safe_join(self.app.web_dir, relative)
        if target is None or target.suffix.lower() not in _STATIC_SUFFIXES:
            raise HttpError(404, f"no such file: {relative}")
        if not target.is_file():
            raise HttpError(404, f"no such file: {relative}")
        self._send_file(target, _content_type(target))

    def _square_viz(self, relative: str) -> None:
        """Serve the Square viewer with immutable, content-versioned assets."""
        dist = self.app.square_visualiser_dir
        legacy_prefix = f"_assets/{self.app.square_visualiser_revision}/"
        code_prefix = f"_code/{self.app.square_visualiser_code_revision}/"
        sprite_prefix = f"_sprites/{self.app.square_visualiser_sprite_revision}/"

        if relative in ("", "index.html"):
            index = dist / "index.html"
            try:
                body = index.read_text(encoding="utf-8")
            except OSError as exc:
                raise HttpError(404, f"cannot read {index.name}: {exc}") from exc
            code_browser_prefix = f"./{code_prefix}"
            sprite_browser_prefix = f"./{sprite_prefix}"
            body = body.replace(
                'src="./square-only.js"',
                f'src="{code_browser_prefix}square-only.js" '
                f'data-oarena-sprite-base="{sprite_browser_prefix}"',
            )
            body = body.replace('"./assets/', f'"{code_browser_prefix}assets/')
            self._send_square_body(
                body.encode("utf-8"),
                "text/html; charset=utf-8",
                cache=_NO_STORE,
            )
            return

        immutable = False
        namespace: str | None = None
        if relative.startswith("_assets/"):
            if not relative.startswith(legacy_prefix):
                raise HttpError(404, "stale Square visualiser asset revision")
            relative = relative[len(legacy_prefix):]
            immutable = True
        elif relative.startswith("_code/"):
            if not relative.startswith(code_prefix):
                raise HttpError(404, "stale Square visualiser code revision")
            relative = relative[len(code_prefix):]
            namespace = "code"
            immutable = True
        elif relative.startswith("_sprites/"):
            if not relative.startswith(sprite_prefix):
                raise HttpError(404, "stale Square visualiser sprite revision")
            relative = relative[len(sprite_prefix):]
            namespace = "sprites"
            immutable = True

        if immutable and not relative:
            raise HttpError(404, "no such Square visualiser file")

        target = _safe_join(dist, relative)
        if (
            target is None
            or target.suffix.lower() not in _STATIC_SUFFIXES
            or not target.is_file()
        ):
            raise HttpError(404, f"no such Square visualiser file: {relative}")
        if (
            namespace is not None
            and _square_visualiser_asset_kind(dist, target) != namespace
        ):
            raise HttpError(
                404, f"wrong Square visualiser asset namespace: {relative}"
            )
        self._send_square_file(target, cache=_IMMUTABLE if immutable else _NO_STORE)

    def _viz(self, relative: str, query: dict[str, list[str]]) -> None:
        """Serve the visualiser bundled with fcode, rewriting its absolute assets."""
        dist = self.app.viz_dir
        if dist is None:
            raise HttpError(
                503,
                "the fcode visualiser is not available — this fcode install ships "
                "no data/visualiser directory",
            )
        if relative in ("", "index.html"):
            target: Path | None = dist / "index.html"
        else:
            target = _safe_join(dist, relative)
        if target is None or not target.is_file():
            raise HttpError(404, f"no such visualiser file: {relative}")
        if target.suffix.lower() == ".html":
            html = target.read_text(encoding="utf-8", errors="replace")
            html = html.replace('"/assets/', '"/viz/assets/')
            html = html.replace("<title>Florent Code League Replay Viewer</title>", "<title>oarena replay</title>")
            # Phaser's map is pointer-native. Add one narrowly scoped keyboard
            # equivalent inside the iframe: it never listens on oarena's parent
            # document, and it only consumes modified arrows/Enter while the
            # canvas itself is focused. Native hover/selection remains the
            # source of tile/entity details and playback shortcuts are intact.
            keyboard_inspection = r"""
<style id="oarena-viz-keyboard-style">
#oarena-inspection-cursor {
  position: fixed; z-index: 2147483647; display: none; width: 14px; height: 14px;
  margin: -7px 0 0 -7px; border: 2px solid #ffbf40; border-radius: 50%;
  box-shadow: 0 0 0 2px #000, 0 0 8px #000; pointer-events: none;
}
#oarena-inspection-status {
  position: fixed; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
canvas[data-oarena-keyboard-map="true"]:focus-visible {
  outline: 3px solid #ffbf40; outline-offset: -3px;
}
</style>
<script id="oarena-viz-keyboard-inspection">
(() => {
  let activeCanvas = null;
  let cursor = null;
  let status = null;
  let cursorX = 0.5;
  let cursorY = 0.5;
  let announceTimer = 0;
  let announceFrame = 0;
  let announceToken = 0;
  let keyboardIntent = false;
  const installedCanvases = new WeakSet();

  // A click-focusable canvas must not jump the native mouse hover to the
  // keyboard cursor. Track modality independently of :focus-visible (which is
  // unavailable in some older browsers); the first bridge key also activates
  // the cursor, so keyboard inspection never depends on this heuristic alone.
  document.addEventListener("keydown", (event) => {
    if (event.isTrusted) keyboardIntent = true;
  }, true);
  const notePointerIntent = (event) => {
    if (!event.isTrusted) return;
    keyboardIntent = false;
    if (cursor) cursor.style.display = "none";
    cancelAnnouncement();
  };
  document.addEventListener("pointerdown", notePointerIntent, true);
  document.addEventListener("mousedown", notePointerIntent, true);
  document.addEventListener("touchstart", notePointerIntent, true);

  const exactText = (value) => [...document.querySelectorAll("[data-visualiser-root] *")]
    .find((node) => node.children.length === 0 && node.textContent.trim() === value);

  function cancelAnnouncement() {
    announceToken += 1;
    clearTimeout(announceTimer);
    announceTimer = 0;
    if (announceFrame) cancelAnimationFrame(announceFrame);
    announceFrame = 0;
  }

  function writeStatus(text, token) {
    if (!status || token !== announceToken) return;
    status.textContent = "";
    announceFrame = requestAnimationFrame(() => {
      announceFrame = 0;
      if (token === announceToken) status.textContent = text;
    });
  }

  function announce(labels, missingText = "Inspection details unavailable") {
    const candidates = Array.isArray(labels) ? labels : [labels];
    cancelAnnouncement();
    const token = announceToken;
    announceTimer = setTimeout(() => {
      announceTimer = 0;
      if (token !== announceToken) return;
      const matched = candidates
        .map((label) => ({ label, marker: exactText(label) }))
        .find((entry) => entry.marker);
      const marker = matched?.marker;
      const panel = marker?.closest("section") || marker?.parentElement?.parentElement;
      const details = (panel?.innerText || panel?.textContent || "")
        .replace(/\s+/g, " ").trim().slice(0, 1600);
      writeStatus(details || missingText, token);
    }, 80);
  }

  function announceNow(text) {
    cancelAnnouncement();
    writeStatus(text, announceToken);
  }

  function point(canvas) {
    const rect = canvas.getBoundingClientRect();
    return {
      rect,
      x: rect.left + rect.width * cursorX,
      y: rect.top + rect.height * cursorY,
    };
  }

  function place(canvas) {
    const { x, y } = point(canvas);
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  }

  function mouse(canvas, type, buttons) {
    const { x, y } = point(canvas);
    // Phaser 3 calls its scene-level inputs "pointer" events, but its browser
    // MouseManager consumes DOM mousemove/mousedown/mouseup events. Dispatch
    // that concrete family even in browsers which also expose PointerEvent.
    canvas.dispatchEvent(new MouseEvent(type, {
      bubbles: true, cancelable: true, clientX: x, clientY: y,
      button: 0, buttons,
    }));
  }

  function consume(event) {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }

  function focusLooksKeyboard(canvas) {
    if (keyboardIntent) return true;
    try {
      return canvas.matches(":focus-visible");
    } catch (_err) {
      return false;
    }
  }

  function isActive(canvas) {
    return Boolean(canvas && canvas === activeCanvas && canvas.isConnected);
  }

  function deactivate(canvas) {
    if (canvas !== activeCanvas) return;
    activeCanvas = null;
    if (cursor) cursor.style.display = "none";
    cancelAnnouncement();
  }

  function install() {
    const root = document.querySelector("[data-visualiser-root]") || document.getElementById("root");
    const canvas = root?.querySelector("canvas");
    if (activeCanvas && (activeCanvas !== canvas || !activeCanvas.isConnected)) {
      deactivate(activeCanvas);
    }
    if (!canvas || !canvas.isConnected || canvas === activeCanvas) return;
    activeCanvas = canvas;
    if (installedCanvases.has(canvas)) return;
    installedCanvases.add(canvas);
    canvas.dataset.oarenaKeyboardMap = "true";
    canvas.tabIndex = 0;
    canvas.setAttribute("role", "application");
    canvas.setAttribute(
      "aria-label",
      "Replay map. W A S D pans; Q and E zoom; Left and Right change turn; " +
      "Shift plus arrow moves the inspection cursor; Enter selects; Escape clears."
    );

    if (!cursor) {
      cursor = document.createElement("div");
      cursor.id = "oarena-inspection-cursor";
      cursor.setAttribute("aria-hidden", "true");
      document.body.append(cursor);
    }
    if (!status) {
      status = document.createElement("div");
      status.id = "oarena-inspection-status";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      status.setAttribute("aria-atomic", "true");
      document.body.append(status);
    }

    canvas.addEventListener("focus", () => {
      if (!isActive(canvas)) return;
      if (!focusLooksKeyboard(canvas)) return;
      cursor.style.display = "block";
      place(canvas);
      mouse(canvas, "mousemove", 0);
      announce("Hovered", "No tile under the inspection cursor");
    });
    canvas.addEventListener("blur", () => {
      if (!isActive(canvas)) return;
      cursor.style.display = "none";
      cancelAnnouncement();
    });
    canvas.addEventListener("mousemove", (event) => {
      if (isActive(canvas)) notePointerIntent(event);
    }, true);
    canvas.addEventListener("keydown", (event) => {
      if (!isActive(canvas)) return;
      const directions = {
        ArrowLeft: [-1, 0], ArrowRight: [1, 0],
        ArrowUp: [0, -1], ArrowDown: [0, 1],
      };
      const direction = event.shiftKey ? directions[event.key] : null;
      if (direction) {
        keyboardIntent = true;
        consume(event);
        const { rect } = point(canvas);
        const stepX = Math.max(0.01, Math.min(0.08, 24 / Math.max(1, rect.width)));
        const stepY = Math.max(0.01, Math.min(0.08, 24 / Math.max(1, rect.height)));
        cursorX = Math.max(0.01, Math.min(0.99, cursorX + direction[0] * stepX));
        cursorY = Math.max(0.01, Math.min(0.99, cursorY + direction[1] * stepY));
        cursor.style.display = "block";
        place(canvas);
        mouse(canvas, "mousemove", 0);
        announce("Hovered", "No tile under the inspection cursor");
      } else if (event.key === "Enter") {
        keyboardIntent = true;
        consume(event);
        cursor.style.display = "block";
        place(canvas);
        mouse(canvas, "mousedown", 1);
        mouse(canvas, "mouseup", 0);
        announce(["Selected", "Clicked"], "Selection cleared");
      } else if (event.key === "Escape") {
        announceNow("Selection cleared");
      }
    });
  }

  new MutationObserver(install).observe(document.body, {
    childList: true, subtree: true,
  });
  window.addEventListener("resize", () => {
    if (!isActive(activeCanvas) || cursor?.style.display !== "block") return;
    place(activeCanvas);
    mouse(activeCanvas, "mousemove", 0);
    announce("Hovered", "No tile under the inspection cursor");
  });
  install();
})();
</script>"""
            html = html.replace("</body>", f"{keyboard_inspection}</body>", 1)
            if "render" not in query and str(self.app.fcode_version or "").startswith("2.2."):
                # fcode 2.2's viewer supports `render=square`; newer viewers
                # removed projection selection entirely. Keep the legacy
                # default honest and never inject a dead redirect into 2.3+.
                square_default = """
<script id="oarena-square-render-default">
(() => {
  const url = new URL(location.href);
  if (!url.searchParams.has("render")) {
    url.searchParams.set("render", "square");
    location.replace(url);
  }
})();
</script>"""
                html = html.replace("</body>", f"{square_default}</body>")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                       headers={"Cache-Control": _NO_STORE})
            return
        # Vite hashes every asset filename, so they are safe to cache forever.
        self._send_file(target, _content_type(target), cache=_IMMUTABLE)

    def _map_editor(self, relative: str, query: dict[str, list[str]]) -> None:
        """Serve fcode's editor, optionally preloading one project map.

        The official editor only supports file-picker imports.  Its input is a
        normal browser file input, so the small same-origin bootstrap below
        fetches the selected map and dispatches that exact import flow.  The
        editor remains the official fcode UI; it simply opens on the requested
        map rather than a blank board.
        """
        dist = self.app.viz_dir
        if dist is None:
            raise HttpError(503, "the fcode map editor is not available in this fcode install")
        target = dist / "map-editor.html" if relative in ("", "index.html", "map-editor.html") else _safe_join(dist, relative)
        if target is None or not target.is_file():
            raise HttpError(404, f"no such map-editor file: {relative}")
        if target.suffix.lower() != ".html":
            return self._send_file(target, _content_type(target), cache=_IMMUTABLE)

        name = _qs_str(query, "map")
        if name is not None:
            self._project_map(name)  # validate before returning a page that will fail later
        html = target.read_text(encoding="utf-8", errors="replace")
        html = html.replace('"/assets/', '"/map-editor/assets/')
        square_editor = """
<script id="oarena-square-render-default">
(() => {
  const deadline = Date.now() + 10_000;
  function selectSquare() {
    const button = [...document.querySelectorAll("button")]
      .find((node) => node.textContent.trim() === "Square");
    if (button) {
      if (!button.disabled) button.click();
      return;
    }
    if (Date.now() < deadline) setTimeout(selectSquare, 30);
  }
  selectSquare();
})();
</script>"""
        if name is not None:
            endpoint = f"/api/maps/{quote(name, safe='')}/file"
            bootstrap = f"""
<script id="oarena-map-import">
(() => {{
  const endpoint = {json.dumps(endpoint)};
  const name = {json.dumps(name)};
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function waitForEditorScene() {{
    // React creates the hidden file input before Phaser has run the editor
    // scene's `create()` method. Importing at that point decodes the map, but
    // crashes in `loadMap()` because `mapLayer` does not exist yet.
    const deadline = Date.now() + 10_000;
    while (!document.querySelector("#root canvas")) {{
      if (Date.now() >= deadline) throw new Error("fcode map editor did not initialise");
      await pause(30);
    }}
    // The canvas appears at the beginning of Phaser boot, before its assets
    // and scene `create()` hook finish. The bundled editor exposes no ready
    // signal, so use a conservative local-only settle window before its React
    // state update calls `loadMap()`.
    await pause(1_500);
  }}
  async function load() {{
    const input = [...document.querySelectorAll('input[type="file"]')]
      .find((node) => String(node.accept || "").includes(".map26"));
    if (!input) return setTimeout(load, 30);
    try {{
      const response = await fetch(endpoint, {{ cache: "no-store" }});
      if (!response.ok) throw new Error(`map fetch failed (${{response.status}})`);
      // Use the raw buffer rather than a response Blob.  Firefox has been
      // observed to hand the editor an empty/opaque Blob from this synthetic
      // file-input path even though the fetch itself succeeded; ArrayBuffer is
      // copied byte-for-byte into the File the editor's FileReader consumes.
      const bytes = await response.arrayBuffer();
      if (!bytes.byteLength) throw new Error("map fetch returned an empty file");
      const imported = new File([bytes], `${{name}}.map26`, {{ type: "application/octet-stream" }});
      // The fcode editor clears its input before FileReader starts. Keep this
      // synthetic file alive independently of that input: Firefox otherwise
      // may release the DataTransfer-backed payload before the editor's
      // FileReader uses it, despite the successful fetch above.
      window.__oarenaMapImportFile = imported;
      const files = new DataTransfer();
      files.items.add(imported);
      const importAlert = "Failed to import map file. Make sure it's a valid .map26 or .pb map file.";
      const nativeAlert = window.alert.bind(window);
      let attempts = 0;
      const dispatchImport = () => {{
        input.files = files.files;
        input.dispatchEvent(new Event("change", {{ bubbles: true, composed: true }}));
      }};
      // The bundled editor reports its scene-startup race through `alert`,
      // after swallowing the underlying `mapLayer is undefined` exception.
      // Retry that one known transient failure with exponential backoff. A
      // persistent (real) import failure still reaches the user unchanged.
      window.alert = (message) => {{
        if (message === importAlert && attempts < 4) {{
          attempts += 1;
          setTimeout(dispatchImport, 500 * (2 ** attempts));
          return;
        }}
        nativeAlert(message);
      }};
      await waitForEditorScene();
      dispatchImport();
      document.title = `${{name}} · fcode map editor`;
    }} catch (error) {{
      console.error("oarena could not import map into the fcode editor", error);
    }}
  }}
  load();
}})();
</script>"""
            html = html.replace("</body>", f"{square_editor}{bootstrap}</body>")
        else:
            html = html.replace("</body>", f"{square_editor}</body>")
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", headers={"Cache-Control": _NO_STORE})

    # -- GET /api ----------------------------------------------------------

    def _api_platform_session(self, query: dict[str, list[str]]) -> None:
        _only_query(query, set())
        self._json(self.app.platform.session())

    def _api_platform_matches(self, query: dict[str, list[str]]) -> None:
        _only_query(query, {"limit", "type", "mine", "team_id", "cursor"})
        limit = max(1, min(100, _qs_int(query, "limit", 20)))
        match_type = _qs_str(query, "type")
        if match_type not in {None, "ladder", "unrated"}:
            raise HttpError(400, "'type' must be 'ladder' or 'unrated'")
        mine = _qs_bool(query, "mine")
        team_id = _qs_uuid(query, "team_id")
        if mine and team_id is not None:
            raise HttpError(400, "'mine' and 'team_id' cannot be combined")
        cursor = _qs_str(query, "cursor")
        if cursor is not None and (
            len(cursor) > 2048 or any(ord(char) < 0x20 for char in cursor)
        ):
            raise HttpError(400, "'cursor' is invalid")
        result = self.app.platform.matches(
            limit=limit,
            match_type=match_type,
            mine=mine,
            team_id=team_id,
            cursor=cursor,
        )
        try:
            self.app.platform_history.observe_matches(result.get("matches"))
        except Exception:
            # Version history is auxiliary; never hide a valid platform result
            # because its local cache is unavailable.
            pass
        self._json(result)

    def _api_platform_match(
        self, match_id: str, query: dict[str, list[str]]
    ) -> None:
        _only_query(query, set())
        result = self.app.platform.match(match_id)
        match = result.get("match")
        try:
            self.app.platform_history.observe_matches(
                [match] if match is not None else []
            )
        except Exception:
            pass
        self._json(result)

    def _api_platform_replay(
        self, match_id: str, game: int, query: dict[str, list[str]]
    ) -> None:
        _only_query(query, set())
        body = self.app.platform.replay(match_id, game)
        self._send(
            200,
            body,
            "application/octet-stream",
            headers={
                "Cache-Control": _PRIVATE_IMMUTABLE,
                "Content-Disposition": (
                    f'inline; filename="{match_id}_game_{game}.replay26"'
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )

    def _api_platform_ladder(self, query: dict[str, list[str]]) -> None:
        _only_query(query, {"limit"})
        limit = max(1, min(100, _qs_int(query, "limit", 50)))
        try:
            tracking = self.app.platform_history.request_refresh(
                platform=self.app.platform
            )
        except Exception:
            tracking = _unavailable_version_tracking()
        result = self.app.platform.ladder(limit=limit)
        try:
            result = self.app.platform_history.enrich_ladder(result)
        except Exception:
            result = dict(result)
            tracking = {
                **tracking,
                "last_error": "Version tracking is unavailable",
                "error": "Version tracking is unavailable",
            }
        result["version_tracking"] = tracking
        self._json(result)

    def _api_platform_version_tracking(
        self, query: dict[str, list[str]]
    ) -> None:
        """Report local sync progress without refetching the public ladder."""

        _only_query(query, set())
        try:
            status = self.app.platform_history.status()
        except Exception:
            status = _unavailable_version_tracking()
        else:
            try:
                # Paging progress is extra detail about a sync that is already
                # reported; losing it must not turn a healthy status into an
                # "unavailable" one.
                status = {
                    **status,
                    "backfill": self.app.platform_history.backfill_state(),
                }
            except Exception:
                pass
        self._json(status)

    def _api_platform_version_history(
        self, query: dict[str, list[str]]
    ) -> None:
        """Return the local observed version timeline without polling FCode."""

        _only_query(query, {"limit", "team_id"})
        limit = max(1, min(200, _qs_int(query, "limit", 100)))
        team_id = _qs_uuid(query, "team_id")
        try:
            result = self.app.platform_history.history(
                team_id=team_id,
                limit=limit,
            )
        except Exception as exc:
            raise HttpError(503, "Version tracking is unavailable") from exc
        self._json(result)

    def _api_platform_version_run_games(
        self, query: dict[str, list[str]]
    ) -> None:
        """Return the matches observed during one team-version run."""

        _only_query(query, {"team_id", "ordinal", "limit"})
        team_id = _qs_uuid(query, "team_id")
        if team_id is None:
            raise HttpError(400, "'team_id' is required")
        ordinal = _qs_bounded_int(query, "ordinal", 0, low=0, high=100_000)
        limit = _qs_bounded_int(query, "limit", 500, low=1, high=500)
        try:
            result = self.app.platform_history.run_games(
                team_id=team_id,
                ordinal=ordinal,
                limit=limit,
            )
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        except Exception as exc:
            raise HttpError(503, "Version tracking is unavailable") from exc
        self._json(result)

    def _api_platform_version_match_runs(
        self, query: dict[str, list[str]]
    ) -> None:
        """Report the version each team played in one match, from local records."""

        _only_query(query, {"match_id"})
        match_id = _qs_uuid(query, "match_id")
        if match_id is None:
            raise HttpError(400, "'match_id' is required")
        try:
            result = self.app.platform_history.match_runs(match_id=match_id)
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        except Exception as exc:
            raise HttpError(503, "Version tracking is unavailable") from exc
        self._json(result)

    def _api_platform_test_runs(self, query: dict[str, list[str]]) -> None:
        _only_query(query, {"limit"})
        limit = max(1, min(100, _qs_int(query, "limit", 50)))
        self._json(self.app.platform.test_runs(limit=limit))

    def _api_platform_scrims(self, query: dict[str, list[str]]) -> None:
        """Return only durable local scrim state; this route never polls FCode."""

        _only_query(query, {"limit", "our_version"})
        limit = _qs_bounded_int(query, "limit", 100, low=1, high=200)
        raw_version = _one(query, "our_version")
        our_version: str | int | None
        if raw_version is None:
            our_version = None
        elif raw_version == "current":
            our_version = "current"
        else:
            try:
                parsed = int(raw_version)
            except (TypeError, ValueError) as exc:
                raise HttpError(
                    400, "'our_version' must be 'current' or a positive integer"
                ) from exc
            if parsed <= 0 or parsed > 2_147_483_647 or str(parsed) != raw_version:
                raise HttpError(
                    400, "'our_version' must be 'current' or a positive integer"
                )
            our_version = parsed
        try:
            snapshot = self.app.scrims.snapshot(
                limit=limit,
                our_version=our_version,
            )
        except ValueError as exc:
            raise _scrim_validation_error(exc) from exc
        self._json(snapshot)

    def _api_platform_teams(self, query: dict[str, list[str]]) -> None:
        _only_query(query, {"q", "limit"})
        raw_query = _one(query, "q")
        search = _bounded_text(
            raw_query,
            "q",
            limit=MAX_PLATFORM_NAME_CHARS,
        )
        assert search is not None
        limit = _qs_bounded_int(query, "limit", 20, low=1, high=20)
        self._json(self.app.platform.team_search(search, limit=limit))

    def _api_platform_maps(self, query: dict[str, list[str]]) -> None:
        _only_query(query, set())
        self._json(self.app.platform.platform_maps())

    def _api_state(self) -> None:
        app = self.app
        # Read the sequence first: a client resuming from it may replay an event
        # already folded into this snapshot, which is the harmless direction.
        seq = app.bus.last_seq
        rows = reporting.ladder(app.store, include_inactive=True)
        maps_json = app.maps_json()
        self._json(
            {
                "config": app.config_json(),
                "status": app.league.status,
                "ladder": app.ladder_json(rows),
                "maps": maps_json,
                "counts": {
                    "bots": len(rows),
                    "games": app.store.game_count(),
                    "maps": len(maps_json),
                },
                "fcode": app.fcode_version,
                "seq": seq,
                "instance": app.instance_id,
                "web_revision": app.web_revision,
            }
        )

    def _api_ladder(self, query: dict[str, list[str]]) -> None:
        # Competitive views use active bots by default.  `/api/state` retains
        # the full catalog for the Bots administration view; `?all=1` remains
        # available to callers that explicitly need disabled entries.
        rows = reporting.ladder(self.app.store, include_inactive=_qs_bool(query, "all", False))
        self._json(self.app.ladder_json(rows))

    def _api_matrix(self, query: dict[str, list[str]]) -> None:
        store = self.app.store
        names = [row.name for row in reporting.ladder(store, include_inactive=False)]
        self._json(reporting.matrix_json(store, names, min_games=max(0, _qs_int(query, "min", 0))))

    def _api_pair_matrix(self, query: dict[str, list[str]]) -> None:
        """Map-by-map head-to-head records for the selected Games pairing."""
        first = _qs_str(query, "a")
        second = _qs_str(query, "b")
        if not first or not second:
            raise HttpError(400, "both 'a' and 'b' are required")
        if first == second:
            raise HttpError(400, "'a' and 'b' must be different bots")
        if self.app.store.get_bot(first) is None or self.app.store.get_bot(second) is None:
            raise HttpError(404, "unknown bot in pairing")
        map_names = [
            game_map.name
            for game_map in maps.discover(
                self.app.cfg.maps_dir,
                self.app.cfg.extra_maps_dir,
            )
        ]
        self._json(reporting.pair_map_matrix_json(self.app.store, first, second, map_names))

    def _api_timeline(self, query: dict[str, list[str]]) -> None:
        # 0 deliberately means every bot; 50 keeps an accidental URL from
        # sending thousands of bot *series* to a local browser.  Each selected
        # series is intentionally uncapped: this is a local diagnostic graph,
        # and silently trimming its left side falsifies the global-game axis.
        top = max(0, min(50, _qs_int(query, "top", 5)))
        self._json(reporting.timeline_json(self.app.store, top=top))

    def _api_games(self, query: dict[str, list[str]]) -> None:
        limit = min(MAX_GAME_LIMIT, max(1, _qs_int(query, "limit", DEFAULT_GAME_LIMIT)))
        status = _qs_str(query, "status")
        if _qs_bool(query, "failed"):
            status = "failed"
        games = self.app.store.list_games(
            limit=limit,
            before_id=_qs_int(query, "before", 0) or None,
            bot=_qs_str(query, "bot"),
            opponent=_qs_str(query, "opponent"),
            map=_qs_str(query, "map"),
            status=status,
            tag=_qs_str(query, "tag"),
            rated_only=_qs_bool(query, "rated"),
        )
        # A full page means there may be more; the cursor is the oldest id here.
        nxt = games[-1].id if len(games) == limit else None
        serializer = (
            reporting.game_summary_json
            if _qs_bool(query, "summary")
            else reporting.game_json
        )
        self._json(
            {
                "games": [serializer(g) for g in games],
                "next": nxt,
                "latest_match_tag": self.app.store.latest_match_tag(),
            }
        )

    def _api_batch(self, query: dict[str, list[str]]) -> None:
        """Return one immutable run and its games in submitted plan order."""
        _only_query(query, {"tag", "limit"})
        tag = _one(query, "tag")
        if tag is None or tag == "":
            raise HttpError(400, "'tag' is required")
        limit = _qs_int(query, "limit", MAX_GAME_LIMIT)
        if limit < 1 or limit > MAX_GAME_LIMIT:
            raise HttpError(
                400, f"'limit' must be between 1 and {MAX_GAME_LIMIT}"
            )

        # Read the monotonic game list first and the counter second.  While a
        # batch is still running this yields a self-consistent recovery view:
        # ``played_games`` cannot trail the rows returned below.
        games = self.app.store.list_batch_games(tag, limit=limit)
        batch = self.app.store.batch(tag)
        if batch is None:
            raise HttpError(404, f"no batch tagged {tag!r}")
        played_games = int(batch["played_games"])
        self._json(
            {
                "tag": str(batch["tag"]),
                "mode": str(batch["mode"]),
                "status": str(batch["status"]),
                "requested_games": (
                    None
                    if batch["requested_games"] is None
                    else int(batch["requested_games"])
                ),
                "played_games": played_games,
                "started": str(batch["started"]),
                "finished": str(batch["finished"]),
                "games": [reporting.game_summary_json(game) for game in games],
                "more": played_games > len(games),
            }
        )

    def _api_game(self, gid: int) -> None:
        game = self.app.store.get_game(gid)
        if game is None:
            raise HttpError(404, f"no game {gid}")
        data = reporting.game_json(game)
        try:
            data["fcode_metadata"] = (
                json.loads(game.fcode_metadata_json) if game.fcode_metadata_json else None
            )
        except (TypeError, ValueError):
            data["fcode_metadata"] = None
        data["log_tail"] = (
            _tail(self.app.cfg.log_dir / Path(game.log).name) if game.log else ""
        )
        self._json(data)

    def _api_replay(self, gid: int) -> None:
        game = self.app.store.get_game(gid)
        if game is None:
            raise HttpError(404, f"no game {gid}")
        if not game.replay:
            raise HttpError(404, f"the replay for game {gid} has been pruned")
        path = self.app.cfg.replay_dir / Path(game.replay).name
        if not path.is_file():
            raise HttpError(404, f"the replay for game {gid} is missing from disk")
        self._send_file(path, "application/octet-stream", cache=_IMMUTABLE)

    def _api_log(self, gid: int) -> None:
        game = self.app.store.get_game(gid)
        if game is None:
            raise HttpError(404, f"no game {gid}")
        if not game.log:
            raise HttpError(404, f"no log was kept for game {gid}")
        path = self.app.cfg.log_dir / Path(game.log).name
        if not path.is_file():
            raise HttpError(404, f"the log for game {gid} is missing from disk")
        self._send_file(path, "text/plain; charset=utf-8")

    def _project_map(self, name: str) -> maps.GameMap:
        """A map by its project package name, never an arbitrary filesystem path."""
        for game_map in maps.discover(
            self.app.cfg.maps_dir,
            self.app.cfg.extra_maps_dir,
        ):
            if game_map.name == name:
                return game_map
        raise HttpError(404, f"no map named {name!r}")

    def _api_map_file(self, name: str) -> None:
        game_map = self._project_map(name)
        self._send_file(game_map.path, "application/octet-stream", cache=_NO_STORE)

    def _api_bot(self, name: str) -> None:
        try:
            detail = reporting.bot_detail(self.app.store, name)
        except KeyError as exc:
            raise HttpError(404, f"no bot named {name!r}") from exc
        self._json(detail)

    # -- GET /api/events (SSE) ---------------------------------------------

    def _api_events(self, query: dict[str, list[str]]) -> None:
        """Stream the event bus: ``hello``, the missed gap, then live events.

        The bus lock is only held inside ``subscribe``/``since``/``emit``; every
        socket write happens outside it, so a stalled reader cannot block the
        league's run thread (its queue drops old events instead).
        """
        since = _qs_int(query, "since", 0)
        resume = self.headers.get("Last-Event-ID")
        if resume and resume.strip().isdigit():
            since = max(since, int(resume.strip()))

        bus = self.app.bus
        self._sent = True
        self.close_connection = True  # the stream is delimited by the close
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", _NO_STORE)
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            self.wfile.write(f"retry: {SSE_RETRY_MS}\n\n".encode())
            with bus.subscribe() as subscription:
                # Subscribe first, then take the sequence: anything emitted in
                # between is delivered twice at worst, never lost.
                current = bus.last_seq
                # No `id:` on hello — the client is not caught up until the gap
                # below has been replayed, and an id here would move its
                # Last-Event-ID past events it has never seen.
                self._frame(
                    Event(
                        seq=current,
                        ts=time.time(),
                        type="hello",
                        data={
                            "seq": current,
                            "instance": self.app.instance_id,
                            "web_revision": self.app.web_revision,
                        },
                    ),
                    with_id=False,
                )
                highest = since
                for event in bus.since(since):
                    if event.seq > highest:
                        self._frame(event)
                        highest = event.seq
                last_write = time.monotonic()
                while True:
                    try:
                        event = subscription.get(timeout=SSE_TICK_S)
                    except queue.Empty:
                        if time.monotonic() - last_write >= HEARTBEAT_S:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                            last_write = time.monotonic()
                        continue
                    if event.seq > highest:
                        self._frame(event)
                        highest = event.seq
                        last_write = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the browser navigated away; nothing to report
        except OSError:
            pass

    def _frame(self, event: Event, *, with_id: bool = True) -> None:
        """Write one SSE frame: ``id``/``event``/``data`` with the full envelope."""
        payload = json.dumps(event.to_json(), default=str)
        head = f"id: {event.seq}\n" if with_id else ""
        self.wfile.write(f"{head}event: {event.type}\ndata: {payload}\n\n".encode())
        self.wfile.flush()

    # -- POST --------------------------------------------------------------

    def _post(self, path: str, _query: dict[str, list[str]], payload: dict[str, Any]) -> None:
        if not path.startswith("/api/"):
            raise HttpError(404, f"no such path: {path}")
        route = path[len("/api"):].rstrip("/") or "/"
        if route == "/match":
            return self._post_match(payload)
        if route == "/arena":
            return self._post_arena(payload)
        if route == "/platform/scrims":
            return self._post_platform_scrim(payload)
        if route == "/platform/scrims/autoscrim":
            return self._post_platform_autoscrim(payload)
        if route == "/platform/scrims/refresh":
            return self._post_platform_scrim_refresh(payload)
        if route == "/stop":
            force = _body_bool(payload, "force", False)
            killed = self.app.league.force_stop() if force else 0
            if not force:
                self.app.league.stop()
            return self._json({"ok": True, "force": force, "killed": killed}, code=202)
        if route == "/sync":
            self._busy()
            return self._json(dataclasses.asdict(self.app.league.sync()))
        if route == "/recompute":
            return self._post_recompute()
        if route == "/reset":
            return self._post_reset(payload)
        if route == "/maps/editor":
            return self._post_map_editor()
        if route == "/storage/replays":
            return self._post_storage_replays(payload)
        if route == "/storage/budget":
            return self._post_storage_budget(payload)
        if route == "/theme":
            return self._post_theme(payload)

        action = _RE_BOT_ACTION.fullmatch(route)
        if action is not None:
            name, verb = action.group(1), action.group(2)
            if verb == "active":
                return self._post_bot_active(name, payload)
            return self._post_bot_note(name, payload)

        raise HttpError(404, f"no such path: {path}")

    def _busy(self) -> None:
        if self.app.league.running:
            raise HttpError(409, "a run is already in progress — stop it first")

    def _require_owned_state(self, action: str) -> None:
        if not self.app.cfg.owns_state_dir:
            raise HttpError(
                403,
                f"{action} is disabled for external shared state; use the owning project",
            )

    def _start(self, action: Callable[[], None]) -> None:
        """Run a league start call, translating "already running" into a 409."""
        self._busy()
        try:
            action()
        except RuntimeError as exc:
            raise HttpError(409, str(exc)) from exc

    def _post_match(self, payload: dict[str, Any]) -> None:
        a = _body_str(payload, "a")
        b = _body_str(payload, "b")
        if not a or not b:
            raise HttpError(400, "both 'a' and 'b' are required")
        mirror_raw = payload.get("mirror")
        mirror = None if mirror_raw is None else _body_bool(payload, "mirror", True)
        tag = _body_str(payload, "tag") or None
        repeat = _parsed_body_int(payload.get("repeat", 1), "repeat")
        if not 1 <= repeat <= 500:
            raise HttpError(400, "'repeat' must be between 1 and 500")
        seed_policy_raw = _body_str(payload, "seed_policy").lower()
        seed_policy = seed_policy_raw or None
        if seed_policy not in {None, "fixed", "random"}:
            raise HttpError(400, "'seed_policy' must be 'random' or 'fixed'")
        if seed_policy is None and payload.get("seed") is not None:
            raise HttpError(400, "'seed_policy' is required when 'seed' is provided")
        seed: int | None = None
        if seed_policy == "fixed":
            if payload.get("seed") is None:
                raise HttpError(400, "'seed' is required for a fixed seed policy")
            seed = _body_seed(payload, "seed")
            if seed + repeat - 1 > MAX_GAME_SEED:
                raise HttpError(
                    400,
                    f"'seed' plus {repeat} rounds exceeds {MAX_GAME_SEED}",
                )
        elif seed_policy == "random" and payload.get("seed") is not None:
            raise HttpError(400, "a random seed policy cannot include 'seed'")
        # Resolve up front so a typo answers 400 rather than queueing games that
        # can only fail (this also syncs a bot that appeared since the last scan).
        self.app.league.resolve(a)
        self.app.league.resolve(b)
        try:
            jobs = self.app.league.plan_match(
                a,
                b,
                maps=_body_names(payload, "maps"),
                repeat=repeat,
                mirror=mirror,
                rated=_body_bool(payload, "rated", True),
                tag=tag or "match",
                seed_policy=seed_policy,
                seed=seed,
            )
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        if not jobs:
            raise HttpError(400, "that match plans zero games")
        label = _body_str(payload, "label") or f"{a} vs {b}"
        self._start(
            lambda: self.app.league.start_match(
                jobs, label=label, batch_tag=tag
            )
        )
        response: dict[str, Any] = {"total": len(jobs)}
        if tag is not None:
            response["tag"] = tag
        self._json(response, code=202)

    def _post_arena(self, payload: dict[str, Any]) -> None:
        kind = (_body_str(payload, "kind") or "ladder").lower()
        if kind not in _ARENA_KINDS:
            raise HttpError(400, f"'kind' must be one of {', '.join(_ARENA_KINDS)}")
        target = _body_str(payload, "target") or None
        if kind == "vs" and not target:
            raise HttpError(400, "'target' is required when kind is 'vs'")
        if target:
            self.app.league.resolve(target)
        top = _body_int(payload, "top", 0, minimum=0)
        rated = _body_bool(payload, "rated", True)
        tag = _body_str(payload, "tag") or None
        try:
            self._start(
                lambda: self.app.league.start_arena(
                    kind, top=top, target=target, rated=rated, batch_tag=tag
                )
            )
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        response: dict[str, Any] = {"ok": True}
        if tag is not None:
            response["tag"] = tag
        self._json(response, code=202)

    def _post_platform_scrim(self, payload: dict[str, Any]) -> None:
        _only_body(
            payload,
            allowed={
                "request_key",
                "opponent_team_id",
                "opponent_team_name",
                "source_match_id",
                "map_names",
            },
            required={"request_key", "opponent_team_id"},
        )
        request_key = _body_uuid(payload, "request_key")
        opponent_team_id = _body_uuid(payload, "opponent_team_id")
        opponent_team_name = _bounded_text(
            payload.get("opponent_team_name"),
            "opponent_team_name",
            limit=MAX_PLATFORM_NAME_CHARS,
            optional=True,
        )
        source_match_id = _body_uuid(payload, "source_match_id", optional=True)
        map_names = _body_map_names(payload)
        assert request_key is not None and opponent_team_id is not None
        try:
            request = self.app.scrims.enqueue_manual(
                request_key,
                opponent_team_id,
                opponent_team_name=opponent_team_name,
                source_match_id=source_match_id,
                map_names=map_names,
            )
        except ValueError as exc:
            raise _scrim_validation_error(exc) from exc
        self._json({"request": request}, code=202)

    def _post_platform_autoscrim(self, payload: dict[str, Any]) -> None:
        _only_body(
            payload,
            allowed={
                "enabled",
                "target_team_ids",
                "target_team_names",
                "target_matches_per_version",
                "map_names",
            },
            required={"enabled"},
        )
        enabled = _body_bool(payload, "enabled", False)
        if not enabled and set(payload) == {"enabled"}:
            try:
                settings = self.app.scrims.disable_autoscrim()
            except ValueError as exc:
                raise _scrim_validation_error(exc) from exc
            self._json({"settings": settings})
            return
        target_ids = _body_target_ids(payload)
        target_names = _body_target_names(payload, target_ids)
        target_matches = _body_bounded_int(
            payload,
            "target_matches_per_version",
            0,
            low=0,
            high=100,
        )
        map_names = _body_map_names(payload)
        try:
            settings = self.app.scrims.configure_autoscrim(
                enabled,
                target_team_ids=target_ids,
                target_team_names=target_names,
                target_matches_per_version=target_matches,
                map_names=map_names,
            )
        except ValueError as exc:
            raise _scrim_validation_error(exc) from exc
        self._json({"settings": settings})

    def _post_platform_scrim_refresh(self, payload: dict[str, Any]) -> None:
        _only_body(payload, allowed=set())
        try:
            self.app.scrims.refresh()
        except ValueError as exc:
            raise _scrim_validation_error(exc) from exc
        self._json({"ok": True}, code=202)

    def _post_recompute(self) -> None:
        self._busy()
        if not self.app.cfg.owns_state_dir:
            raise HttpError(
                403,
                "recompute is disabled for external shared state; use the owning project",
            )
        self.app.store.recompute(self.app.rater)
        self.app.bus.emit("log", level="info", msg="ratings recomputed from game history")
        self._json({"ok": True})

    def _post_storage_replays(self, payload: dict[str, Any]) -> None:
        """Delete retained replay files except for the requested newest count.

        Game rows and ratings deliberately survive: this is space management,
        not a history reset.  The store orders retained files newest first, so
        slicing after ``keep`` makes the deletion policy unambiguous.
        """
        self._busy()
        self._require_owned_state("replay deletion")
        keep = _body_int(payload, "keep", 0, minimum=0)
        app = self.app
        victims = app.store.replay_files()[keep:]
        freed = 0
        removed = 0
        for gid, filename in victims:
            path = app.cfg.replay_dir / filename
            freed += _path_size(path)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                app.bus.emit("log", level="warn", msg=f"could not remove replay {filename}: {exc}")
                continue
            app.store.clear_replay(gid)
            removed += 1
        if removed:
            app.bus.emit(
                "log", level="warn", msg=f"deleted {removed} old replay(s), freeing {freed / 1_000_000:.1f} MB"
            )
        self._json({"ok": True, "keep": keep, "removed": removed, "freed": freed, "storage": app.storage_json()})

    def _post_storage_budget(self, payload: dict[str, Any]) -> None:
        """Persist a replay cap (or uncapped mode) and apply a lowered cap now."""
        self._busy()
        self._require_owned_state("replay budget changes")
        if "budget_mb" not in payload:
            raise HttpError(400, "'budget_mb' is required (use null for unlimited)")
        raw = payload["budget_mb"]
        if raw is None:
            budget: int | None = None
        else:
            budget = _body_int(payload, "budget_mb", 0, minimum=0)
        app = self.app
        try:
            config.set_replay_budget(app.cfg.config_path, budget)
            updated = config.from_file(app.cfg.config_path)
        except ConfigError as exc:
            raise HttpError(500, str(exc)) from exc
        # This setting is safe to replace while games run; the next completed
        # game and any manual collection see the new cap immediately.
        app.cfg = updated
        app.league.cfg = updated
        pruned = app.league.enforce_replay_budget()
        app.bus.emit(
            "log",
            level="info",
            msg=("replay budget set to unlimited" if budget is None else f"replay budget set to {budget} MB")
            + (f"; pruned {pruned} replay(s)" if pruned else ""),
        )
        self._json({"ok": True, "budget_mb": budget, "pruned": pruned, "storage": app.storage_json()})

    def _post_theme(self, payload: dict[str, Any]) -> None:
        """Save a project-wide visual preference while the league is idle."""
        self._busy()
        theme = _body_str(payload, "theme").lower()
        if theme not in {"dark", "light"}:
            raise HttpError(400, "'theme' must be 'dark' or 'light'")
        app = self.app
        try:
            config.set_ui_theme(app.cfg.config_path, theme)
            updated = config.from_file(app.cfg.config_path)
        except ConfigError as exc:
            raise HttpError(500, str(exc)) from exc
        app.cfg = updated
        # The league only reads config for game settings, but retaining the
        # same object graph avoids one server exposing stale config in state.
        app.league.cfg = updated
        app.bus.emit("config", ui_theme=theme)
        self._json({"ok": True, "theme": theme})

    def _post_reset(self, payload: dict[str, Any]) -> None:
        self._busy()
        wipe_all = _body_bool(payload, "all", False)
        clean = _body_bool(payload, "clean", False)
        app = self.app
        if not app.cfg.owns_state_dir:
            raise HttpError(
                403,
                "reset is disabled for external shared state; use the owning project",
            )
        with app.store.writer_lock.hold("dashboard reset"):
            if clean:
                app.store.clean()
                app.store.ensure_rating_config(app.cfg.trueskill)
            else:
                app.store.reset(keep_bots=not wipe_all, rater=app.rater)
            if wipe_all or clean:
                # Plain reset leaves files for `oarena gc`; `all` starts over.
                for directory in (app.cfg.replay_dir, app.cfg.log_dir, app.cfg.tmp_dir):
                    _empty_dir(directory)
            report = app.league.sync()
        app.bus.emit(
            "log",
            level="warn",
            msg="clean reset — database, history, replays and logs wiped" if clean else "history reset" + (" (bots, replays and logs wiped)" if wipe_all else ""),
        )
        self._json({"ok": True, "all": wipe_all or clean, "clean": clean, "sync": dataclasses.asdict(report)})

    def _post_map_editor(self) -> None:
        """Launch the official fcode map editor from the project directory."""
        executable = shutil.which("fcode")
        if executable is None:
            raise HttpError(503, "the fcode executable is not on this server's PATH")
        try:
            subprocess.Popen(
                [executable, "map-editor"],
                cwd=self.app.cfg.root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise HttpError(500, f"could not launch fcode map-editor: {exc}") from exc
        self._json({"ok": True}, code=202)

    def _post_bot_active(self, name: str, payload: dict[str, Any]) -> None:
        self._busy()
        self._require_bot(name)
        active = _body_bool(payload, "active", True)
        self.app.store.set_active(name, active)
        self.app.bus.emit(
            "log", level="info", msg=f"{name} {'enabled' if active else 'disabled'}"
        )
        self.app.bus.emit("bot_active", name=name, active=active)
        self._json({"ok": True, "name": name, "active": active})

    def _post_bot_note(self, name: str, payload: dict[str, Any]) -> None:
        self._busy()
        self._require_bot(name)
        note = _body_str(payload, "note")
        self.app.store.set_note(name, note)
        self._json({"ok": True, "name": name, "note": note})

    # -- DELETE ------------------------------------------------------------

    def _delete(self, path: str, _query: dict[str, list[str]], _payload: dict[str, Any]) -> None:
        route = path[len("/api"):].rstrip("/") if path.startswith("/api/") else ""
        bot = _RE_BOT.fullmatch(route) if route else None
        if bot is None:
            raise HttpError(404, f"no such path: {path}")
        name = bot.group(1)
        self._busy()
        self._require_owned_state("bot deletion")
        self._require_bot(name)
        self.app.store.delete_bot(name)
        self.app.bus.emit("log", level="warn", msg=f"{name} deleted along with its games")
        self._json({"ok": True, "name": name})

    def _require_bot(self, name: str) -> Bot:
        stored = self.app.store.get_bot(name)
        if stored is None:
            raise HttpError(404, f"no bot named {name!r}")
        return stored


def _empty_dir(directory: Path) -> None:
    """Delete every regular file in *directory*, keeping the directory itself."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file():
                entry.unlink()
        except OSError:
            continue


# --------------------------------------------------------------------------- #
# server
# --------------------------------------------------------------------------- #


class Server(ThreadingHTTPServer):
    """Threaded HTTP server holding the one shared :class:`App`."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: App) -> None:
        self.app = app
        super().__init__(address, Handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Swallow the routine disconnect noise, print anything genuine."""
        exc = sys.exc_info()[1]
        if isinstance(
            exc,
            (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError),
        ):
            return
        traceback.print_exc()


def make_server(
    app: App,
    host: str = "127.0.0.1",
    port: int = 7878,
    *,
    strict_port: bool = False,
) -> Server:
    """Bind a server, optionally falling back to a free port when busy."""
    try:
        return Server((host, port), app)
    except OSError:
        if port == 0 or strict_port:
            raise
        return Server((host, 0), app)


def _url_host(host: str) -> str:
    if host in ("", "0.0.0.0"):  # noqa: S104 - display only
        return "127.0.0.1"
    if host in ("::", "::0"):
        return "[::1]"
    if ":" in host:
        return f"[{host}]"
    return host


def _banner(app: App, url: str, *, requested: int, actual: int) -> None:
    cfg = app.cfg
    engine = app.fcode_version or "missing"
    print(f"oarena {__version__}  ·  fcode {engine}")
    print(f"  {url}")
    if requested not in (0, actual):
        print(f"  (port {requested} was busy — using {actual})")
    print(f"  project  {cfg.root}")
    print(f"  bots     {cfg.bots_dir}")
    print(f"  maps     {cfg.maps_dir}")
    print(f"  extra    {cfg.extra_maps_dir}")
    print(f"  workers  {cfg.n_workers}")
    if app.viz_dir is None:
        print("  note     no bundled official 3D visualiser; built-in 2D replay viewer is available")
    print("  no authentication — do not expose this port to a network")
    print("  Ctrl-C to stop", flush=True)


def _open_later(url: str, delay: float = 0.3) -> None:
    """Open a browser once the server is definitely accepting connections."""

    def go() -> None:
        try:
            webbrowser.open(url, new=2)
        except Exception:  # pragma: no cover - headless machines
            pass

    timer = threading.Timer(delay, go)
    timer.daemon = True
    timer.start()


def serve(
    cfg: Config,
    *,
    host: str = "127.0.0.1",
    port: int = 7878,
    open_browser: bool = True,
    workers: int | None = None,
    strict_port: bool = False,
) -> None:
    """Run the dashboard until Ctrl-C, then stop the league and close cleanly."""
    app = App.create(cfg, workers=workers)
    try:
        app.league.sync()
    except StoreBusyError as exc:
        # Another oarena process holds the arena's single-writer lease -- a
        # match run, usually. Syncing the bot catalog is the only thing that
        # needs it here, and `League.sync` is explicitly safe to run beside a
        # live run; it is the coarse arena-wide lease it cannot get. Serving a
        # slightly stale catalog beats refusing to start, which took the whole
        # dashboard down for the length of someone else's sweep every time a
        # bot edit tripped the reloader.
        print(f"warning: bot catalog not synced — {exc}", flush=True)
    try:
        httpd = make_server(app, host, port, strict_port=strict_port)
    except OSError as exc:
        app.close()
        raise ConfigError(f"cannot bind {host}:{port} — {exc}") from exc

    actual = int(httpd.server_address[1])
    url = f"http://{_url_host(host)}:{actual}/"
    _banner(app, url, requested=port, actual=actual)
    if open_browser:
        _open_later(url)

    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nstopping — aborting in-flight games…", flush=True)
    finally:
        app.close()
        httpd.server_close()
