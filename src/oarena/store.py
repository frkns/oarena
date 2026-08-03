"""SQLite persistence for oarena: bots, games and the aggregates built from them.

Design notes
------------
* **One connection per process**, opened with ``check_same_thread=False`` and
  WAL, guarded by a module-level :class:`threading.RLock`. Every mutation also
  takes one OS advisory lease for the database's state directory. A League owns
  that lease for its whole run, and one rated result updates both bots and
  inserts its history row in a single transaction.
* **The database is scratch state.** The schema is versioned with
  ``PRAGMA user_version``. Known upgrades preserve history; an unrecognised
  schema fails closed rather than risking history. Replays and logs live on disk
  and ratings can be rebuilt with ``recompute``.
* Rating *policy* (what counts as rated, coinflip handling, breaking a bot that
  fails to import) lives in ``league.py``. This module only persists what it is
  handed.
"""

from __future__ import annotations

import functools
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import threading
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from oarena.ratings import CI, Rater, Rating

if TYPE_CHECKING:  # pragma: no cover - typing only
    from oarena.bots import BotSource
    from oarena.config import TrueSkillConfig

__all__ = [
    "SCHEMA_VERSION",
    "Bot",
    "Game",
    "ImportReport",
    "Record",
    "Store",
    "StoreBatchError",
    "StoreBusyError",
    "StoreConfigError",
    "StoreImportError",
    "StoreSchemaError",
    "WriterLock",
    "now_iso",
]

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS bots (
  name          TEXT PRIMARY KEY,
  dir           TEXT NOT NULL,
  entry         TEXT NOT NULL,
  active        INTEGER NOT NULL DEFAULT 1,
  broken        INTEGER NOT NULL DEFAULT 0,
  broken_reason TEXT NOT NULL DEFAULT '',
  src_hash      TEXT NOT NULL DEFAULT '',
  mu            REAL NOT NULL,
  sigma         REAL NOT NULL,
  note          TEXT NOT NULL DEFAULT '',
  created       TEXT NOT NULL,
  updated       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_versions (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  bot      TEXT NOT NULL,
  src_hash TEXT NOT NULL,
  ts       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS games (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  a             TEXT NOT NULL,
  b             TEXT NOT NULL,
  a_src_hash    TEXT NOT NULL DEFAULT '',
  b_src_hash    TEXT NOT NULL DEFAULT '',
  fcode_version TEXT NOT NULL DEFAULT '',
  fcode_metadata_json TEXT NOT NULL DEFAULT '',
  map           TEXT NOT NULL,
  seed          INTEGER NOT NULL,
  rated         INTEGER NOT NULL DEFAULT 1,
  status        TEXT NOT NULL,
  winner        TEXT,
  win_condition TEXT NOT NULL DEFAULT '',
  turns         INTEGER NOT NULL DEFAULT 0,
  duration_ms   INTEGER NOT NULL DEFAULT 0,
  resign_message TEXT NOT NULL DEFAULT '',
  error         TEXT NOT NULL DEFAULT '',
  a_titanium INTEGER DEFAULT 0, a_mined INTEGER DEFAULT 0,
  a_units    INTEGER DEFAULT 0, a_buildings INTEGER DEFAULT 0, a_errors INTEGER DEFAULT 0,
  b_titanium INTEGER DEFAULT 0, b_mined INTEGER DEFAULT 0,
  b_units    INTEGER DEFAULT 0, b_buildings INTEGER DEFAULT 0, b_errors INTEGER DEFAULT 0,
  a_mu_before REAL, a_sigma_before REAL, a_mu_after REAL, a_sigma_after REAL,
  b_mu_before REAL, b_sigma_before REAL, b_mu_after REAL, b_sigma_after REAL,
  replay      TEXT NOT NULL DEFAULT '',
  log         TEXT NOT NULL DEFAULT '',
  tag         TEXT NOT NULL DEFAULT '',
  batch_ordinal INTEGER,
  ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_pair ON games(a, b);
CREATE INDEX IF NOT EXISTS idx_games_ts   ON games(id DESC);
CREATE INDEX IF NOT EXISTS idx_games_map  ON games(map);
CREATE INDEX IF NOT EXISTS idx_games_tag  ON games(tag);
CREATE TABLE IF NOT EXISTS game_imports (
  source_key       TEXT NOT NULL,
  source_game_id   INTEGER NOT NULL,
  game_id          INTEGER NOT NULL UNIQUE
                   REFERENCES games(id) ON DELETE CASCADE,
  source_game_hash TEXT NOT NULL,
  source_db        TEXT NOT NULL,
  imported         TEXT NOT NULL,
  PRIMARY KEY (source_key, source_game_id)
);
CREATE INDEX IF NOT EXISTS idx_game_imports_game ON game_imports(game_id);
CREATE TABLE IF NOT EXISTS game_batches (
  tag             TEXT PRIMARY KEY,
  mode            TEXT NOT NULL,
  status          TEXT NOT NULL,
  requested_games INTEGER,
  played_games    INTEGER NOT NULL DEFAULT 0,
  started         TEXT NOT NULL,
  finished        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS league_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

# One lock for every Store in the process (see module docstring).
_LOCK = threading.RLock()

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _locked(fn: Callable[_P, _R]) -> Callable[_P, _R]:
    """Hold the database lock for the whole body of a Store method."""

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        self = cast("Store", args[0])
        with self._lock:
            return fn(*args, **kwargs)

    return wrapper


def _write_locked(fn: Callable[_P, _R]) -> Callable[_P, _R]:
    """Serialise a mutation across both threads and oarena processes."""

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        self = cast("Store", args[0])
        with self.writer_lock.hold(fn.__name__):
            with self._lock:
                return fn(*args, **kwargs)

    return wrapper


def now_iso() -> str:
    """UTC timestamp used for every ``ts``/``created``/``updated`` column."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StoreImportError(RuntimeError):
    """A source database is unsafe or incompatible with the destination league."""


class StoreSchemaError(RuntimeError):
    """The database schema is newer than or incompatible with this oarena."""


class StoreBusyError(RuntimeError):
    """Another process owns the league's exclusive writer lease."""


class StoreBatchError(RuntimeError):
    """A requested immutable game batch tag is invalid or already reserved."""


class StoreConfigError(RuntimeError):
    """A shared state directory was opened with incompatible rating settings."""


class WriterLock:
    """A re-entrant process-local handle for one OS advisory writer lock.

    SQLite protects individual transactions, but a rated result historically
    required several read/update/write calls. A League holds this lease for its
    entire run, while standalone mutations take it for one method. Separate
    oarena processes therefore fail fast instead of interleaving one ladder.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = Path(path) if path is not None else None
        self._guard = threading.RLock()
        self._condition = threading.Condition(self._guard)
        self._depth = 0
        self._fd: int | None = None
        self._purpose = ""
        self._authorized_threads: set[int] = set()
        self._exclusive = False

    def acquire(self, purpose: str = "write", *, exclusive: bool = False) -> None:
        with self._condition:
            thread_id = threading.get_ident()
            while self._depth:
                if thread_id not in self._authorized_threads:
                    if self._exclusive:
                        raise StoreBusyError(
                            f"another oarena writer is active in this process for "
                            f"{self.path.parent if self.path is not None else 'memory state'}"
                        )
                    self._condition.wait()
                    continue
                self._depth += 1
                return
            if self.path is None:
                self._depth = 1
                self._purpose = purpose
                self._authorized_threads = {thread_id}
                self._exclusive = bool(exclusive)
                return

            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    owner = os.read(fd, 4096).decode("utf-8", errors="replace").strip()
                finally:
                    os.close(fd)
                detail = f" ({owner})" if owner else ""
                raise StoreBusyError(
                    f"another oarena writer is active for {self.path.parent}{detail}"
                ) from exc
            except BaseException:
                os.close(fd)
                raise

            owner = json.dumps(
                {"pid": os.getpid(), "purpose": purpose, "started": now_iso()},
                separators=(",", ":"),
            ).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, owner)
            self._fd = fd
            self._depth = 1
            self._purpose = purpose
            self._authorized_threads = {thread_id}
            self._exclusive = bool(exclusive)

    def release(self) -> None:
        with self._condition:
            thread_id = threading.get_ident()
            if self._depth <= 0:
                raise RuntimeError("oarena writer lock released without being held")
            if thread_id not in self._authorized_threads:
                raise StoreBusyError(
                    "the current thread does not own the oarena writer lease"
                )
            self._depth -= 1
            if self._depth:
                return
            fd, self._fd = self._fd, None
            self._purpose = ""
            self._authorized_threads.clear()
            self._exclusive = False
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
            self._condition.notify_all()

    @contextmanager
    def hold(self, purpose: str = "write"):
        self.acquire(purpose)
        try:
            yield self
        finally:
            self.release()

    def authorize_current_thread(self) -> None:
        """Allow the run thread to inherit a lease acquired during setup."""

        with self._guard:
            if self._depth <= 0:
                raise RuntimeError("cannot inherit an oarena writer lease that is not held")
            self._authorized_threads.add(threading.get_ident())

    def disallow_current_thread(self) -> None:
        """Relinquish this thread's authority without releasing the lease."""

        with self._guard:
            thread_id = threading.get_ident()
            if thread_id not in self._authorized_threads:
                raise RuntimeError("current thread is not authorised for the writer lease")
            if len(self._authorized_threads) <= 1:
                raise RuntimeError("cannot leave an active writer lease without an owner")
            self._authorized_threads.remove(thread_id)

    @property
    def held(self) -> bool:
        with self._guard:
            return self._depth > 0


# --------------------------------------------------------------------------- #
# rows
# --------------------------------------------------------------------------- #


@dataclass
class Bot:
    """A row of the ``bots`` table."""

    name: str
    dir: str = ""
    entry: str = ""
    active: bool = True
    broken: bool = False
    broken_reason: str = ""
    src_hash: str = ""
    mu: float = 25.0
    sigma: float = 25.0 / 3.0
    note: str = ""
    created: str = ""
    updated: str = ""

    @property
    def rating(self) -> Rating:
        return Rating(self.mu, self.sigma)

    @property
    def score(self) -> float:
        return self.mu - CI * self.sigma

    @property
    def playable(self) -> bool:
        # ``broken`` is diagnostic: failed bots still play and take losses.
        return self.active


@dataclass
class Game:
    """A row of the ``games`` table.

    Field order mirrors the schema. ``id`` is 0 until :meth:`Store.add_game`
    assigns one. ``winner`` is ``'a'``, ``'b'``, ``'draw'`` or ``None`` (no
    result, e.g. a crash or timeout).
    """

    id: int = 0
    a: str = ""
    b: str = ""
    a_src_hash: str = ""
    b_src_hash: str = ""
    fcode_version: str = ""
    fcode_metadata_json: str = ""
    map: str = ""
    seed: int = 0
    rated: bool = True
    status: str = "ok"
    winner: str | None = None
    win_condition: str = ""
    turns: int = 0
    duration_ms: int = 0
    resign_message: str = ""
    error: str = ""
    a_titanium: int = 0
    a_mined: int = 0
    a_units: int = 0
    a_buildings: int = 0
    a_errors: int = 0
    b_titanium: int = 0
    b_mined: int = 0
    b_units: int = 0
    b_buildings: int = 0
    b_errors: int = 0
    a_mu_before: float | None = None
    a_sigma_before: float | None = None
    a_mu_after: float | None = None
    a_sigma_after: float | None = None
    b_mu_before: float | None = None
    b_sigma_before: float | None = None
    b_mu_after: float | None = None
    b_sigma_after: float | None = None
    replay: str = ""
    log: str = ""
    tag: str = ""
    batch_ordinal: int | None = None
    ts: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class Record:
    """Win/loss/draw tally from one bot's point of view."""

    wins: int = 0
    losses: int = 0
    draws: int = 0
    games: int = 0

    @property
    def winrate(self) -> float | None:
        """Share of points won, a draw counting as half a win. ``None`` if unplayed."""
        if self.games <= 0:
            return None
        return (self.wins + 0.5 * self.draws) / self.games

    @property
    def score(self) -> float:
        return self.wins + 0.5 * self.draws

    def __str__(self) -> str:
        return f"{self.wins}-{self.losses}-{self.draws}"


@dataclass(frozen=True)
class ImportReport:
    """Summary of one idempotent rated-game database import.

    ``bots`` is the set referenced by selected source rows. Hash validation is
    required only for bots in pending rows; an all-skipped idempotence check
    does not claim that old game hashes equal the bots' current versions.
    """

    source_key: str
    source_db: str
    through: int | None
    selected: int
    imported: int
    skipped: int
    would_import: int
    bots: tuple[str, ...]
    dry_run: bool


_GAME_COLUMNS: tuple[str, ...] = (
    "a",
    "b",
    "a_src_hash",
    "b_src_hash",
    "fcode_version",
    "fcode_metadata_json",
    "map",
    "seed",
    "rated",
    "status",
    "winner",
    "win_condition",
    "turns",
    "duration_ms",
    "resign_message",
    "error",
    "a_titanium",
    "a_mined",
    "a_units",
    "a_buildings",
    "a_errors",
    "b_titanium",
    "b_mined",
    "b_units",
    "b_buildings",
    "b_errors",
    "a_mu_before",
    "a_sigma_before",
    "a_mu_after",
    "a_sigma_after",
    "b_mu_before",
    "b_sigma_before",
    "b_mu_after",
    "b_sigma_after",
    "replay",
    "log",
    "tag",
    "batch_ordinal",
    "ts",
)

_LEGACY_GAME_COLUMNS = tuple(
    col
    for col in _GAME_COLUMNS
    if col
    not in {
        "a_src_hash",
        "b_src_hash",
        "batch_ordinal",
        "fcode_version",
        "fcode_metadata_json",
    }
)
_OPTIONAL_IMPORT_GAME_COLUMNS = frozenset(
    {
        "a_src_hash",
        "b_src_hash",
        "batch_ordinal",
        "fcode_version",
        "fcode_metadata_json",
    }
)

_RATING_COLUMNS = frozenset(
    {
        "a_mu_before",
        "a_sigma_before",
        "a_mu_after",
        "a_sigma_after",
        "b_mu_before",
        "b_sigma_before",
        "b_mu_after",
        "b_sigma_after",
    }
)
_LEGACY_GAME_FINGERPRINT_COLUMNS = tuple(
    col for col in _LEGACY_GAME_COLUMNS if col not in _RATING_COLUMNS
)
_PROVENANCE_GAME_COLUMNS = ("a_src_hash", "b_src_hash", "batch_ordinal")
_FCODE_PROVENANCE_GAME_COLUMNS = ("fcode_version", "fcode_metadata_json")


def _bot_from_row(row: sqlite3.Row) -> Bot:
    return Bot(
        name=row["name"],
        dir=row["dir"],
        entry=row["entry"],
        active=bool(row["active"]),
        broken=bool(row["broken"]),
        broken_reason=row["broken_reason"],
        src_hash=row["src_hash"],
        mu=float(row["mu"]),
        sigma=float(row["sigma"]),
        note=row["note"],
        created=row["created"],
        updated=row["updated"],
    )


def _game_from_row(row: sqlite3.Row) -> Game:
    g = Game(id=int(row["id"]))
    keys = set(row.keys())
    for col in _GAME_COLUMNS:
        if col in keys:
            setattr(g, col, row[col])
    g.rated = bool(row["rated"])
    g.seed = int(row["seed"])
    if g.batch_ordinal is not None:
        g.batch_ordinal = int(g.batch_ordinal)
    return g


def _game_fingerprint(row: sqlite3.Row) -> str:
    """Stable identity for source-game data that must not change between resumes."""

    # Keep the exact pre-provenance payload for migrated legacy rows so an
    # already-imported source remains resumable after its additive migration.
    payload = [row[col] for col in _LEGACY_GAME_FINGERPRINT_COLUMNS]
    provenance = [row[col] for col in _PROVENANCE_GAME_COLUMNS]
    if any(value not in ("", None) for value in provenance):
        payload.extend(["oarena-game-provenance-v1", *provenance])
    fcode_provenance = [row[col] for col in _FCODE_PROVENANCE_GAME_COLUMNS]
    if any(value not in ("", None) for value in fcode_provenance):
        payload.extend(["oarena-fcode-provenance-v1", *fcode_provenance])
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_artifact(state_dir: Path, kind: str, stored_name: str) -> Path | None:
    """Resolve a store-owned artifact without permitting path traversal."""

    if not stored_name:
        return None
    relative = Path(stored_name)
    if relative.is_absolute() or relative.name != stored_name:
        raise StoreImportError(f"unsafe {kind} filename in source database: {stored_name!r}")
    path = state_dir / ("replays" if kind == "replay" else "logs") / relative
    if not path.is_file():
        raise StoreImportError(f"source {kind} is recorded but missing: {path}")
    return path


def _copy_artifact(source: Path, destination: Path) -> None:
    """Copy one artifact without overwriting an existing game-id filename."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open("xb") as dst:
            created = True
            with source.open("rb") as src:
                shutil.copyfileobj(src, dst)
        shutil.copystat(source, destination)
    except BaseException:
        if created:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise


# --------------------------------------------------------------------------- #
# aggregation helpers
# --------------------------------------------------------------------------- #

# A decided game (winner IS NOT NULL) that is not a bot playing itself: the only
# rows that carry a head-to-head signal.
_DECIDED = "winner IS NOT NULL AND a <> b"


def _bot_source_clause(name: str, source_hash: str | None) -> tuple[str, tuple[object, ...]]:
    """SQL scope for games played by ``name``, optionally at one source hash."""
    if source_hash is None:
        return "(a = ? OR b = ?)", (name, name)
    return (
        "((a = ? AND a_src_hash = ?) OR (b = ? AND b_src_hash = ?))",
        (name, source_hash, name, source_hash),
    )


def _tally(rec: Record, side: str, winner: str | None, n: int = 1) -> None:
    """Fold ``n`` games with outcome ``winner`` into ``rec``, seen from ``side``."""
    if winner is None:
        return
    if winner == "draw":
        rec.draws += n
    elif winner == side:
        rec.wins += n
    else:
        rec.losses += n
    rec.games += n


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #


class Store:
    """The whole persistence layer. Thread-safe; one instance per process."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = _LOCK
        self.writer_lock = WriterLock(
            None if str(self._path) == ":memory:" else self._path.parent / "writer.lock"
        )
        self._closed = False
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        try:
            self._migrate()
        except BaseException:
            self._conn.close()
            self._closed = True
            raise

    # -- lifecycle ---------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    def _migrate(self) -> None:
        """Create or upgrade the schema without throwing away a known ladder.

        Version 2 retired the unused ``bots.snapshot`` column and gained import
        provenance. Version 3 adds an immutable fcode version and metadata
        snapshot to each game. Migrated rows deliberately keep both new values
        empty: replay provenance cannot be reconstructed after the fact.
        """
        with self._lock:
            row = self._conn.execute("PRAGMA user_version").fetchone()
            version = int(row[0]) if row is not None else 0
            # Do not guess at future layouts. In particular, never "recover" by
            # dropping tables: a newer oarena may contain the user's only copy
            # of a league.
            if version not in (0, 1, 2, SCHEMA_VERSION):
                raise StoreSchemaError(
                    f"unsupported oarena database schema version {version}; "
                    f"this build supports version {SCHEMA_VERSION}"
                )

            tables = {
                str(r["name"])
                for r in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            game_columns = (
                {
                    str(r["name"])
                    for r in self._conn.execute("PRAGMA table_info(games)").fetchall()
                }
                if "games" in tables
                else set()
            )
            required_tables = {
                "bots",
                "bot_versions",
                "games",
                "game_imports",
                "game_batches",
                "league_meta",
            }
            required_game_columns = {
                "a_src_hash",
                "b_src_hash",
                "batch_ordinal",
                "fcode_version",
                "fcode_metadata_json",
            }
            indexes = {
                str(r["name"])
                for r in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            current = (
                version == SCHEMA_VERSION
                and required_tables <= tables
                and required_game_columns <= game_columns
                and {
                    "idx_games_batch_ordinal",
                    "idx_games_tag",
                } <= indexes
            )
            if current:
                return

            with self.writer_lock.hold("schema migration"):
                # Re-check the version after taking the cross-process lease.
                row = self._conn.execute("PRAGMA user_version").fetchone()
                version = int(row[0]) if row is not None else 0
                if version not in (0, 1, 2, SCHEMA_VERSION):
                    raise StoreSchemaError(
                        f"unsupported oarena database schema version {version}; "
                        f"this build supports version {SCHEMA_VERSION}"
                    )
                self._conn.executescript(SCHEMA)
                columns = {
                    str(r["name"])
                    for r in self._conn.execute("PRAGMA table_info(games)").fetchall()
                }
                additions = {
                    "a_src_hash": "TEXT NOT NULL DEFAULT ''",
                    "b_src_hash": "TEXT NOT NULL DEFAULT ''",
                    "batch_ordinal": "INTEGER",
                    "fcode_version": "TEXT NOT NULL DEFAULT ''",
                    "fcode_metadata_json": "TEXT NOT NULL DEFAULT ''",
                }
                for name, declaration in additions.items():
                    if name not in columns:
                        self._conn.execute(
                            f"ALTER TABLE games ADD COLUMN {name} {declaration}"
                        )
                self._conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_games_batch_ordinal "
                    "ON games(tag, batch_ordinal) "
                    "WHERE tag <> '' AND batch_ordinal IS NOT NULL"
                )
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._conn.commit()

    @_locked
    def close(self) -> None:
        """Commit and close. Idempotent — a second close is a no-op, not a crash."""
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.commit()
        finally:
            self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- bots --------------------------------------------------------------
    @_write_locked
    def upsert_bot(self, src: BotSource, initial: Rating) -> Bot:
        """Insert ``src`` if it is new (keeping any existing row untouched) and return it."""
        ts = now_iso()
        self._conn.execute(
            "INSERT OR IGNORE INTO bots "
            "(name, dir, entry, active, broken, broken_reason, src_hash,"
            " mu, sigma, note, created, updated) "
            "VALUES (?,?,?,1,0,'',?,?,?,'',?,?)",
            (
                src.name,
                str(src.dir),
                str(src.entry),
                src.src_hash,
                float(initial.mu),
                float(initial.sigma),
                ts,
                ts,
            ),
        )
        self._conn.commit()
        bot = self.get_bot(src.name)
        if bot is None:  # pragma: no cover - the insert above guarantees a row
            raise RuntimeError(f"failed to store bot {src.name!r}")
        return bot

    @_locked
    def get_bot(self, name: str) -> Bot | None:
        row = self._conn.execute("SELECT * FROM bots WHERE name = ?", (name,)).fetchone()
        return _bot_from_row(row) if row is not None else None

    @_locked
    def bots(self, *, active_only: bool = False, playable_only: bool = False) -> list[Bot]:
        """All bots, name-sorted. Playable means active; broken is diagnostic."""
        where = ""
        if playable_only or active_only:
            where = " WHERE active = 1"
        rows = self._conn.execute(f"SELECT * FROM bots{where} ORDER BY name").fetchall()
        return [_bot_from_row(r) for r in rows]

    def _touch(self, name: str, sql: str, params: Sequence[Any]) -> None:
        self._conn.execute(sql, (*params, now_iso(), name))
        self._conn.commit()

    @_write_locked
    def set_rating(self, name: str, r: Rating) -> None:
        self._touch(
            name,
            "UPDATE bots SET mu = ?, sigma = ?, updated = ? WHERE name = ?",
            (float(r.mu), float(r.sigma)),
        )

    @_write_locked
    def set_active(self, name: str, active: bool) -> None:
        self._touch(
            name, "UPDATE bots SET active = ?, updated = ? WHERE name = ?", (int(bool(active)),)
        )

    @_write_locked
    def set_broken(self, name: str, broken: bool, reason: str = "") -> None:
        self._touch(
            name,
            "UPDATE bots SET broken = ?, broken_reason = ?, updated = ? WHERE name = ?",
            (int(bool(broken)), reason if broken else ""),
        )

    @_write_locked
    def set_note(self, name: str, note: str) -> None:
        self._touch(name, "UPDATE bots SET note = ?, updated = ? WHERE name = ?", (note,))

    @_write_locked
    def set_hash(self, name: str, src_hash: str) -> None:
        """Record a new source hash and append it to the bot's version history.

        Callers append a version every time they call this, so only call it when
        the hash actually changed (or when the bot is first discovered).
        """
        self._touch(name, "UPDATE bots SET src_hash = ?, updated = ? WHERE name = ?", (src_hash,))
        self._conn.execute(
            "INSERT INTO bot_versions (bot, src_hash, ts) VALUES (?,?,?)",
            (name, src_hash, now_iso()),
        )
        self._conn.commit()

    @_write_locked
    def set_paths(self, name: str, dir: str, entry: str) -> None:
        self._touch(
            name,
            "UPDATE bots SET dir = ?, entry = ?, updated = ? WHERE name = ?",
            (str(dir), str(entry)),
        )

    @_write_locked
    def delete_bot(self, name: str) -> None:
        """Remove a bot together with its games and version history."""
        self._conn.execute("DELETE FROM games WHERE a = ? OR b = ?", (name, name))
        self._conn.execute("DELETE FROM bot_versions WHERE bot = ?", (name,))
        self._conn.execute("DELETE FROM bots WHERE name = ?", (name,))
        self._conn.commit()

    @_locked
    def versions(self, name: str, limit: int = 50) -> list[tuple[int, str, str]]:
        """``(id, src_hash, ts)`` for a bot's recorded source versions, newest first."""
        rows = self._conn.execute(
            "SELECT id, src_hash, ts FROM bot_versions WHERE bot = ? ORDER BY id DESC LIMIT ?",
            (name, int(limit)),
        ).fetchall()
        return [(int(r["id"]), r["src_hash"], r["ts"]) for r in rows]

    @_locked
    def latest_versions(self) -> dict[str, tuple[int, str]]:
        """Latest recorded source ``(version_id, timestamp)`` for every bot.

        ``bots.updated`` is intentionally not used for source recency: ratings,
        notes and health changes all touch that column.  A version row is added
        only when the discovered source hash changes, so it is the stable signal
        used by bot pickers and other source-oriented UI.
        """
        rows = self._conn.execute(
            "SELECT v.bot, v.id, v.ts "
            "FROM bot_versions AS v "
            "JOIN ("
            "  SELECT bot, MAX(id) AS id FROM bot_versions GROUP BY bot"
            ") AS latest ON latest.id = v.id "
            "ORDER BY v.id DESC"
        ).fetchall()
        return {
            str(row["bot"]): (int(row["id"]), str(row["ts"]))
            for row in rows
        }

    # -- games -------------------------------------------------------------
    def _insert_game(self, g: Game) -> int:
        """Insert without committing. The caller must hold ``self._lock``."""

        if not g.ts:
            g.ts = now_iso()
        values: list[Any] = []
        for col in _GAME_COLUMNS:
            v = getattr(g, col)
            values.append(int(v) if isinstance(v, bool) else v)
        placeholders = ",".join("?" * len(_GAME_COLUMNS))
        cur = self._conn.execute(
            f"INSERT INTO games ({','.join(_GAME_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
        g.id = int(cur.lastrowid or 0)
        return g.id

    @_write_locked
    def add_game(self, g: Game) -> int:
        """Insert a game, stamping ``ts`` if unset. Sets and returns ``g.id``."""

        gid = self._insert_game(g)
        self._conn.commit()
        return gid

    @_write_locked
    def record_game(self, g: Game, rater: Rater) -> dict[str, float]:
        """Atomically insert one result and, when rated, update both bots.

        The game row's before/after rating stamps and both current bot ratings
        commit in one ``BEGIN IMMEDIATE`` transaction. This prevents even a
        misbehaving writer that ignores the run lease from observing or leaving
        half of a rating chain.
        """

        delta: dict[str, float] = {}
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            batch = (
                self._conn.execute(
                    "SELECT status, requested_games FROM game_batches WHERE tag = ?",
                    (g.tag,),
                ).fetchone()
                if g.tag
                else None
            )
            bots: dict[str, sqlite3.Row] | None = None
            if batch is not None or (g.rated and g.a != g.b):
                rows = self._conn.execute(
                    "SELECT name, src_hash, mu, sigma FROM bots WHERE name IN (?, ?)",
                    (g.a, g.b),
                ).fetchall()
                bots = {str(row["name"]): row for row in rows}

            if batch is not None:
                if str(batch["status"]) != "running":
                    raise StoreBatchError(
                        f"batch tag {g.tag!r} is already sealed"
                    )
                if g.batch_ordinal is None or int(g.batch_ordinal) < 0:
                    raise StoreBatchError(
                        f"batch tag {g.tag!r} requires a non-negative batch ordinal"
                    )
                requested = batch["requested_games"]
                if requested is not None and int(g.batch_ordinal) >= int(requested):
                    raise StoreBatchError(
                        f"batch ordinal {g.batch_ordinal} is outside the "
                        f"{requested}-game plan for {g.tag!r}"
                    )
                if not g.a_src_hash or not g.b_src_hash:
                    raise StoreBatchError(
                        f"batch tag {g.tag!r} requires both per-side source hashes"
                    )
                assert bots is not None
                for side, name, recorded_hash in (
                    ("a", g.a, g.a_src_hash),
                    ("b", g.b, g.b_src_hash),
                ):
                    current = bots.get(name)
                    if current is None:
                        raise StoreBatchError(
                            f"batch tag {g.tag!r} side {side} references missing bot {name!r}"
                        )
                    current_hash = str(current["src_hash"])
                    if recorded_hash != current_hash:
                        raise StoreBatchError(
                            f"batch tag {g.tag!r} side {side} source hash for {name!r} "
                            f"is {recorded_hash!r}, but the league has {current_hash!r}"
                        )
            elif g.batch_ordinal is not None:
                raise StoreBatchError(
                    f"game has batch ordinal {g.batch_ordinal} but tag {g.tag!r} "
                    "is not reserved"
                )

            if g.rated and g.a != g.b:
                assert bots is not None
                row_a, row_b = bots.get(g.a), bots.get(g.b)
                if row_a is None or row_b is None:
                    g.rated = False
                else:
                    before_a = Rating(float(row_a["mu"]), float(row_a["sigma"]))
                    before_b = Rating(float(row_b["mu"]), float(row_b["sigma"]))
                    after_a, after_b = rater.update(
                        before_a, before_b, g.winner or "draw"
                    )
                    g.a_mu_before, g.a_sigma_before = before_a.mu, before_a.sigma
                    g.a_mu_after, g.a_sigma_after = after_a.mu, after_a.sigma
                    g.b_mu_before, g.b_sigma_before = before_b.mu, before_b.sigma
                    g.b_mu_after, g.b_sigma_after = after_b.mu, after_b.sigma
                    updated = now_iso()
                    self._conn.executemany(
                        "UPDATE bots SET mu = ?, sigma = ?, updated = ? WHERE name = ?",
                        (
                            (after_a.mu, after_a.sigma, updated, g.a),
                            (after_b.mu, after_b.sigma, updated, g.b),
                        ),
                    )
                    delta = {
                        g.a: after_a.score - before_a.score,
                        g.b: after_b.score - before_b.score,
                    }
            elif g.rated:
                g.rated = False

            self._insert_game(g)
            if g.tag:
                self._conn.execute(
                    "UPDATE game_batches SET played_games = played_games + 1 "
                    "WHERE tag = ?",
                    (g.tag,),
                )
            self._conn.commit()
            return delta
        except BaseException:
            self._conn.rollback()
            raise

    @staticmethod
    def _validated_batch_tag(tag: str) -> str:
        cleaned = tag.strip()
        if not cleaned or cleaned != tag:
            raise StoreBatchError(
                "batch tag must be non-empty and have no surrounding whitespace"
            )
        if len(cleaned) > 200:
            raise StoreBatchError("batch tag must be at most 200 characters")
        return cleaned

    @_write_locked
    def reserve_batch(
        self,
        tag: str,
        *,
        mode: str,
        requested_games: int | None,
    ) -> None:
        """Reserve an immutable tag exactly once; reuse and resume are forbidden."""

        key = self._validated_batch_tag(tag)
        if self._conn.execute(
            "SELECT 1 FROM game_batches WHERE tag = ?", (key,)
        ).fetchone() is not None:
            raise StoreBatchError(
                f"batch tag {key!r} is already reserved; choose a new tag "
                "(tagged batches are immutable and cannot be resumed)"
            )
        if self._conn.execute(
            "SELECT 1 FROM games WHERE tag = ? LIMIT 1", (key,)
        ).fetchone() is not None:
            raise StoreBatchError(
                f"batch tag {key!r} already exists in legacy game history; choose a new tag"
            )
        total = None if requested_games is None else max(0, int(requested_games))
        self._conn.execute(
            "INSERT INTO game_batches "
            "(tag, mode, status, requested_games, played_games, started, finished) "
            "VALUES (?,?, 'running', ?, 0, ?, '')",
            (key, mode, total, now_iso()),
        )
        self._conn.commit()

    @_write_locked
    def finish_batch(self, tag: str, *, status: str) -> None:
        """Seal a reserved batch. Its tag remains unavailable forever."""

        key = self._validated_batch_tag(tag)
        if status not in {"completed", "stopped", "aborted"}:
            raise StoreBatchError(f"unsupported batch status {status!r}")
        row = self._conn.execute(
            "SELECT requested_games, played_games FROM game_batches "
            "WHERE tag = ? AND status = 'running'",
            (key,),
        ).fetchone()
        if row is None:
            raise StoreBatchError(f"batch tag {key!r} is not an active reserved batch")
        if (
            status == "completed"
            and row["requested_games"] is not None
            and int(row["requested_games"]) != int(row["played_games"])
        ):
            status = "aborted"
        cur = self._conn.execute(
            "UPDATE game_batches SET status = ?, finished = ? "
            "WHERE tag = ? AND status = 'running'",
            (status, now_iso(), key),
        )
        if cur.rowcount != 1:
            raise StoreBatchError(f"batch tag {key!r} is not an active reserved batch")
        self._conn.commit()

    @_locked
    def batch(self, tag: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM game_batches WHERE tag = ?", (tag,)
        ).fetchone()
        return dict(row) if row is not None else None

    def ensure_rating_config(self, cfg: TrueSkillConfig) -> None:
        """Persist and verify the TrueSkill environment used by this ladder."""

        payload = json.dumps(
            {
                "mu": float(cfg.mu),
                "sigma": float(cfg.sigma),
                "beta": float(cfg.beta),
                "tau": float(cfg.tau),
                "draw_prob": float(cfg.draw_prob),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM league_meta WHERE key = 'trueskill'"
            ).fetchone()
        if row is None:
            with self.writer_lock.hold("record TrueSkill configuration"):
                with self._lock:
                    row = self._conn.execute(
                        "SELECT value FROM league_meta WHERE key = 'trueskill'"
                    ).fetchone()
                    if row is None:
                        self._conn.execute(
                            "INSERT INTO league_meta(key, value) VALUES ('trueskill', ?)",
                            (payload,),
                        )
                        self._conn.commit()
                        return
        if str(row["value"]) != payload:
            raise StoreConfigError(
                "TrueSkill settings do not match the existing shared league; "
                f"database has {row['value']}, config requests {payload}"
            )

    @_write_locked
    def set_files(self, gid: int, replay: str, log: str) -> None:
        """Attach the persisted replay/log filenames once they are in place."""
        self._conn.execute(
            "UPDATE games SET replay = ?, log = ? WHERE id = ?", (replay, log, int(gid))
        )
        self._conn.commit()

    @_locked
    def get_game(self, gid: int) -> Game | None:
        row = self._conn.execute("SELECT * FROM games WHERE id = ?", (int(gid),)).fetchone()
        return _game_from_row(row) if row is not None else None

    @_locked
    def list_games(
        self,
        *,
        limit: int = 100,
        before_id: int | None = None,
        bot: str | None = None,
        opponent: str | None = None,
        map: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        rated_only: bool = False,
    ) -> list[Game]:
        """Games newest first.

        ``bot`` and ``opponent`` each require that name to have played, so giving
        both selects exactly that pairing (either way round). ``before_id`` is the
        keyset cursor: only games with a smaller id are returned. ``status`` takes
        a literal status, or the pseudo-status ``"failed"`` for an execution
        failure or any game containing an attributed bot error.
        """
        where: list[str] = []
        params: list[Any] = []
        if before_id is not None:
            where.append("id < ?")
            params.append(int(before_id))
        for name in (bot, opponent):
            if name:
                where.append("(a = ? OR b = ?)")
                params.extend((name, name))
        if map:
            where.append("map = ?")
            params.append(map)
        if status:
            if status == "failed":
                where.append("(status <> 'ok' OR a_errors > 0 OR b_errors > 0)")
            else:
                where.append("status = ?")
                params.append(status)
        if tag:
            where.append("tag = ?")
            params.append(tag)
        if rated_only:
            where.append("rated = 1")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._conn.execute(
            f"SELECT * FROM games{clause} ORDER BY id DESC LIMIT ?", (*params, int(limit))
        ).fetchall()
        return [_game_from_row(r) for r in rows]

    @_locked
    def list_batch_games(self, tag: str, *, limit: int = 500) -> list[Game]:
        """Return one reserved batch in immutable plan order.

        Batch ordinals, unlike game ids, describe the submitted plan.  Ordering
        by them ensures the first planned game remains recoverable even when a
        large batch has completed out of worker/insert order.
        """
        rows = self._conn.execute(
            "SELECT * FROM games WHERE tag = ? "
            "ORDER BY batch_ordinal ASC, id ASC LIMIT ?",
            (tag, int(limit)),
        ).fetchall()
        return [_game_from_row(r) for r in rows]

    @_locked
    def list_games_after(
        self,
        after_id: int,
        *,
        limit: int = 500,
        tag: str | None = None,
    ) -> list[Game]:
        """Games newer than ``after_id``, oldest first.

        This is the forward keyset cursor used by live consumers.  Repeated
        calls with the last returned id cannot skip rows when more than
        ``limit`` games arrive between polls.
        """
        where = ["id > ?"]
        params: list[Any] = [int(after_id)]
        if tag:
            where.append("tag = ?")
            params.append(tag)
        rows = self._conn.execute(
            f"SELECT * FROM games WHERE {' AND '.join(where)} "
            "ORDER BY id ASC LIMIT ?",
            (*params, int(limit)),
        ).fetchall()
        return [_game_from_row(r) for r in rows]

    @_locked
    def game_count(self, *, tag: str | None = None) -> int:
        if tag is None:
            return int(self._conn.execute("SELECT COUNT(*) FROM games").fetchone()[0])
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM games WHERE tag = ?", (tag,)
            ).fetchone()[0]
        )

    @_write_locked
    def import_rated_games(
        self,
        source_db: Path,
        *,
        source_key: str,
        rater: Rater,
        replay_dir: Path,
        log_dir: Path,
        source_state_dir: Path | None = None,
        through: int | None = None,
        dry_run: bool = False,
    ) -> ImportReport:
        """Import rated rows from another oarena database, exactly once.

        ``(source_key, source game id)`` is the durable identity. Reusing the key
        resumes an earlier cutoff import; already-seen rows are verified and
        skipped. A fingerprint prevents a reset or edited source database from
        silently changing history under the same key.

        Bot names and current source hashes must match the destination. Replay
        and log files are copied under the newly allocated destination game id.
        The inserts, provenance rows, artifact names and complete native rating
        updates append from the destination bots' current ratings and commit as
        part of the same database transaction. Ratings belonging to bots outside
        the imported batch are left untouched. Any failure rolls the database
        back and removes files created by this call.
        """

        key = source_key.strip()
        if not key or key != source_key:
            raise StoreImportError("source key must be non-empty and have no surrounding whitespace")
        if len(key) > 200:
            raise StoreImportError("source key must be at most 200 characters")
        if through is not None and int(through) < 1:
            raise StoreImportError("--through must be a positive source game id")
        cutoff = int(through) if through is not None else None

        source_path = Path(source_db).expanduser().resolve()
        if not source_path.is_file():
            raise StoreImportError(f"source database does not exist: {source_path}")
        if str(self._path) != ":memory:":
            destination_path = self._path.expanduser().resolve()
            try:
                same_database = os.path.samefile(source_path, destination_path)
            except (FileNotFoundError, OSError):
                same_database = source_path == destination_path
            if same_database:
                raise StoreImportError("source and destination databases are the same file")

        state_dir = (
            Path(source_state_dir).expanduser().resolve()
            if source_state_dir is not None
            else source_path.parent
        )

        uri = f"{source_path.as_uri()}?mode=ro"
        source: sqlite3.Connection | None = None
        try:
            source = sqlite3.connect(uri, uri=True)
            source.row_factory = sqlite3.Row
            source.execute("PRAGMA query_only=ON")
            source.execute("BEGIN")

            game_columns = {
                str(row["name"]) for row in source.execute("PRAGMA table_info(games)").fetchall()
            }
            bot_columns = {
                str(row["name"]) for row in source.execute("PRAGMA table_info(bots)").fetchall()
            }
            # Provenance columns were added under the v2 marker. A read-only
            # pre-provenance v2 source remains importable by synthesising their
            # legacy defaults below.
            missing_games = ({"id"} | set(_LEGACY_GAME_COLUMNS)) - game_columns
            missing_bots = {"name", "src_hash"} - bot_columns
            if missing_games or missing_bots:
                details = []
                if missing_games:
                    details.append("games: " + ", ".join(sorted(missing_games)))
                if missing_bots:
                    details.append("bots: " + ", ".join(sorted(missing_bots)))
                raise StoreImportError(
                    "source is not a compatible oarena database; missing " + "; ".join(details)
                )

            where = "WHERE rated = 1"
            params: tuple[object, ...] = ()
            if cutoff is not None:
                where += " AND id <= ?"
                params = (cutoff,)
            selections = []
            for col in _GAME_COLUMNS:
                if col in game_columns:
                    selections.append(col)
                elif col == "batch_ordinal":
                    selections.append("NULL AS batch_ordinal")
                else:
                    selections.append(f"'' AS {col}")
            source_rows = source.execute(
                f"SELECT id,{','.join(selections)} FROM games {where} ORDER BY id",
                params,
            ).fetchall()
            if cutoff is not None and (
                not source_rows or int(source_rows[-1]["id"]) != cutoff
            ):
                highest = int(source_rows[-1]["id"]) if source_rows else 0
                raise StoreImportError(
                    f"--through {cutoff} is not an existing rated source game id "
                    f"(highest selected rated id: {highest})"
                )
            for row in source_rows:
                source_id = int(row["id"])
                if row["status"] != "ok":
                    raise StoreImportError(
                        f"rated source game {source_id} has unsupported status {row['status']!r}"
                    )
                if row["winner"] not in ("a", "b", "draw"):
                    raise StoreImportError(
                        f"rated source game {source_id} has unsupported winner {row['winner']!r}"
                    )
                if row["a"] == row["b"]:
                    raise StoreImportError(
                        f"rated source game {source_id} is a self-match and carries no skill signal"
                    )

            bot_names = sorted(
                {
                    str(row[side])
                    for row in source_rows
                    for side in ("a", "b")
                }
            )
            source_hashes: dict[str, str] = {}
            if bot_names:
                placeholders = ",".join("?" for _ in bot_names)
                source_hashes = {
                    str(row["name"]): str(row["src_hash"])
                    for row in source.execute(
                        f"SELECT name, src_hash FROM bots WHERE name IN ({placeholders})",
                        bot_names,
                    ).fetchall()
                }

            for name in bot_names:
                if not source_hashes.get(name):
                    raise StoreImportError(
                        f"source game references bot {name!r} without a source hash"
                    )

            fingerprints = {
                int(row["id"]): _game_fingerprint(row)
                for row in source_rows
            }

            mapping_where = "source_key = ?"
            mapping_params: tuple[object, ...] = (key,)
            if cutoff is not None:
                mapping_where += " AND source_game_id <= ?"
                mapping_params += (cutoff,)
            existing_rows = self._conn.execute(
                "SELECT source_game_id, source_game_hash FROM game_imports "
                f"WHERE {mapping_where}",
                mapping_params,
            ).fetchall()
            existing = {
                int(row["source_game_id"]): str(row["source_game_hash"])
                for row in existing_rows
            }
            for source_id, old_fingerprint in existing.items():
                fingerprint = fingerprints.get(source_id)
                if fingerprint is None:
                    raise StoreImportError(
                        f"source key {key!r} previously imported game {source_id}, "
                        "but that rated source row is now missing"
                    )
                if old_fingerprint != fingerprint:
                    raise StoreImportError(
                        f"source game {source_id} changed since it was imported under key {key!r}"
                    )

            pending: list[tuple[int, Game, str, Path | None, Path | None]] = []
            pending_hashes: dict[str, set[str]] = {}
            for row in source_rows:
                source_id = int(row["id"])
                if source_id in existing:
                    continue
                source_replay = _source_artifact(state_dir, "replay", str(row["replay"]))
                source_log = _source_artifact(state_dir, "log", str(row["log"]))
                game = _game_from_row(row)
                game.a_src_hash = game.a_src_hash or source_hashes[game.a]
                game.b_src_hash = game.b_src_hash or source_hashes[game.b]
                # The source fingerprint above retains the source batch ordinal,
                # but imported rows are not members of a destination-native
                # batch because game_batches metadata is intentionally not
                # imported. Keep the source tag only as a legacy label.
                game.batch_ordinal = None
                pending_hashes.setdefault(game.a, set()).add(game.a_src_hash)
                pending_hashes.setdefault(game.b, set()).add(game.b_src_hash)
                for col in _RATING_COLUMNS:
                    setattr(game, col, None)
                game.id = 0
                game.replay = ""
                game.log = ""
                pending.append(
                    (source_id, game, fingerprints[source_id], source_replay, source_log)
                )

            pending_tags = sorted(
                {game.tag for _source_id, game, *_rest in pending if game.tag}
            )
            if pending_tags:
                placeholders = ",".join("?" for _ in pending_tags)
                collision = self._conn.execute(
                    "SELECT tag FROM game_batches "
                    f"WHERE tag IN ({placeholders}) LIMIT 1",
                    pending_tags,
                ).fetchone()
                if collision is not None:
                    raise StoreImportError(
                        f"source tag {collision['tag']!r} is reserved by a "
                        "destination-native batch"
                    )

            expected_hashes: dict[str, str] = {}
            for name, hashes in sorted(pending_hashes.items()):
                if len(hashes) != 1:
                    raise StoreImportError(
                        f"pending source games contain multiple source hashes for {name!r}: "
                        + ", ".join(sorted(hashes))
                    )
                expected = next(iter(hashes))
                destination_bot = self.get_bot(name)
                if destination_bot is None:
                    raise StoreImportError(f"destination has no bot named {name!r}")
                if not destination_bot.src_hash:
                    raise StoreImportError(f"destination bot {name!r} has no source hash")
                if destination_bot.src_hash != expected:
                    raise StoreImportError(
                        f"source hash mismatch for {name!r}: "
                        f"source game {expected}, destination {destination_bot.src_hash}"
                    )
                expected_hashes[name] = expected

            report = ImportReport(
                source_key=key,
                source_db=str(source_path),
                through=cutoff,
                selected=len(source_rows),
                imported=0 if dry_run else len(pending),
                skipped=len(existing),
                would_import=len(pending),
                bots=tuple(bot_names),
                dry_run=bool(dry_run),
            )
            if dry_run or not pending:
                source.rollback()
                return report

            created_files: list[Path] = []
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                # Import is an append to the destination league, just like a
                # sequence of native League.finish calls. In particular, current
                # ratings may encode source-change sigma re-inflation that is not
                # recoverable from game history and must not be reset.
                current_rows = self._conn.execute(
                    "SELECT name, src_hash, mu, sigma FROM bots"
                ).fetchall()
                current = {str(row["name"]): row for row in current_rows}
                pending_names = {
                    name
                    for _source_id, game, _fingerprint, _replay, _log in pending
                    for name in (game.a, game.b)
                }
                ratings: dict[str, Rating] = {}
                for name in pending_names:
                    row = current.get(name)
                    if row is None:
                        raise StoreImportError(
                            f"destination bot {name!r} disappeared before import"
                        )
                    if str(row["src_hash"]) != expected_hashes[name]:
                        raise StoreImportError(
                            f"source hash for {name!r} changed before import"
                        )
                    ratings[name] = Rating(float(row["mu"]), float(row["sigma"]))

                # Recheck provenance after taking the write lock. This matters if
                # another importer raced this process between preview and commit.
                for source_id, _game, fingerprint, _replay, _log in pending:
                    duplicate = self._conn.execute(
                        "SELECT source_game_hash FROM game_imports "
                        "WHERE source_key = ? AND source_game_id = ?",
                        (key, source_id),
                    ).fetchone()
                    if duplicate is not None:
                        if str(duplicate["source_game_hash"]) != fingerprint:
                            raise StoreImportError(
                                f"source game {source_id} changed during concurrent import"
                            )
                        raise StoreImportError(
                            f"source game {source_id} was imported concurrently; rerun the command"
                        )

                if pending_tags:
                    placeholders = ",".join("?" for _ in pending_tags)
                    collision = self._conn.execute(
                        "SELECT tag FROM game_batches "
                        f"WHERE tag IN ({placeholders}) LIMIT 1",
                        pending_tags,
                    ).fetchone()
                    if collision is not None:
                        raise StoreImportError(
                            f"source tag {collision['tag']!r} became reserved by a "
                            "destination-native batch"
                        )

                for source_id, game, fingerprint, source_replay, source_log in pending:
                    before_a = ratings[game.a]
                    before_b = ratings[game.b]
                    after_a, after_b = rater.update(before_a, before_b, game.winner or "draw")
                    game.a_mu_before, game.a_sigma_before = before_a.mu, before_a.sigma
                    game.a_mu_after, game.a_sigma_after = after_a.mu, after_a.sigma
                    game.b_mu_before, game.b_sigma_before = before_b.mu, before_b.sigma
                    game.b_mu_after, game.b_sigma_after = after_b.mu, after_b.sigma

                    destination_id = self._insert_game(game)
                    replay_name = ""
                    log_name = ""
                    if source_replay is not None:
                        suffix = "".join(source_replay.suffixes) or ".replay26"
                        replay_name = f"{destination_id}{suffix}"
                        replay_path = Path(replay_dir) / replay_name
                        _copy_artifact(source_replay, replay_path)
                        created_files.append(replay_path)
                    if source_log is not None:
                        suffix = "".join(source_log.suffixes) or ".log"
                        log_name = f"{destination_id}{suffix}"
                        log_path = Path(log_dir) / log_name
                        _copy_artifact(source_log, log_path)
                        created_files.append(log_path)
                    if replay_name or log_name:
                        self._conn.execute(
                            "UPDATE games SET replay = ?, log = ? WHERE id = ?",
                            (replay_name, log_name, destination_id),
                        )
                    self._conn.execute(
                        "INSERT INTO game_imports "
                        "(source_key, source_game_id, game_id, source_game_hash, source_db, imported) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            key,
                            source_id,
                            destination_id,
                            fingerprint,
                            str(source_path),
                            now_iso(),
                        ),
                    )
                    ratings[game.a], ratings[game.b] = after_a, after_b

                updated = now_iso()
                self._conn.executemany(
                    "UPDATE bots SET mu = ?, sigma = ?, updated = ? WHERE name = ?",
                    [
                        (rating.mu, rating.sigma, updated, name)
                        for name, rating in ratings.items()
                    ],
                )
                self._conn.commit()
            except BaseException:
                # Keep the SQLite write lock until these game-id filenames are
                # gone, so another writer cannot reuse an id while stale files
                # from this failed batch still exist.
                for path in reversed(created_files):
                    try:
                        path.unlink()
                    except OSError:
                        pass
                self._conn.rollback()
                raise
            source.rollback()
            return report
        except StoreImportError:
            raise
        except sqlite3.Error as exc:
            raise StoreImportError(f"database import failed: {exc}") from exc
        except OSError as exc:
            raise StoreImportError(f"artifact import failed: {exc}") from exc
        finally:
            if source is not None:
                source.close()

    # -- aggregates --------------------------------------------------------
    @_locked
    def record(
        self,
        name: str,
        *,
        rated_only: bool = False,
        source_hash: str | None = None,
    ) -> Record:
        """Overall W/L/D over decided games, optionally restricted to rated play.

        The default keeps bot-detail and diagnostic views as complete history.
        Ladder callers pass ``rated_only=True`` so their empirical record covers
        rated results, and ``source_hash`` so an edited bot starts a fresh
        visible record without deleting its historical games.
        """
        rec = Record()
        rated_clause = " AND rated = 1" if rated_only else ""
        source_clause, source_params = _bot_source_clause(name, source_hash)
        rows = self._conn.execute(
            "SELECT CASE WHEN a = ? THEN 'a' ELSE 'b' END AS side, winner, COUNT(*) AS n "
            f"FROM games WHERE {_DECIDED}{rated_clause} "
            f"AND {source_clause} GROUP BY side, winner",
            (name, *source_params),
        ).fetchall()
        for r in rows:
            _tally(rec, r["side"], r["winner"], int(r["n"]))
        return rec

    @_locked
    def last_played(self, name: str, *, source_hash: str | None = None) -> str | None:
        """Timestamp of ``name``'s newest game, optionally for one source hash."""
        source_clause, source_params = _bot_source_clause(name, source_hash)
        row = self._conn.execute(
            f"SELECT ts FROM games WHERE {source_clause} ORDER BY id DESC LIMIT 1",
            source_params,
        ).fetchone()
        return str(row["ts"]) if row is not None else None

    @_locked
    def head_to_head(self, name: str) -> dict[str, Record]:
        """``opponent -> record`` from ``name``'s point of view."""
        out: dict[str, Record] = {}
        rows = self._conn.execute(
            "SELECT CASE WHEN a = ? THEN b ELSE a END AS opp, "
            "CASE WHEN a = ? THEN 'a' ELSE 'b' END AS side, winner, COUNT(*) AS n "
            f"FROM games WHERE {_DECIDED} AND (a = ? OR b = ?) GROUP BY opp, side, winner",
            (name, name, name, name),
        ).fetchall()
        for r in rows:
            _tally(out.setdefault(r["opp"], Record()), r["side"], r["winner"], int(r["n"]))
        return out

    @_locked
    def matrix(self, names: Sequence[str]) -> dict[str, dict[str, Record]]:
        """Full crosstable over ``names``; ``cells[a][b]`` is a's record against b."""
        wanted = set(names)
        cells: dict[str, dict[str, Record]] = {
            x: {y: Record() for y in names} for x in names
        }
        rows = self._conn.execute(
            f"SELECT a, b, winner, COUNT(*) AS n FROM games WHERE {_DECIDED} "
            "GROUP BY a, b, winner"
        ).fetchall()
        for r in rows:
            a, b = r["a"], r["b"]
            if a not in wanted or b not in wanted:
                continue
            n = int(r["n"])
            _tally(cells[a][b], "a", r["winner"], n)
            _tally(cells[b][a], "b", r["winner"], n)
        return cells

    @_locked
    def pair_counts(self) -> dict[tuple[str, str], int]:
        """How many games each unordered pair has played, decided or not.

        Deliberately *not* filtered to decided games, unlike :meth:`matrix`.
        Matchmakers use this to spread play evenly, and a pairing whose games all
        crash or time out must still count as attempted — otherwise it sits at
        zero forever and gets re-selected as eagerly as a genuinely unplayed one.
        """
        out: dict[tuple[str, str], int] = {}
        for r in self._conn.execute(
            "SELECT a, b, COUNT(*) AS n FROM games WHERE a <> b GROUP BY a, b"
        ).fetchall():
            key = (r["a"], r["b"]) if r["a"] < r["b"] else (r["b"], r["a"])
            out[key] = out.get(key, 0) + int(r["n"])
        return out

    @_locked
    def map_record(self, name: str) -> dict[str, Record]:
        """``map -> record`` for one bot."""
        out: dict[str, Record] = {}
        rows = self._conn.execute(
            "SELECT map, CASE WHEN a = ? THEN 'a' ELSE 'b' END AS side, winner, COUNT(*) AS n "
            f"FROM games WHERE {_DECIDED} AND (a = ? OR b = ?) GROUP BY map, side, winner",
            (name, name, name),
        ).fetchall()
        for r in rows:
            _tally(out.setdefault(r["map"], Record()), r["side"], r["winner"], int(r["n"]))
        return out

    @_locked
    def pair_map_record(self, first: str, second: str) -> dict[str, Record]:
        """``map -> record`` for ``first`` against exactly ``second``.

        This is intentionally narrower than :meth:`map_record`: the Games
        pairing view must not make one bot look strong on a map because it beat
        somebody else there.  Each record is from ``first``'s perspective;
        callers can invert it for ``second`` without another query.
        """
        out: dict[str, Record] = {}
        rows = self._conn.execute(
            "SELECT map, a, b, winner, COUNT(*) AS n FROM games "
            f"WHERE {_DECIDED} AND ((a = ? AND b = ?) OR (a = ? AND b = ?)) "
            "GROUP BY map, a, b, winner",
            (first, second, second, first),
        ).fetchall()
        for r in rows:
            side = "a" if r["a"] == first else "b"
            _tally(out.setdefault(r["map"], Record()), side, r["winner"], int(r["n"]))
        return out

    @_locked
    def error_count(
        self, name: str, *, source_hash: str | None = None
    ) -> tuple[int, int]:
        """``(error games, attributed bot errors)``, optionally for one version.

        An error is one uncaught runtime traceback or one validation/load
        failure, counted on the responsible side.
        """
        source_clause, source_params = _bot_source_clause(name, source_hash)
        row = self._conn.execute(
            "SELECT "
            " SUM(CASE WHEN (a = ? AND a_errors > 0) OR (b = ? AND b_errors > 0)"
            "          THEN 1 ELSE 0 END) AS g, "
            " SUM((CASE WHEN a = ? THEN a_errors ELSE 0 END)"
            "   + (CASE WHEN b = ? THEN b_errors ELSE 0 END)) AS n "
            f"FROM games WHERE {source_clause}",
            (name, name, name, name, *source_params),
        ).fetchone()
        return int(row["g"] or 0), int(row["n"] or 0)

    @_locked
    def rating_history(self, name: str, limit: int | None = None) -> list[dict]:
        """Rating after each rated game the bot played, oldest first.

        The series is prefixed with the bot's rating *before* the first game in
        the window so a chart starts from a real point rather than the first
        update. ``None`` keeps the complete history; a positive ``limit`` is
        available only to a caller that deliberately wants a recent window. If
        the bot has no rated games the list holds just that point.
        """
        sql = (
            "WITH rated_games AS ("
            " SELECT games.*, ROW_NUMBER() OVER (ORDER BY id) AS game_no"
            " FROM games WHERE rated = 1"
            ") "
            "SELECT id, game_no, ts, "
            " CASE WHEN a = ? THEN a_mu_before ELSE b_mu_before END AS mu0, "
            " CASE WHEN a = ? THEN a_sigma_before ELSE b_sigma_before END AS sigma0, "
            " CASE WHEN a = ? THEN a_mu_after ELSE b_mu_after END AS mu, "
            " CASE WHEN a = ? THEN a_sigma_after ELSE b_sigma_after END AS sigma "
            "FROM rated_games WHERE (a = ? OR b = ?) "
            "AND (CASE WHEN a = ? THEN a_mu_after ELSE b_mu_after END) IS NOT NULL "
            "ORDER BY game_no DESC"
        )
        params: tuple[object, ...] = (name, name, name, name, name, name, name)
        if limit is not None:
            sql += " LIMIT ?"
            params += (max(1, int(limit)),)
        rows = self._conn.execute(sql, params).fetchall()
        rows = list(reversed(rows))

        def point(gid: int, ts: str, mu: float, sigma: float) -> dict:
            return {
                "game": gid,
                "ts": ts,
                "mu": float(mu),
                "sigma": float(sigma),
                "score": float(mu) - CI * float(sigma),
            }

        if not rows:
            bot = self.get_bot(name)
            if bot is None:
                return []
            return [point(0, bot.created, bot.mu, bot.sigma)]

        first = rows[0]
        mu0 = first["mu0"] if first["mu0"] is not None else first["mu"]
        sigma0 = first["sigma0"] if first["sigma0"] is not None else first["sigma"]
        # Histories use the ordinal of the global rated game as their horizontal
        # coordinate.  A database id is not equivalent: unrated attempts consume
        # ids, and old SQLite sequences can survive a history reset.
        # The initial estimate belongs immediately before this bot's first
        # rated game, rather than at an artificial global game zero.
        out = [point(max(0, int(first["game_no"]) - 1), first["ts"], mu0, sigma0)]
        out.extend(
            point(int(r["game_no"]), r["ts"], r["mu"], r["sigma"]) for r in rows
        )
        return out

    @_locked
    def map_play_counts(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT map, COUNT(*) AS n FROM games GROUP BY map").fetchall()
        return {r["map"]: int(r["n"]) for r in rows}

    @_locked
    def recent_crashes(self, name: str, limit: int = 5) -> list[Game]:
        """The bot's own recent load failures and runtime exceptions.

        A failed game is not automatically this bot's crash: ``loadfail_a``
        belongs only to side A, ``loadfail_b`` only to B, ``loadfail_both`` to
        both, and turn tracebacks are already attributed in the per-side error
        counters. Unattributed engine/process failures are deliberately omitted
        rather than blaming both opponents in their bot-detail panels.
        """
        rows = self._conn.execute(
            "SELECT * FROM games WHERE "
            "(a = ? AND (status IN ('loadfail_a', 'loadfail_both') OR a_errors > 0)) OR "
            "(b = ? AND (status IN ('loadfail_b', 'loadfail_both') OR b_errors > 0)) "
            "ORDER BY id DESC LIMIT ?",
            (name, name, int(limit)),
        ).fetchall()
        return [_game_from_row(r) for r in rows]

    # -- maintenance -------------------------------------------------------
    @_write_locked
    def recompute(self, rater: Rater) -> None:
        """Rebuild every rating by replaying the rated games in id order.

        The per-game ``*_mu_before``/``*_after`` columns are rewritten as the
        replay proceeds, so the history charts keep matching the final ladder.
        Bots with no rated games fall back to ``rater.initial()``.
        """

        ratings: dict[str, Rating] = {b.name: rater.initial() for b in self.bots()}
        rows = self._conn.execute(
            "SELECT id, a, b, winner FROM games WHERE rated = 1 ORDER BY id"
        ).fetchall()
        for r in rows:
            a, b = r["a"], r["b"]
            if a == b:  # a bot playing itself carries no rating signal
                continue
            ra = ratings.setdefault(a, rater.initial())
            rb = ratings.setdefault(b, rater.initial())
            na, nb = rater.update(ra, rb, r["winner"] or "draw")
            self._conn.execute(
                "UPDATE games SET a_mu_before = ?, a_sigma_before = ?, a_mu_after = ?,"
                " a_sigma_after = ?, b_mu_before = ?, b_sigma_before = ?, b_mu_after = ?,"
                " b_sigma_after = ? WHERE id = ?",
                (
                    ra.mu,
                    ra.sigma,
                    na.mu,
                    na.sigma,
                    rb.mu,
                    rb.sigma,
                    nb.mu,
                    nb.sigma,
                    int(r["id"]),
                ),
            )
            ratings[a], ratings[b] = na, nb

        ts = now_iso()
        self._conn.executemany(
            "UPDATE bots SET mu = ?, sigma = ?, updated = ? WHERE name = ?",
            [(r.mu, r.sigma, ts, name) for name, r in ratings.items()],
        )
        self._conn.commit()

    @_write_locked
    def reset(self, *, keep_bots: bool = True, rater: Rater | None = None) -> None:
        """Wipe game history.

        ``keep_bots`` keeps the bot rows (and their notes); otherwise everything
        goes. Pass ``rater`` to also put the surviving bots back on their initial
        rating and clear their broken flags — without it the stale ratings remain
        until the caller runs :meth:`recompute`.
        """
        self._conn.execute("DELETE FROM games")
        self._conn.execute("DELETE FROM game_batches")
        # A reset is a new arena epoch. Keep game URLs and database ids aligned
        # with the chart's global rated-game counter by restarting at one.
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name = 'games'")
        if keep_bots:
            if rater is not None:
                init = rater.initial()
                self._conn.execute(
                    "UPDATE bots SET mu = ?, sigma = ?, broken = 0, broken_reason = '',"
                    " updated = ?",
                    (float(init.mu), float(init.sigma), now_iso()),
                )
        else:
            self._conn.execute("DELETE FROM bots")
            self._conn.execute("DELETE FROM bot_versions")
        self._conn.commit()

    @_write_locked
    def clean(self) -> None:
        """Empty every arena table and reset their SQLite row counters.

        This is the server-safe form of a complete reset: the active connection
        remains open, then league discovery recreates rows solely from bots/.
        """
        self._conn.execute("DELETE FROM games")
        self._conn.execute("DELETE FROM game_batches")
        self._conn.execute("DELETE FROM league_meta")
        self._conn.execute("DELETE FROM bot_versions")
        self._conn.execute("DELETE FROM bots")
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('games', 'bot_versions')")
        self._conn.commit()
        self._conn.execute("VACUUM")

    @_locked
    def replay_files(self) -> list[tuple[int, str]]:
        """``(game_id, filename)`` for every retained replay, newest first."""
        rows = self._conn.execute(
            "SELECT id, replay FROM games WHERE replay <> '' ORDER BY id DESC"
        ).fetchall()
        return [(int(r["id"]), r["replay"]) for r in rows]

    @_locked
    def log_files(self) -> list[tuple[int, str]]:
        """``(game_id, filename)`` for every retained log, newest first."""
        rows = self._conn.execute(
            "SELECT id, log FROM games WHERE log <> '' ORDER BY id DESC"
        ).fetchall()
        return [(int(r["id"]), r["log"]) for r in rows]

    @_write_locked
    def clear_replay(self, gid: int) -> None:
        self._conn.execute("UPDATE games SET replay = '' WHERE id = ?", (int(gid),))
        self._conn.commit()

    @_write_locked
    def clear_log(self, gid: int) -> None:
        self._conn.execute("UPDATE games SET log = '' WHERE id = ?", (int(gid),))
        self._conn.commit()
