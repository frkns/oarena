"""Persistent, low-rate observations of official FCode bot versions.

The public ladder does not expose submission versions or upload timestamps.
Match records do expose the version each team played, so Oarena keeps those
normalized observations and derives version transitions from match time. The
resulting timestamps are deliberately named ``first_seen``: for teams other
than the signed-in team, the platform does not reveal the exact upload.

Both ladder and unrated matches are observed. Ladder games arrive in ~10 minute
rounds that only a fraction of teams play, so unrated games -- which run
continuously -- materially sharpen when a version change is placed. A match may
pin one side to a historical submission (`source_match_*_id`), and that side's
version says nothing about what is active now, so pinned sides are skipped
individually rather than discarding the whole match with them.
"""

from __future__ import annotations

import fcntl
import math
import os
import sqlite3
import stat
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

__all__ = ["PlatformVersionHistory"]


_PAGE_LIMIT = 100
_HISTORY_LIMIT = 8
_MATCH_TYPES = ("ladder", "unrated")
# How far back a fresh install (or a newly observed match type) reaches.
_BACKFILL_WINDOW_S = 2.0 * 24.0 * 60.0 * 60.0
# Paging backwards is spread over refresh cycles so one catch-up never turns
# into a burst of upstream requests.
_BACKFILL_PAGES_PER_CYCLE = 20
_BACKFILL_MAX_PAGES = 400
_MAX_RUN_GAMES = 500
# A match still without an outcome this long after it started was recorded
# before outcomes were tracked, rather than being genuinely unfinished.
_RESULT_SETTLE_S = 3600.0
_ERROR_RETRY_S = 60.0
_STALE_SYNC_S = 10.0 * 60.0
_MAX_NAME = 200
_MAX_ERROR = 300
_MAX_TEAM_HISTORY_LIMIT = 200
_RUNS_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS version_observations (
  match_id         TEXT NOT NULL,
  team_id          TEXT NOT NULL,
  team_name        TEXT NOT NULL DEFAULT '',
  version          INTEGER NOT NULL CHECK (version > 0),
  match_at         REAL NOT NULL,
  observed_at      REAL NOT NULL,
  match_type       TEXT NOT NULL DEFAULT 'ladder',
  opponent_team_id TEXT,
  opponent_name    TEXT,
  opponent_version INTEGER,
  result           TEXT,
  score_for        INTEGER,
  score_against    INTEGER,
  PRIMARY KEY (match_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_version_observations_team_time
  ON version_observations(team_id, match_at, match_id);

CREATE TABLE IF NOT EXISTS version_runs (
  team_id          TEXT NOT NULL,
  ordinal          INTEGER NOT NULL,
  version          INTEGER NOT NULL CHECK (version > 0),
  first_seen_at    REAL NOT NULL,
  last_seen_at     REAL NOT NULL,
  transition_known INTEGER NOT NULL CHECK (transition_known IN (0, 1)),
  PRIMARY KEY (team_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_version_runs_team_ordinal
  ON version_runs(team_id, ordinal);

-- How far back each match type has been paged, so a newly observed type
-- backfills itself instead of needing a manual catch-up.
-- Paging progress only. How far back a type reaches is read from the
-- observations themselves, so it cannot drift from what is actually stored,
-- and how far back is *wanted* is a live setting -- widening the window
-- reopens the backfill on its own.
CREATE TABLE IF NOT EXISTS version_backfill (
  match_type TEXT PRIMARY KEY,
  cursor     TEXT NOT NULL DEFAULT '',
  pages_used INTEGER NOT NULL DEFAULT 0,
  walked_to  REAL,
  exhausted  INTEGER NOT NULL DEFAULT 0,
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS version_sync_state (
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  initialized      INTEGER NOT NULL DEFAULT 0,
  last_started_at  REAL,
  last_finished_at REAL,
  last_success_at  REAL,
  runs_schema_version INTEGER NOT NULL DEFAULT 0,
  last_error       TEXT NOT NULL DEFAULT ''
);
INSERT OR IGNORE INTO version_sync_state (id) VALUES (1);
"""


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return str(parsed)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _score_int(value: Any) -> int | None:
    """Game counts, where zero is a real score and not a missing one."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _name(value: Any) -> str | None:
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return None
    clean = " ".join(value.split())
    return clean if len(clean) <= _MAX_NAME else None


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        result = parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _iso(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


class PlatformVersionHistory:
    """Store ladder-match version observations and refresh them at low rate."""

    def __init__(
        self,
        db_path: str | Path,
        platform: Any,
        *,
        clock: Callable[[], float] = time.time,
        refresh_interval_s: float = 300.0,
        initial_pages: int = 5,
        backfill_window_s: float = _BACKFILL_WINDOW_S,
        backfill_pages_per_cycle: int = _BACKFILL_PAGES_PER_CYCLE,
    ) -> None:
        self.path = Path(db_path)
        self.platform = platform
        self._clock = clock
        self._refresh_interval_s = max(30.0, float(refresh_interval_s))
        self._initial_pages = max(1, min(20, int(initial_pages)))
        self._backfill_window_s = max(0.0, float(backfill_window_s))
        self._backfill_pages_per_cycle = max(
            1, min(_BACKFILL_MAX_PAGES, int(backfill_pages_per_cycle))
        )
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._conn_closed = False

        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path), timeout=10.0, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            sync_columns = {
                str(row["name"])
                for row in self._conn.execute(
                    "PRAGMA table_info(version_sync_state)"
                ).fetchall()
            }
            if "last_success_at" not in sync_columns:
                self._conn.execute(
                    "ALTER TABLE version_sync_state ADD COLUMN last_success_at REAL"
                )
            if "runs_schema_version" not in sync_columns:
                self._conn.execute(
                    "ALTER TABLE version_sync_state ADD COLUMN "
                    "runs_schema_version INTEGER NOT NULL DEFAULT 0"
                )
            observation_columns = {
                str(row["name"])
                for row in self._conn.execute(
                    "PRAGMA table_info(version_observations)"
                ).fetchall()
            }
            for column, decl in (
                ("match_type", "TEXT NOT NULL DEFAULT 'ladder'"),
                ("opponent_team_id", "TEXT"),
                ("opponent_name", "TEXT"),
                ("opponent_version", "INTEGER"),
                ("result", "TEXT"),
                ("score_for", "INTEGER"),
                ("score_against", "INTEGER"),
            ):
                if column not in observation_columns:
                    self._conn.execute(
                        f"ALTER TABLE version_observations ADD COLUMN {column} {decl}"
                    )
            # Every row written before this schema was a ladder match by
            # construction, so the default is a fact rather than a guess.
            self._seed_backfill_coverage_locked()
            materialized = self._conn.execute(
                "SELECT runs_schema_version FROM version_sync_state WHERE id = 1"
            ).fetchone()
            if (
                not materialized
                or int(materialized["runs_schema_version"]) < _RUNS_SCHEMA_VERSION
            ):
                team_ids = {
                    str(row["team_id"])
                    for row in self._conn.execute(
                        "SELECT DISTINCT team_id FROM version_observations"
                    ).fetchall()
                }
                self._rebuild_runs_locked(team_ids)
                self._conn.execute(
                    "UPDATE version_sync_state SET runs_schema_version = ? "
                    "WHERE id = 1",
                    (_RUNS_SCHEMA_VERSION,),
                )
        if str(self.path) != ":memory:":
            try:
                os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

    _BACKFILL_COLUMNS = frozenset(
        {"match_type", "cursor", "pages_used", "walked_to", "exhausted", "updated_at"}
    )

    def _seed_backfill_coverage_locked(self) -> None:
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_version_observations_type_time "
            "ON version_observations(match_type, match_at)"
        )
        # This table holds nothing but resumable paging progress -- every fact
        # it reports is read back from the observations. An older shape is
        # therefore cheaper to discard than to migrate: the next cycle simply
        # pages again, and nothing observed is lost.
        columns = {
            str(row["name"])
            for row in self._conn.execute(
                "PRAGMA table_info(version_backfill)"
            ).fetchall()
        }
        if columns and columns != self._BACKFILL_COLUMNS:
            self._conn.execute("DROP TABLE version_backfill")
            self._conn.execute(
                "CREATE TABLE version_backfill ("
                "match_type TEXT PRIMARY KEY, cursor TEXT NOT NULL DEFAULT '', "
                "pages_used INTEGER NOT NULL DEFAULT 0, walked_to REAL, "
                "exhausted INTEGER NOT NULL DEFAULT 0, updated_at REAL)"
            )
        for match_type in _MATCH_TYPES:
            self._conn.execute(
                "INSERT OR IGNORE INTO version_backfill "
                "(match_type, cursor, pages_used, exhausted, updated_at) "
                "VALUES (?,'',0,0,?)",
                (match_type, self._clock()),
            )

    def _covered_from_locked(self, match_type: str) -> float | None:
        """The oldest match already stored for a type, read from the rows."""
        row = self._conn.execute(
            "SELECT MIN(match_at) AS oldest FROM version_observations "
            "WHERE match_type = ?",
            (match_type,),
        ).fetchone()
        if row is None or row["oldest"] is None:
            return None
        return float(row["oldest"])

    def _missing_results_locked(self, match_type: str, target: float) -> int:
        """Rows inside the window that finished but whose outcome was never read.

        Reaching far enough back is not the only thing that makes a window
        usable: a run expanded into its games is not much use if every result
        is blank. Settled matches missing an outcome are therefore work too.
        """
        row = self._conn.execute(
            "SELECT COUNT(*) AS missing FROM version_observations "
            "WHERE match_type = ? AND result IS NULL AND match_at >= ? "
            "AND match_at <= ?",
            (match_type, target, self._clock() - _RESULT_SETTLE_S),
        ).fetchone()
        return int(row["missing"]) if row is not None else 0

    # -- public API -------------------------------------------------

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.25)
        # Platform I/O is not interruptible. Do not hold a hot reload behind
        # its timeout: a daemon worker may retain this tiny private connection
        # until it returns, while the old process is free to exit immediately.
        if thread is not None and thread.is_alive():
            return
        with self._lock:
            if self._conn_closed:
                return
            self._conn.close()
            self._conn_closed = True

    def observe_matches(self, rows: Sequence[Any] | None) -> int:
        """Persist normalized matches; return newly accepted team observations."""

        with self._lifecycle_lock:
            self._require_open()
        observations = self._normalize_observations(rows)
        if not observations:
            return 0
        columns = (
            "match_id",
            "team_id",
            "team_name",
            "version",
            "match_at",
            "observed_at",
            "match_type",
            "opponent_team_id",
            "opponent_name",
            "opponent_version",
            "result",
            "score_for",
            "score_against",
        )
        placeholders = ",".join("?" for _ in columns)
        with self._lock, self._conn:
            inserted = 0
            affected: set[str] = set()
            for observation in observations:
                values = tuple(observation[column] for column in columns)
                cursor = self._conn.execute(
                    f"INSERT OR IGNORE INTO version_observations "
                    f"({','.join(columns)}) VALUES ({placeholders})",
                    values,
                )
                if cursor.rowcount > 0:
                    inserted += 1
                    affected.add(str(observation["team_id"]))
                elif observation["result"] is not None:
                    # A match first seen while queued or running has no outcome
                    # yet. Let the result settle later without touching version
                    # or timing, which are fixed when the match is created and
                    # are the only fields runs are derived from.
                    self._conn.execute(
                        "UPDATE version_observations SET result = ?, "
                        "score_for = ?, score_against = ? "
                        "WHERE match_id = ? AND team_id = ? AND result IS NULL",
                        (
                            observation["result"],
                            observation["score_for"],
                            observation["score_against"],
                            observation["match_id"],
                            observation["team_id"],
                        ),
                    )
            self._rebuild_runs_locked(affected)
        return inserted

    def enrich_ladder(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        """Return a copied ladder payload annotated with observed version runs."""

        with self._lifecycle_lock:
            self._require_open()
        source = payload if isinstance(payload, Mapping) else {}
        raw_rankings = source.get("rankings")
        rankings = list(raw_rankings) if isinstance(raw_rankings, list) else []
        team_ids = {
            canonical
            for row in rankings
            if isinstance(row, Mapping)
            if (canonical := _canonical_uuid(row.get("team_id"))) is not None
        }
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if team_ids:
            placeholders = ",".join("?" for _ in team_ids)
            with self._lock:
                records = self._conn.execute(
                    "SELECT team_id, ordinal, version, first_seen_at, last_seen_at, "
                    "transition_known FROM version_runs "
                    f"WHERE team_id IN ({placeholders}) ORDER BY team_id, ordinal",
                    tuple(sorted(team_ids)),
                ).fetchall()
            for record in records:
                grouped[str(record["team_id"])].append(
                    {
                        "ordinal": int(record["ordinal"]),
                        "version": int(record["version"]),
                        "first_seen_at": _iso(float(record["first_seen_at"])),
                        "last_seen_at": _iso(float(record["last_seen_at"])),
                        "transition_known": bool(record["transition_known"]),
                    }
                )

        enriched: list[Any] = []
        for raw in rankings:
            if not isinstance(raw, Mapping):
                enriched.append(raw)
                continue
            row = dict(raw)
            team_id = _canonical_uuid(row.get("team_id"))
            runs = grouped.get(team_id or "", [])
            if runs:
                current = runs[-1]
                row.update(
                    {
                        "bot_version": current["version"],
                        "version_first_seen_at": current["first_seen_at"],
                        "version_last_seen_at": current["last_seen_at"],
                        "version_transition_known": current["transition_known"],
                        "versions_observed": len({run["version"] for run in runs}),
                        "version_history": list(reversed(runs[-_HISTORY_LIMIT:])),
                    }
                )
            else:
                row.update(
                    {
                        "bot_version": None,
                        "version_first_seen_at": None,
                        "version_last_seen_at": None,
                        "version_transition_known": False,
                        "versions_observed": 0,
                        "version_history": [],
                    }
                )
            enriched.append(row)
        result = dict(source)
        result["rankings"] = enriched
        return result

    def history(
        self,
        *,
        team_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return saved team-version runs without contacting the platform."""

        with self._lifecycle_lock:
            self._require_open()
            if (
                isinstance(limit, bool)
                or not isinstance(limit, int)
                or not 1 <= limit <= _MAX_TEAM_HISTORY_LIMIT
            ):
                raise ValueError(
                    f"limit must be between 1 and {_MAX_TEAM_HISTORY_LIMIT}"
                )
            canonical_team_id: str | None = None
            if team_id is not None:
                canonical_team_id = _canonical_uuid(team_id)
                if canonical_team_id is None:
                    raise ValueError("team_id must be a UUID")

            where = " WHERE team_id = ?" if canonical_team_id else ""
            parameters: tuple[Any, ...] = (
                (canonical_team_id,) if canonical_team_id else ()
            )
            with self._lock:
                # Multiple queries compose one public snapshot. An explicit read
                # transaction prevents a sibling process from splitting it across
                # two observation generations while WAL keeps writers unblocked.
                self._conn.execute("BEGIN")
                try:
                    summary = self._conn.execute(
                        "SELECT COUNT(DISTINCT team_id) AS total, "
                        "MIN(match_at) AS observed_from, "
                        "MAX(match_at) AS observed_through "
                        f"FROM version_observations{where}",
                        parameters,
                    ).fetchone()
                    team_rows = self._conn.execute(
                        "SELECT grouped.team_id, grouped.observed_from, "
                        "grouped.observed_through, "
                        "(SELECT newest.team_name FROM version_observations newest "
                        "WHERE newest.team_id = grouped.team_id "
                        "ORDER BY newest.match_at DESC, newest.match_id DESC LIMIT 1) "
                        "AS team_name FROM (SELECT team_id, "
                        "MIN(match_at) AS observed_from, "
                        "MAX(match_at) AS observed_through "
                        f"FROM version_observations{where} GROUP BY team_id) grouped "
                        "ORDER BY grouped.observed_through DESC, grouped.team_id ASC "
                        "LIMIT ?",
                        (*parameters, limit),
                    ).fetchall()
                    selected_ids = [str(row["team_id"]) for row in team_rows]
                    if selected_ids:
                        placeholders = ",".join("?" for _ in selected_ids)
                        run_rows = self._conn.execute(
                            "SELECT team_id, ordinal, version, first_seen_at, "
                            "last_seen_at, transition_known FROM version_runs "
                            f"WHERE team_id IN ({placeholders}) "
                            "ORDER BY team_id ASC, ordinal DESC",
                            tuple(selected_ids),
                        ).fetchall()
                    else:
                        run_rows = []
                finally:
                    self._conn.rollback()

            grouped_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in run_rows:
                grouped_runs[str(row["team_id"])].append(
                    {
                        "ordinal": int(row["ordinal"]),
                        "version": int(row["version"]),
                        "first_seen_at": _iso(float(row["first_seen_at"])),
                        "last_seen_at": _iso(float(row["last_seen_at"])),
                        "transition_known": bool(row["transition_known"]),
                    }
                )

            teams: list[dict[str, Any]] = []
            for row in team_rows:
                selected_id = str(row["team_id"])
                runs = grouped_runs.get(selected_id, [])
                teams.append(
                    {
                        "team_id": selected_id,
                        "team_name": str(row["team_name"] or ""),
                        "current_version": runs[0]["version"] if runs else None,
                        "observed_from": _iso(float(row["observed_from"])),
                        "observed_through": _iso(float(row["observed_through"])),
                        "runs": runs,
                    }
                )

            return {
                "teams": teams,
                "total": int(summary["total"]) if summary is not None else 0,
                "observed_from": (
                    _iso(float(summary["observed_from"]))
                    if summary is not None and summary["observed_from"] is not None
                    else None
                ),
                "observed_through": (
                    _iso(float(summary["observed_through"]))
                    if summary is not None and summary["observed_through"] is not None
                    else None
                ),
            }

    def run_games(
        self, *, team_id: str, ordinal: int, limit: int = _MAX_RUN_GAMES
    ) -> dict[str, Any]:
        """Return the matches observed during one team-version run.

        Runs are recomputed here from the same observations and the same
        algorithm that materialized them, rather than reselected by version and
        time range. Ladder rounds share a timestamp to the second, so a version
        that is dropped and later reactivated could otherwise pull a neighbouring
        run's games into the list.
        """
        with self._lifecycle_lock:
            self._require_open()
            canonical = _canonical_uuid(team_id)
            if canonical is None:
                raise ValueError("team_id must be a UUID")
            if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
                raise ValueError("ordinal must be a non-negative integer")
            if (
                isinstance(limit, bool)
                or not isinstance(limit, int)
                or not 1 <= limit <= _MAX_RUN_GAMES
            ):
                raise ValueError(f"limit must be between 1 and {_MAX_RUN_GAMES}")

        with self._lock:
            rows = self._conn.execute(
                "SELECT match_id, version, match_at, match_type, opponent_team_id, "
                "opponent_name, opponent_version, result, score_for, score_against "
                "FROM version_observations WHERE team_id = ? "
                "ORDER BY match_at, match_id",
                (canonical,),
            ).fetchall()

        index = -1
        previous: int | None = None
        selected: list[sqlite3.Row] = []
        for row in rows:
            version = int(row["version"])
            if previous is None or version != previous:
                index += 1
                previous = version
            if index == ordinal:
                selected.append(row)
            elif index > ordinal:
                break

        settled_by = self._clock() - _RESULT_SETTLE_S
        games = [
            {
                "match_id": str(row["match_id"]),
                "match_at": _iso(float(row["match_at"])),
                "match_type": str(row["match_type"] or "ladder"),
                "version": int(row["version"]),
                "opponent_team_id": row["opponent_team_id"],
                "opponent_name": row["opponent_name"],
                "opponent_version": row["opponent_version"],
                # A blank outcome on a long-finished match was never recorded,
                # and saying "running" about a match from last week would be
                # simply untrue. Only recent blanks are genuinely undecided.
                "result": (
                    row["result"]
                    if row["result"] is not None
                    else ("unknown" if float(row["match_at"]) <= settled_by else None)
                ),
                "score_for": row["score_for"],
                "score_against": row["score_against"],
            }
            # Newest first, matching how the timeline itself is ordered.
            for row in reversed(selected)
        ]
        record = {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "undecided": 0,
            "unknown": 0,
        }
        for game in games:
            if game["result"] == "win":
                record["wins"] += 1
            elif game["result"] == "loss":
                record["losses"] += 1
            elif game["result"] == "draw":
                record["draws"] += 1
            elif game["result"] == "unknown":
                record["unknown"] += 1
            else:
                record["undecided"] += 1
        return {
            "team_id": canonical,
            "ordinal": ordinal,
            "version": selected[0]["version"] if selected else None,
            "total": len(games),
            "truncated": len(games) > limit,
            "record": record,
            "games": games[:limit],
        }

    def match_runs(self, *, match_id: str) -> dict[str, Any]:
        """Which version each team played in one match, and the run it belongs to.

        FCode's match *detail* response carries no team versions -- only the
        match list does -- so a match opened by ID cannot say what was played.
        Oarena already recorded it per match when the list went by, and walking
        the team's own series identifies the run by position rather than by
        timestamp, which stays exact even where a whole ladder round shares one.
        """
        with self._lifecycle_lock:
            self._require_open()
            canonical = _canonical_uuid(match_id)
            if canonical is None:
                raise ValueError("match_id must be a UUID")

        with self._lock:
            observed = self._conn.execute(
                "SELECT team_id, version FROM version_observations "
                "WHERE match_id = ? ORDER BY team_id",
                (canonical,),
            ).fetchall()
            teams = []
            for row in observed:
                team_id = str(row["team_id"])
                series = self._conn.execute(
                    "SELECT match_id, version FROM version_observations "
                    "WHERE team_id = ? ORDER BY match_at, match_id",
                    (team_id,),
                ).fetchall()
                ordinal = None
                index = -1
                previous: int | None = None
                for entry in series:
                    version = int(entry["version"])
                    if previous is None or version != previous:
                        index += 1
                        previous = version
                    if str(entry["match_id"]) == canonical:
                        ordinal = index
                        break
                teams.append(
                    {
                        "team_id": team_id,
                        "version": int(row["version"]),
                        "ordinal": ordinal,
                    }
                )
        return {"match_id": canonical, "teams": teams}

    def request_refresh(self, *, platform: Any | None = None) -> dict[str, Any]:
        """Start one bounded global ladder-history refresh when its cadence is due."""

        with self._lifecycle_lock:
            self._require_open()
            if platform is not None:
                self.platform = platform
            status = self._status_locked()
            local_active = self._thread is not None and self._thread.is_alive()
            if local_active or (not status["syncing"] and not status["due"]):
                return {**status, "started": False}
            # Claim the process-wide file lock before changing persisted state.
            # A hot-reload sibling can therefore neither duplicate nor queue a
            # second upstream refresh behind the first one.
            descriptor = self._acquire_refresh_lock(nonblocking=True)
            if descriptor is None:
                return {**self._status_locked(), "started": False}
            claimed = False
            try:
                # Owning the file lock proves no other live worker owns a stale
                # database claim left by a crashed process.
                self._clear_refresh_claim()
                status = self._status_locked()
                if status["syncing"] or not status["due"]:
                    self._release_refresh_lock(descriptor)
                    return {**status, "started": False}
                now = self._clock()
                with self._lock, self._conn:
                    self._conn.execute(
                        "UPDATE version_sync_state SET last_started_at = ? "
                        "WHERE id = 1",
                        (now,),
                    )
                claimed = True
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._refresh_worker,
                    args=(descriptor,),
                    name="oarena-platform-versions",
                    daemon=True,
                )
                self._thread.start()
            except Exception:
                if claimed:
                    self._clear_refresh_claim()
                self._release_refresh_lock(descriptor)
                raise
            return {**self._status_locked(), "started": True}

    def status(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._require_open()
            status = self._status_locked()
            local_active = self._thread is not None and self._thread.is_alive()
            if status["syncing"] and not local_active:
                # A hot-reloaded process may die after persisting its claim but
                # before its daemon worker can clear it. The OS releases its
                # flock; acquiring that lock proves the claim is orphaned.
                descriptor = self._acquire_refresh_lock(nonblocking=True)
                if descriptor is not None:
                    try:
                        self._clear_refresh_claim()
                        status = self._status_locked()
                    finally:
                        self._release_refresh_lock(descriptor)
            return {**status, "started": False}

    # -- observations ------------------------------------------------

    def _normalize_observations(
        self, rows: Sequence[Any] | None
    ) -> list[dict[str, Any]]:
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return []
        now = self._clock()
        normalized: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            match_type = raw.get("type")
            if match_type not in _MATCH_TYPES:
                continue
            match_id = _canonical_uuid(raw.get("id"))
            match_at = _epoch(raw.get("created_at"))
            if match_at is None:
                match_at = _epoch(raw.get("completed_at"))
            if match_id is None or match_at is None:
                continue
            winner_id = _canonical_uuid(raw.get("winner_id"))
            decided = raw.get("status") == "complete"
            sides = {}
            for side in ("a", "b"):
                team = raw.get(f"team_{side}")
                if not isinstance(team, Mapping):
                    sides = {}
                    break
                team_id = _canonical_uuid(team.get("id"))
                team_name = _name(team.get("name"))
                if team_id is None or team_name is None:
                    sides = {}
                    break
                sides[side] = (team_id, team_name, _positive_int(team.get("version")))
            if len(sides) != 2:
                continue
            for side, (team_id, team_name, version) in sides.items():
                # A pinned side replayed an old submission, so its version says
                # nothing about what that team is running now. Skip just that
                # side: the other one is still a valid sighting, and a fifth of
                # unrated matches pin exactly one side.
                if raw.get(f"source_match_{side}_id") not in (None, ""):
                    continue
                if version is None:
                    continue
                other = "b" if side == "a" else "a"
                opponent_id, opponent_name, opponent_version = sides[other]
                score_for = _score_int(raw.get(f"score_{side}"))
                score_against = _score_int(raw.get(f"score_{other}"))
                if not decided:
                    result = None
                elif winner_id is None:
                    result = "draw"
                else:
                    result = "win" if winner_id == team_id else "loss"
                normalized.append(
                    {
                        "match_id": match_id,
                        "team_id": team_id,
                        "team_name": team_name,
                        "version": version,
                        "match_at": match_at,
                        "observed_at": now,
                        "match_type": str(match_type),
                        "opponent_team_id": opponent_id,
                        "opponent_name": opponent_name,
                        "opponent_version": opponent_version,
                        "result": result,
                        "score_for": score_for,
                        "score_against": score_against,
                    }
                )
        return normalized

    def _rebuild_runs_locked(self, team_ids: set[str]) -> None:
        """Materialize compact transition runs for fast ladder reads."""

        for team_id in sorted(team_ids):
            rows = self._conn.execute(
                "SELECT version, match_at FROM version_observations "
                "WHERE team_id = ? ORDER BY match_at, match_id",
                (team_id,),
            ).fetchall()
            runs = self._run_records(rows)
            self._conn.execute("DELETE FROM version_runs WHERE team_id = ?", (team_id,))
            self._conn.executemany(
                "INSERT INTO version_runs "
                "(team_id, ordinal, version, first_seen_at, last_seen_at, "
                "transition_known) VALUES (?,?,?,?,?,?)",
                (
                    (
                        team_id,
                        ordinal,
                        run["version"],
                        run["first_seen_at"],
                        run["last_seen_at"],
                        int(run["transition_known"]),
                    )
                    for ordinal, run in enumerate(runs)
                ),
            )

    @staticmethod
    def _run_records(rows: Sequence[sqlite3.Row]) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for row in rows:
            version = int(row["version"])
            match_at = float(row["match_at"])
            if not runs or runs[-1]["version"] != version:
                runs.append(
                    {
                        "version": version,
                        "first_seen_at": match_at,
                        "last_seen_at": match_at,
                        "transition_known": bool(runs),
                    }
                )
            else:
                runs[-1]["last_seen_at"] = match_at
        return runs

    # -- backfill ----------------------------------------------------

    def backfill_state(self) -> list[dict[str, Any]]:
        """Report how far back each match type has been paged."""

        with self._lifecycle_lock:
            self._require_open()
        target = self._clock() - self._backfill_window_s
        with self._lock:
            rows = self._conn.execute(
                "SELECT match_type, pages_used, walked_to, exhausted "
                "FROM version_backfill ORDER BY match_type"
            ).fetchall()
            state = [
                (
                    row,
                    self._covered_from_locked(str(row["match_type"])),
                    self._missing_results_locked(str(row["match_type"]), target),
                )
                for row in rows
            ]
        return [
            {
                "match_type": str(row["match_type"]),
                "covered_from": _iso(covered_from),
                "walked_to": _iso(
                    float(row["walked_to"]) if row["walked_to"] is not None else None
                ),
                "pages_used": int(row["pages_used"]),
                # Reported for visibility only. Some matches never reach a final
                # state upstream, so this legitimately settles above zero.
                "missing_results": missing,
                "complete": self._backfill_complete(
                    bool(row["exhausted"]),
                    float(row["walked_to"]) if row["walked_to"] is not None else None,
                    target,
                ),
                "exhausted": bool(row["exhausted"]),
                "target_from": _iso(target),
            }
            for row, covered_from, missing in state
        ]

    def _backfill_complete(
        self, exhausted: bool, walked_to: float | None, target: float
    ) -> bool:
        """Has a finished walk already covered the window that is wanted now?

        Deliberately not "are all outcomes filled in": a match that errored
        upstream never reaches a final result, so waiting for that count to hit
        zero would re-walk the same window forever. One completed walk fixes
        both coverage and outcomes; widening the window is what asks for another.
        """
        if self._backfill_window_s <= 0.0 or exhausted:
            return True
        return walked_to is not None and walked_to <= target

    def _pending_backfill_locked(self) -> list[str]:
        if self._backfill_window_s <= 0.0:
            return []
        target = self._clock() - self._backfill_window_s
        rows = self._conn.execute(
            "SELECT match_type, walked_to, exhausted FROM version_backfill "
            "WHERE pages_used < ? ORDER BY match_type",
            (_BACKFILL_MAX_PAGES,),
        ).fetchall()
        return [
            str(row["match_type"])
            for row in rows
            if not self._backfill_complete(
                bool(row["exhausted"]),
                float(row["walked_to"]) if row["walked_to"] is not None else None,
                target,
            )
        ]

    def _run_backfill(self, match_type: str) -> None:
        """Page one match type backwards from the head toward the window.

        Only a slice of pages runs per refresh cycle; the cursor is persisted so
        the next cycle resumes instead of restarting. The walk does two jobs at
        once -- reaching further back than the forward sync ever does, and
        settling outcomes for matches first seen before they finished.
        """
        target = self._clock() - self._backfill_window_s
        with self._lock:
            row = self._conn.execute(
                "SELECT cursor, pages_used FROM version_backfill WHERE match_type = ?",
                (match_type,),
            ).fetchone()
            if row is None:
                return
        # One walk serves both jobs -- extending coverage and filling in
        # outcomes -- and both run head-to-target. An empty cursor starts a
        # fresh walk at the head; otherwise this resumes the walk in progress.
        # Restarting at the head every cycle instead would re-fetch the same
        # pages forever and never reach the rest of the window.
        cursor: str | None = str(row["cursor"]) or None
        pages_used = int(row["pages_used"])
        seen_cursors: set[str] = set()
        feed_exhausted = False
        walk_complete = False
        # Only pages fetched in this walk decide when to stop; what was already
        # stored says nothing about how far this walk has got.
        oldest_seen: float | None = None
        for _ in range(self._backfill_pages_per_cycle):
            if self._stop.is_set():
                break
            if pages_used >= _BACKFILL_MAX_PAGES:
                # A safety stop, not a finished walk. `walk_complete` stays
                # false, so the status keeps reporting the window as uncovered
                # rather than quietly claiming it was read.
                break
            response = self.platform.matches(
                limit=_PAGE_LIMIT,
                match_type=match_type,
                mine=False,
                team_id=None,
                cursor=cursor,
            )
            if self._stop.is_set():
                break
            rows = response.get("matches") if isinstance(response, Mapping) else None
            if not isinstance(rows, list):
                raise ValueError("invalid match history response")
            pages_used += 1
            self.observe_matches(rows)
            for raw in rows:
                if not isinstance(raw, Mapping):
                    continue
                at = _epoch(raw.get("created_at")) or _epoch(raw.get("completed_at"))
                if at is not None and (oldest_seen is None or at < oldest_seen):
                    oldest_seen = at
            next_cursor = (
                response.get("next_cursor") if isinstance(response, Mapping) else None
            )
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in seen_cursors
            ):
                # There is nothing older to fetch. Unlike reaching the window,
                # this is permanent and no wider window can undo it.
                feed_exhausted = True
                walk_complete = True
                cursor = None
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            if oldest_seen is not None and oldest_seen <= target:
                # This walk has covered the window. Clearing the cursor ends the
                # pass, so any later one -- a widened window, or outcomes still
                # missing -- starts again at the head where the newest rows are.
                walk_complete = True
                cursor = None
                break
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE version_backfill SET cursor = ?, pages_used = ?, "
                "walked_to = CASE WHEN ? THEN ? ELSE walked_to END, "
                "exhausted = ?, updated_at = ? WHERE match_type = ?",
                (
                    cursor or "",
                    # The page budget guards one walk, not the lifetime of the
                    # database, so a finished walk hands the next one a full one.
                    0 if walk_complete else pages_used,
                    # Only a walk that ran to the end proves the window between
                    # the head and here has been re-read.
                    int(walk_complete),
                    oldest_seen if oldest_seen is not None else target,
                    int(feed_exhausted),
                    self._clock(),
                    match_type,
                ),
            )

    # -- refresh worker ---------------------------------------------

    def _refresh_worker(self, descriptor: int) -> None:
        error = ""
        success = False
        cancelled = False
        try:
            if self._stop.is_set():
                cancelled = True
                return
            with self._lock:
                state = self._conn.execute(
                    "SELECT initialized FROM version_sync_state WHERE id = 1"
                ).fetchone()
                initialized = bool(state and state["initialized"])
            pages = 1 if initialized else self._initial_pages
            # Catch up on what is new in each feed first. Ladder rounds and
            # unrated games are independent streams, and only the forward sync
            # keeps the tab current, so it always runs before any backfill.
            for match_type in _MATCH_TYPES:
                cursor: str | None = None
                seen_cursors: set[str] = set()
                for _ in range(pages):
                    if self._stop.is_set():
                        cancelled = True
                        return
                    response = self.platform.matches(
                        limit=_PAGE_LIMIT,
                        match_type=match_type,
                        mine=False,
                        team_id=None,
                        cursor=cursor,
                    )
                    if self._stop.is_set():
                        cancelled = True
                        return
                    rows = (
                        response.get("matches")
                        if isinstance(response, Mapping)
                        else None
                    )
                    if not isinstance(rows, list):
                        raise ValueError("invalid match history response")
                    self.observe_matches(rows)
                    next_cursor = (
                        response.get("next_cursor")
                        if isinstance(response, Mapping)
                        else None
                    )
                    if not isinstance(next_cursor, str) or not next_cursor:
                        break
                    if next_cursor in seen_cursors:
                        break
                    seen_cursors.add(next_cursor)
                    cursor = next_cursor
            with self._lock:
                pending = self._pending_backfill_locked()
            for match_type in pending:
                if self._stop.is_set():
                    cancelled = True
                    return
                self._run_backfill(match_type)
            success = True
        except Exception as exc:  # never expose credentials/raw upstream bodies
            if self._stop.is_set():
                cancelled = True
            else:
                error = f"refresh failed ({type(exc).__name__})"[:_MAX_ERROR]
        finally:
            if cancelled:
                self._clear_refresh_claim()
            elif not self._conn_closed:
                finished = self._clock()
                try:
                    with self._lock, self._conn:
                        self._conn.execute(
                            "UPDATE version_sync_state SET initialized = CASE WHEN ? "
                            "THEN 1 ELSE initialized END, last_finished_at = ?, "
                            "last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END, "
                            "last_error = ? WHERE id = 1",
                            (int(success), finished, int(success), finished, error),
                        )
                except sqlite3.Error:
                    pass
            self._release_refresh_lock(descriptor)
            if self._closed:
                with self._lock:
                    if not self._conn_closed:
                        self._conn.close()
                        self._conn_closed = True

    def _acquire_refresh_lock(self, *, nonblocking: bool = False) -> int | None:
        if str(self.path) == ":memory:":
            return os.open(os.devnull, os.O_RDONLY)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            operation = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
            fcntl.flock(descriptor, operation)
        except OSError:
            os.close(descriptor)
            return None
        return descriptor

    @staticmethod
    def _release_refresh_lock(descriptor: int) -> None:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(descriptor)
        except OSError:
            pass

    # -- status/lifecycle -------------------------------------------

    def _clear_refresh_claim(self) -> None:
        if self._conn_closed:
            return
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "UPDATE version_sync_state SET last_started_at = last_finished_at "
                    "WHERE id = 1 AND (last_finished_at IS NULL "
                    "OR last_started_at > last_finished_at)"
                )
        except sqlite3.Error:
            pass

    def _status_locked(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            state = self._conn.execute(
                "SELECT * FROM version_sync_state WHERE id = 1"
            ).fetchone()
        if state is None:
            return {
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
        started = (
            float(state["last_started_at"])
            if state["last_started_at"] is not None
            else None
        )
        finished = (
            float(state["last_finished_at"])
            if state["last_finished_at"] is not None
            else None
        )
        succeeded = (
            float(state["last_success_at"])
            if state["last_success_at"] is not None
            else None
        )
        persisted_active = (
            started is not None
            and (finished is None or started > finished)
            and now - started < _STALE_SYNC_S
        )
        local_active = self._thread is not None and self._thread.is_alive()
        error = str(state["last_error"] or "")
        interval = _ERROR_RETRY_S if error else self._refresh_interval_s
        next_refresh = (finished + interval) if finished is not None else now
        syncing = local_active or persisted_active
        return {
            "syncing": syncing,
            "refreshing": syncing,
            "due": not syncing and now >= next_refresh,
            "initialized": bool(state["initialized"]),
            "initial_sync_complete": bool(state["initialized"]),
            "last_sync_at": _iso(succeeded),
            "last_attempt_at": _iso(finished),
            "next_refresh_at": _iso(next_refresh),
            "last_error": error or None,
            "error": error or None,
        }

    def _require_open(self) -> None:
        if self._closed or self._conn_closed:
            raise ValueError("platform version history is closed")
