"""Durable scheduling and statistics for official FCode unrated scrims.

The HTTP server owns this coordinator and its small, separate SQLite database.
Only :class:`FcodePlatform` (or its Unix-socket client) ever sees credentials or
the network.  Persisting a request before POSTing is important because FCode's
unrated endpoint has no idempotency key: if a response is lost, Oarena records
the outcome as unknown and never guesses by issuing the challenge again.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import sqlite3
import stat
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from oarena.fcode_platform import PlatformError, rate_limit_quota

__all__ = ["ScrimCoordinator"]


# Starting guess for FCode's shared unrated-match quota. The real numbers are
# learned from the platform's own rate-limit message (see `_learn_quota`), so a
# retuned limit adjusts pacing instead of stalling autoscrim.
_RATE_LIMIT = 5
_RATE_WINDOW_S = 600.0
_RATE_SAFETY_S = 5.0
_AUTO_CADENCE_S = 125.0
_RATE_BACKOFF_S = _RATE_WINDOW_S + _RATE_SAFETY_S
_MAX_BACKOFF_S = 30.0 * 60.0
# Hitting the shared quota is routine, not a fault: back off politely and keep
# the schedule alive rather than escalating into the long failure backoff.
_RATE_ESCALATION_MAX = 2
# A plain rejection retries a different opponent on the next cycle. Autoscrim
# only stops once this many consecutive attempts fail, so one bad target (or a
# reworded upstream error) can never silently end an overnight session.
_AUTO_REJECTION_PAUSE_AFTER = 5
_AUTO_REJECTION_RETRY_S = 90.0
_UNLIMITED_TARGET_MATCHES = 0
_PENDING_POLL_S = 20.0
_IDLE_SYNC_S = 5.0 * 60.0
_PROFILE_RETRY_S = 60.0
_MAX_HISTORY_PAGES = 5
_MAX_TEXT = 512
_MAX_NAME = 200
_MAX_MAPS = 5


def _quota_wait_text(allowance: int, window_s: float) -> str:
    """Describe the shared quota in the units FCode stated it in."""
    if window_s >= 3600 and window_s % 3600 == 0:
        span = f"{int(window_s // 3600)}h"
    elif window_s >= 60:
        span = f"{int(round(window_s / 60))}min"
    else:
        span = f"{int(round(window_s))}s"
    return f"Waiting for the shared FCode quota ({allowance} per {span})"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  id                         INTEGER PRIMARY KEY CHECK (id = 1),
  enabled                    INTEGER NOT NULL DEFAULT 0,
  target_matches_per_version INTEGER NOT NULL DEFAULT 0,
  map_names_json             TEXT NOT NULL DEFAULT '[]',
  next_auto_at               REAL,
  backoff_until              REAL,
  consecutive_failures       INTEGER NOT NULL DEFAULT 0,
  last_error                 TEXT NOT NULL DEFAULT '',
  paused_reason              TEXT NOT NULL DEFAULT '',
  authenticated              INTEGER NOT NULL DEFAULT 0,
  team_id                    TEXT,
  team_name                  TEXT,
  submission_id              TEXT,
  submission_version         INTEGER,
  submission_name            TEXT,
  submission_status          TEXT,
  submission_uploaded_at     TEXT,
  profile_updated_at         REAL,
  rate_limit_max             INTEGER,
  rate_limit_window_s        REAL,
  rate_limit_seen_at         REAL,
  revision                   INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO settings (id) VALUES (1);

CREATE TABLE IF NOT EXISTS targets (
  team_id          TEXT PRIMARY KEY,
  team_name        TEXT NOT NULL DEFAULT '',
  ordinal          INTEGER NOT NULL,
  last_selected_at REAL
);

CREATE TABLE IF NOT EXISTS requests (
  request_key          TEXT PRIMARY KEY,
  source               TEXT NOT NULL CHECK (source IN ('manual', 'auto')),
  requested_at         REAL NOT NULL,
  updated_at           REAL NOT NULL,
  opponent_team_id     TEXT NOT NULL,
  opponent_team_name   TEXT NOT NULL DEFAULT '',
  source_match_id      TEXT,
  map_names_json       TEXT NOT NULL DEFAULT '[]',
  status               TEXT NOT NULL,
  not_before           REAL NOT NULL,
  attempts             INTEGER NOT NULL DEFAULT 0,
  match_id             TEXT UNIQUE,
  own_team_id          TEXT,
  own_team_name        TEXT,
  own_submission_id    TEXT,
  own_version          INTEGER,
  own_submission_name  TEXT,
  opponent_version     INTEGER,
  score_for            INTEGER,
  score_against        INTEGER,
  completed_at         REAL,
  error                TEXT NOT NULL DEFAULT '',
  last_attempt_at      REAL
);
CREATE INDEX IF NOT EXISTS idx_scrim_requests_queue
  ON requests(status, not_before, source, requested_at);
CREATE INDEX IF NOT EXISTS idx_scrim_requests_match ON requests(match_id);

CREATE TABLE IF NOT EXISTS attempts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  request_key     TEXT NOT NULL REFERENCES requests(request_key) ON DELETE CASCADE,
  started_at      REAL NOT NULL,
  finished_at     REAL,
  status          TEXT NOT NULL,
  response_code   INTEGER,
  error           TEXT NOT NULL DEFAULT '',
  match_id        TEXT,
  outcome_unknown INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scrim_attempts_started ON attempts(started_at);

CREATE TABLE IF NOT EXISTS matches (
  match_id             TEXT PRIMARY KEY,
  status               TEXT NOT NULL,
  own_team_id          TEXT NOT NULL,
  own_team_name        TEXT NOT NULL DEFAULT '',
  own_version          INTEGER,
  opponent_team_id     TEXT NOT NULL,
  opponent_team_name   TEXT NOT NULL DEFAULT '',
  opponent_version     INTEGER,
  winner_id            TEXT,
  score_for            INTEGER,
  score_against        INTEGER,
  source_match_own_id  TEXT,
  source_match_opp_id  TEXT,
  error                TEXT NOT NULL DEFAULT '',
  created_at           TEXT,
  completed_at         TEXT,
  updated_at           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scrim_matches_stats
  ON matches(own_version, opponent_team_id, status);
"""


def _canonical_uuid(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError(f"{label} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a canonical UUID") from exc
    if value != str(parsed):
        raise ValueError(f"{label} must be a canonical UUID")
    return value


def _text(value: Any, *, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _input_text(value: Any, label: str, *, limit: int = _MAX_NAME) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} contains unsupported control characters")
    value = value.strip()
    if not value or len(value) > limit:
        raise ValueError(f"{label} must contain 1 to {limit} characters")
    return value


def _map_names(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("map_names must be a list")
    if len(values) > _MAX_MAPS:
        raise ValueError(f"map_names may contain at most {_MAX_MAPS} maps")
    names: list[str] = []
    for raw in values:
        name = _input_text(raw, "map name")
        if name in names:
            raise ValueError("map_names must not contain duplicates")
        names.append(name)
    return tuple(names)


def _json_list(raw: Any) -> list[str]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else []
    except (TypeError, ValueError):
        return []
    return [_text(item, limit=_MAX_NAME) for item in value if isinstance(item, str)]


def _json_names(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _number(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _epoch_from_iso(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _iso(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


class ScrimCoordinator:
    """One durable, serialized gateway for manual and automatic scrims."""

    def __init__(
        self,
        db_path: str | Path,
        platform: Any,
        *,
        bus: Any = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(db_path)
        self.platform = platform
        self.bus = bus
        self._clock = clock
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._conn_closed = False
        self._refresh_full = False
        self._refresh_in_progress = False
        self._next_sync_at = 0.0
        self._profile_fresh = False
        self._history_fresh = False
        self._dispatch_fd: int | None = None

        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path), timeout=10.0, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # The committed `sending` row is the durability barrier before an
        # irreversible POST. Losing it on power failure could create a second
        # official match after restart, so this tiny low-write DB uses FULL.
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            existing = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(settings)")
            }
            for column, decl in (
                ("rate_limit_max", "INTEGER"),
                ("rate_limit_window_s", "REAL"),
                ("rate_limit_seen_at", "REAL"),
            ):
                if column not in existing:
                    self._conn.execute(
                        f"ALTER TABLE settings ADD COLUMN {column} {decl}"
                    )
            # Repair rows written by early scrim-tab builds: platform `queued`
            # is remote lifecycle state, never permission to POST again.
            self._conn.execute(
                "UPDATE requests SET status = 'accepted' "
                "WHERE status = 'queued' AND match_id IS NOT NULL"
            )

        if self._has_background_work():
            self._ensure_worker()

    # -- public API -------------------------------------------------

    def close(self) -> None:
        with self._lifecycle_lock:
            if not self._closed:
                self._closed = True
                self._stop.set()
                self._wake.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=65.0)
        # Never pull SQLite out from underneath a legal in-flight RPC. Stop
        # checks between calls bound normal shutdown to one 60-second RPC; an
        # injected or broken transport that ignores its timeout may leak this
        # daemon coordinator, but cannot corrupt its durable request state.
        if thread is not None and thread.is_alive():
            return
        with self._lock:
            if self._conn_closed:
                return
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn_closed = True

    def snapshot(
        self,
        *,
        limit: int = 100,
        our_version: str | int | None = None,
    ) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._require_open()
            return self._snapshot(limit=limit, our_version=our_version)

    def _snapshot(
        self,
        *,
        limit: int = 100,
        our_version: str | int | None = None,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._read_transaction():
            settings = self._settings_locked()
            team_id = settings["team_id"]
            active_version = _number(settings["submission_version"])
            if our_version in (None, "current"):
                selected_version = active_version
            elif (
                isinstance(our_version, int)
                and not isinstance(our_version, bool)
                and our_version > 0
            ):
                selected_version = our_version
            else:
                raise ValueError("our_version must be 'current' or a positive integer")
            targets = self._conn.execute(
                "SELECT team_id, team_name FROM targets ORDER BY ordinal, team_id"
            ).fetchall()
            if team_id:
                request_rows = self._conn.execute(
                    "SELECT * FROM requests WHERE own_team_id = ? "
                    "ORDER BY requested_at DESC, rowid DESC LIMIT ?",
                    (team_id, limit),
                ).fetchall()
                version_rows = self._conn.execute(
                    "SELECT DISTINCT own_version FROM matches WHERE own_team_id = ? "
                    "AND own_version IS NOT NULL ORDER BY own_version DESC",
                    (team_id,),
                ).fetchall()
            else:
                request_rows = []
                version_rows = []
            match_rows = (
                self._conn.execute(
                    "SELECT * FROM matches WHERE own_team_id = ? AND own_version = ? "
                    "AND status = 'complete'",
                    (team_id, selected_version),
                ).fetchall()
                if team_id and selected_version is not None
                else []
            )
            revision = int(settings["revision"])
            auto_pending = self._conn.execute(
                "SELECT match_id FROM requests WHERE source = 'auto' "
                "AND own_team_id = ? "
                "AND status IN ('queued', 'sending', 'accepted', 'running') "
                "ORDER BY requested_at LIMIT 1",
                (team_id,),
            ).fetchone()
            queued = self._conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status = 'queued' "
                "AND own_team_id = ?",
                (team_id,),
            ).fetchone()[0]
            sending = self._conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status = 'sending' "
                "AND own_team_id = ?",
                (team_id,),
            ).fetchone()[0]
            now = self._clock()
            state = self._state_label(
                settings,
                now=now,
                queued=int(queued),
                sending=int(sending),
                selected_version=active_version,
            )
            summary, opponents = self._statistics(match_rows, selected_version)
            quota_limit, quota_window = self._quota_locked()
            quota_learned = settings["rate_limit_seen_at"] is not None
            quota_used = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM attempts WHERE status <> 'retrying' "
                    "AND COALESCE(finished_at, started_at) > ?",
                    (now - quota_window,),
                ).fetchone()[0]
            )

        target_ids = [str(row["team_id"]) for row in targets]
        target_names = {
            str(row["team_id"]): str(row["team_name"])
            for row in targets
            if row["team_name"]
        }
        backoff_until = settings["backoff_until"]
        paused = str(settings["paused_reason"] or "")
        rate_limited = (
            state == "backoff"
            and rate_limit_quota(str(settings["last_error"] or "")) is not None
        ) or (state == "backoff" and quota_used >= quota_limit)
        authenticated = bool(settings["authenticated"])
        submission_status = settings["submission_status"]
        active_ready = active_version is not None and submission_status == "ready"
        blocked = ""
        if not authenticated:
            blocked = "Not signed in to FCode"
        elif not active_ready:
            blocked = "No ready active FCode submission"
        elif paused:
            blocked = paused
        elif backoff_until is not None and float(backoff_until) > now:
            blocked = "FCode request cooldown"

        team = (
            {"id": settings["team_id"], "name": settings["team_name"]}
            if settings["team_id"]
            else None
        )
        active_submission = (
            {
                "id": settings["submission_id"],
                "version": active_version,
                "name": settings["submission_name"],
                "status": submission_status,
                "uploaded_at": settings["submission_uploaded_at"],
            }
            if active_version is not None or settings["submission_id"]
            else None
        )
        versions = [
            {
                "version": int(row["own_version"]),
                "name": (
                    settings["submission_name"]
                    if int(row["own_version"]) == active_version
                    else None
                ),
                "is_active": int(row["own_version"]) == active_version,
            }
            for row in version_rows
        ]
        if active_version is not None and all(
            row["version"] != active_version for row in versions
        ):
            versions.insert(
                0,
                {
                    "version": active_version,
                    "name": settings["submission_name"],
                    "is_active": True,
                },
            )

        return {
            "revision": revision,
            "refreshing": self._refresh_in_progress,
            "session": {"authenticated": authenticated, "team": team},
            "active_submission": active_submission,
            "autoscrim": {
                "enabled": bool(settings["enabled"]),
                "state": state,
                "target_team_ids": target_ids,
                "target_team_names": target_names,
                "target_matches_per_version": int(
                    settings["target_matches_per_version"]
                ),
                "map_names": _json_list(settings["map_names_json"]),
                "pending_match_id": (
                    auto_pending["match_id"] if auto_pending is not None else None
                ),
                "next_attempt_at": _iso(settings["next_auto_at"]),
                "backoff_until": _iso(settings["backoff_until"]),
                "consecutive_failures": int(settings["consecutive_failures"]),
                "last_error": settings["last_error"] or None,
                "rate_limited": rate_limited,
                "can_request": not blocked,
                "blocked_reason": blocked or None,
            },
            "quota": {
                "limit": quota_limit,
                "window_s": quota_window,
                "used": quota_used,
                "learned": quota_learned,
            },
            "versions": versions,
            "summary": summary,
            "by_opponent": opponents,
            "requests": [self._request_json(row) for row in request_rows],
            "next_cursor": None,
        }

    def enqueue_manual(
        self,
        request_key: str,
        opponent_team_id: str,
        *,
        opponent_team_name: str | None = None,
        source_match_id: str | None = None,
        map_names: Sequence[str] = (),
    ) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._require_open()
            return self._enqueue_manual(
                request_key,
                opponent_team_id,
                opponent_team_name=opponent_team_name,
                source_match_id=source_match_id,
                map_names=map_names,
            )

    def _enqueue_manual(
        self,
        request_key: str,
        opponent_team_id: str,
        *,
        opponent_team_name: str | None = None,
        source_match_id: str | None = None,
        map_names: Sequence[str] = (),
    ) -> dict[str, Any]:
        key = _canonical_uuid(request_key, "request_key")
        opponent = _canonical_uuid(opponent_team_id, "opponent_team_id")
        source = (
            None
            if source_match_id is None
            else _canonical_uuid(source_match_id, "source_match_id")
        )
        name = (
            ""
            if opponent_team_name is None
            else _input_text(opponent_team_name, "opponent_team_name")
        )
        maps = _map_names(map_names)
        now = self._clock()
        with self._write_transaction():
            settings = self._settings_locked()
            own_team_id = self._require_ready_identity_locked(settings)
            existing = self._conn.execute(
                "SELECT * FROM requests WHERE request_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                same_request = (
                    existing["source"] == "manual"
                    and existing["opponent_team_id"] == opponent
                    and existing["source_match_id"] == source
                    and _json_list(existing["map_names_json"]) == list(maps)
                    and existing["own_team_id"] == own_team_id
                )
                if not same_request:
                    raise ValueError(
                        "request_key is already used for a different scrim request"
                    )
                return self._request_json(existing)
            if own_team_id == opponent:
                raise ValueError("target is your own team")
            self._conn.execute(
                "INSERT INTO requests (request_key, source, requested_at, updated_at, "
                "opponent_team_id, opponent_team_name, source_match_id, map_names_json, "
                "status, not_before, own_team_id, own_team_name, own_submission_id, "
                "own_version, own_submission_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    "manual",
                    now,
                    now,
                    opponent,
                    name,
                    source,
                    _json_names(maps),
                    "queued",
                    now,
                    own_team_id,
                    settings["team_name"],
                    settings["submission_id"],
                    settings["submission_version"],
                    settings["submission_name"],
                ),
            )
            self._touch_locked()
            row = self._conn.execute(
                "SELECT * FROM requests WHERE request_key = ?", (key,)
            ).fetchone()
        self._emit(request_key=key)
        self._ensure_worker()
        self._wake.set()
        assert row is not None
        return self._request_json(row)

    def configure_autoscrim(
        self,
        enabled: bool,
        *,
        target_team_ids: Sequence[str] = (),
        target_team_names: Mapping[str, str] | None = None,
        target_matches_per_version: int = 3,
        map_names: Sequence[str] = (),
    ) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._require_open()
            return self._configure_autoscrim(
                enabled,
                target_team_ids=target_team_ids,
                target_team_names=target_team_names,
                target_matches_per_version=target_matches_per_version,
                map_names=map_names,
            )

    def _configure_autoscrim(
        self,
        enabled: bool,
        *,
        target_team_ids: Sequence[str] = (),
        target_team_names: Mapping[str, str] | None = None,
        target_matches_per_version: int = 3,
        map_names: Sequence[str] = (),
    ) -> dict[str, Any]:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be true or false")
        if (
            isinstance(target_matches_per_version, bool)
            or not isinstance(target_matches_per_version, int)
            or not 0 <= target_matches_per_version <= 100
        ):
            raise ValueError("target_matches_per_version must be between 0 and 100")
        if isinstance(target_team_ids, (str, bytes)):
            raise ValueError("target_team_ids must be a list")
        targets: list[str] = []
        for raw in target_team_ids:
            team_id = _canonical_uuid(raw, "target team ID")
            if team_id in targets:
                raise ValueError("target_team_ids must not contain duplicates")
            targets.append(team_id)
        if len(targets) > 100:
            raise ValueError("target_team_ids may contain at most 100 teams")
        if enabled and not targets:
            raise ValueError("add at least one autoscrim target first")
        names: dict[str, str] = {}
        for raw_id, raw_name in (target_team_names or {}).items():
            team_id = _canonical_uuid(raw_id, "target team ID")
            if team_id not in targets:
                raise ValueError("target team names must belong to selected targets")
            names[team_id] = _input_text(raw_name, "target team name")
        maps = _map_names(map_names)
        now = self._clock()
        changed = False
        with self._write_transaction():
            settings = self._settings_locked()
            own_team_id = self._require_ready_identity_locked(settings)
            if own_team_id in targets:
                raise ValueError("autoscrim targets cannot include your own team")
            current_rows = self._conn.execute(
                "SELECT team_id, team_name, ordinal, last_selected_at FROM targets "
                "ORDER BY ordinal, team_id"
            ).fetchall()
            current_names = {
                str(row["team_id"]): str(row["team_name"] or "")
                for row in current_rows
            }
            desired_names = {
                team_id: names.get(team_id, current_names.get(team_id, ""))
                for team_id in targets
            }
            same_targets = [str(row["team_id"]) for row in current_rows] == targets
            same_names = all(
                current_names.get(team_id, "") == desired_names[team_id]
                for team_id in targets
            )
            same_settings = (
                bool(settings["enabled"]) == enabled
                and int(settings["target_matches_per_version"])
                == target_matches_per_version
                and _json_list(settings["map_names_json"]) == list(maps)
                and not settings["paused_reason"]
                and (not enabled or not settings["last_error"])
            )
            if not (same_targets and same_names and same_settings):
                if targets:
                    placeholders = ",".join("?" for _ in targets)
                    self._conn.execute(
                        f"DELETE FROM targets WHERE team_id NOT IN ({placeholders})",
                        tuple(targets),
                    )
                else:
                    self._conn.execute("DELETE FROM targets")
                self._conn.executemany(
                    "INSERT INTO targets (team_id, team_name, ordinal) VALUES (?,?,?) "
                    "ON CONFLICT(team_id) DO UPDATE SET "
                    "team_name = excluded.team_name, ordinal = excluded.ordinal",
                    [
                        (team_id, desired_names[team_id], index)
                        for index, team_id in enumerate(targets)
                    ],
                )
                if not enabled:
                    next_auto_at = None
                elif not settings["enabled"] or settings["next_auto_at"] is None:
                    next_auto_at = now
                else:
                    next_auto_at = settings["next_auto_at"]
                self._conn.execute(
                    "UPDATE settings SET enabled = ?, target_matches_per_version = ?, "
                    "map_names_json = ?, next_auto_at = ?, paused_reason = '', "
                    "last_error = CASE WHEN ? THEN '' ELSE last_error END, "
                    "revision = revision + 1 WHERE id = 1",
                    (
                        int(enabled),
                        target_matches_per_version,
                        _json_names(maps),
                        next_auto_at,
                        int(enabled),
                    ),
                )
                changed = True
            if not enabled:
                cancelled = self._conn.execute(
                    "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                    "error = CASE WHEN error = '' THEN 'Autoscrim disabled before send' ELSE error END "
                    "WHERE source = 'auto' AND status = 'queued'",
                    (now,),
                ).rowcount
                if cancelled and not changed:
                    self._touch_locked()
                    changed = True
        if changed:
            self._emit()
        if enabled or self._has_background_work():
            self._ensure_worker()
            self._wake.set()
        return self._snapshot(limit=1)["autoscrim"]

    def disable_autoscrim(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._require_open()
            return self._disable_autoscrim()

    def _disable_autoscrim(self) -> dict[str, Any]:
        """Stop automatic scheduling without validating or replacing its draft.

        This narrow operation lets the UI provide an unconditional emergency
        off switch even when the unsaved form contains an invalid count or no
        targets. Accepted remote matches cannot be cancelled; only local work
        that has not started is removed from the queue.
        """

        now = self._clock()
        with self._write_transaction():
            self._conn.execute(
                "UPDATE settings SET enabled = 0, next_auto_at = NULL, "
                "paused_reason = '', revision = revision + 1 WHERE id = 1"
            )
            self._conn.execute(
                "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                "error = CASE WHEN error = '' THEN "
                "'Autoscrim disabled before send' ELSE error END "
                "WHERE source = 'auto' AND status = 'queued'",
                (now,),
            )
        self._emit()
        self._wake.set()
        return self._snapshot(limit=1)["autoscrim"]

    def refresh(self) -> None:
        with self._lifecycle_lock:
            self._require_open()
            self._refresh_full = True
            self._refresh_in_progress = True
            self._ensure_worker()
            self._wake.set()
        self._emit()

    # -- worker -----------------------------------------------------

    def _ensure_worker(self) -> None:
        with self._lifecycle_lock:
            if self._closed:
                raise ValueError("scrim coordinator is closed")
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._worker,
                name="oarena-platform-scrims",
                daemon=True,
            )
            self._thread.start()

    def _worker(self) -> None:
        # Hot reload briefly overlaps the retiring and replacement processes.
        # Wait for the old coordinator's lifetime lock instead of abandoning
        # persisted work in the new process.
        acquired = False
        while not self._stop.is_set() and not acquired:
            acquired = self._acquire_dispatch_lock()
            if acquired:
                break
            self._wake.wait(1.0)
            self._wake.clear()
        if not acquired:
            return
        try:
            if self._stop.is_set():
                return
            self._recover_interrupted_sends()
            while not self._stop.is_set():
                try:
                    delay = self._cycle()
                except Exception as exc:  # keep one bad response from killing autoscrim
                    self._record_background_error(exc)
                    delay = _PROFILE_RETRY_S
                if self._stop.is_set():
                    break
                # Keep one resident worker after the queue drains. This avoids
                # the classic exit/enqueue lost wakeup without polling FCode.
                if delay is None:
                    self._wake.wait()
                    self._wake.clear()
                    continue
                self._wake.wait(max(0.05, min(delay, _IDLE_SYNC_S)))
                self._wake.clear()
        finally:
            self._release_dispatch_lock()

    def _recover_interrupted_sends(self) -> None:
        """Resolve stale pre-POST barriers only after owning the process flock."""

        now = self._clock()
        request_error = (
            "Oarena restarted while the FCode request outcome was unresolved"
        )
        with self._write_transaction():
            keys = [
                str(row["request_key"])
                for row in self._conn.execute(
                    "SELECT request_key FROM requests WHERE status = 'sending'"
                ).fetchall()
            ]
            if not keys:
                return
            placeholders = ",".join("?" for _ in keys)
            self._conn.execute(
                f"UPDATE requests SET status = 'unknown', updated_at = ?, "
                f"error = CASE WHEN error = '' THEN ? ELSE error END "
                f"WHERE request_key IN ({placeholders})",
                (now, request_error, *keys),
            )
            self._conn.execute(
                f"UPDATE attempts SET finished_at = ?, status = 'unknown', "
                f"error = CASE WHEN error = '' THEN ? ELSE error END, "
                f"outcome_unknown = 1 WHERE status = 'sending' "
                f"AND request_key IN ({placeholders})",
                (now, request_error, *keys),
            )
            self._conn.execute(
                "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                "error = CASE WHEN error = '' THEN "
                "'Autoscrim paused after an unknown request outcome' ELSE error END "
                "WHERE source = 'auto' AND status = 'queued'",
                (now,),
            )
            self._conn.execute(
                "UPDATE settings SET enabled = 0, paused_reason = ?, "
                "last_error = ?, revision = revision + 1 WHERE id = 1",
                (
                    "An earlier scrim request has an unknown outcome",
                    "Oarena restarted during an unrated-match request",
                ),
            )
        self._emit()

    def _cycle(self) -> float | None:
        now = self._clock()
        with self._lifecycle_lock:
            if self._closed or self._stop.is_set():
                return None
            full_refresh = self._refresh_full
            self._refresh_full = False
        should_sync = full_refresh or now >= self._next_sync_at
        if should_sync:
            sync_ok = False
            try:
                sync_ok = self._sync_remote(full=full_refresh)
            finally:
                if full_refresh:
                    with self._lifecycle_lock:
                        self._refresh_in_progress = False
                    self._emit()
            now = self._clock()
            if sync_ok:
                pending = self._has_pending_match()
                self._next_sync_at = now + (
                    _PENDING_POLL_S if pending else _IDLE_SYNC_S
                )

        if self._stop.is_set():
            return None
        if self._enabled() and self._profile_fresh and self._history_fresh:
            self._maybe_enqueue_auto(now)
        if self._stop.is_set():
            return None
        request = self._next_request(now)
        if request is not None:
            self._dispatch(request)
            return 0.1

        if not self._has_background_work():
            return None
        now = self._clock()
        deadlines = [self._next_sync_at]
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(not_before) AS due FROM requests WHERE status = 'queued'"
            ).fetchone()
            settings = self._settings_locked()
            if row is not None and row["due"] is not None:
                deadlines.append(float(row["due"]))
            if settings["enabled"] and settings["next_auto_at"] is not None:
                deadlines.append(float(settings["next_auto_at"]))
            if settings["backoff_until"] is not None:
                deadlines.append(float(settings["backoff_until"]))
        future = [deadline for deadline in deadlines if deadline > now]
        return max(0.1, min(future) - now) if future else 0.5

    def _sync_remote(self, *, full: bool) -> bool:
        self._history_fresh = False
        if self._stop.is_set():
            return False
        try:
            profile = self.platform.scrim_profile()
            if self._stop.is_set():
                return False
            self._save_profile(profile)
        except PlatformError as exc:
            self._profile_error(exc)
            return False
        except Exception as exc:
            self._profile_error(PlatformError(502, _text(str(exc)) or "Could not read FCode profile"))
            return False

        cursor: str | None = None
        pages = _MAX_HISTORY_PAGES if full else 1
        seen_match_ids: set[str] = set()
        for _ in range(pages):
            if self._stop.is_set():
                return False
            try:
                response = self.platform.matches(
                    limit=100,
                    match_type="unrated",
                    mine=True,
                    team_id=None,
                    cursor=cursor,
                )
            except PlatformError as exc:
                self._set_transient_error(exc.message)
                return False
            except Exception as exc:
                self._set_transient_error(
                    _text(str(exc)) or "Could not read unrated-match history"
                )
                return False
            if self._stop.is_set():
                return False
            rows = response.get("matches") if isinstance(response, Mapping) else None
            if not isinstance(rows, list):
                self._set_transient_error("Invalid unrated-match history from FCode")
                return False
            for row in rows:
                if isinstance(row, Mapping) and isinstance(row.get("id"), str):
                    seen_match_ids.add(row["id"])
            self._save_matches(rows)
            next_cursor = response.get("next_cursor") if isinstance(response, Mapping) else None
            if not full or not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        if not self._sync_pending_matches(seen_match_ids):
            return False
        self._history_fresh = True
        return True

    def _sync_pending_matches(self, seen_match_ids: set[str]) -> bool:
        """Poll exact IDs that may have fallen outside the newest history page."""

        with self._lock:
            team_id = self._settings_locked()["team_id"]
            rows = self._conn.execute(
                "SELECT match_id FROM requests WHERE match_id IS NOT NULL "
                "AND own_team_id = ? AND status IN ('accepted', 'running') "
                "ORDER BY requested_at LIMIT 20",
                (team_id,),
            ).fetchall()
        pending_ids = [
            str(row["match_id"])
            for row in rows
            if str(row["match_id"]) not in seen_match_ids
        ]
        for match_id in pending_ids:
            if self._stop.is_set():
                return False
            try:
                detail = self.platform.match(match_id)
            except PlatformError as exc:
                if exc.code == 404:
                    # The list can expose a newly accepted ID just before its
                    # detail route becomes visible. Leave it pending and poll
                    # again normally; this is not a scheduler failure.
                    continue
                self._set_transient_error(exc.message)
                return False
            except Exception as exc:
                self._set_transient_error(
                    _text(str(exc)) or "Could not read pending unrated match"
                )
                return False
            if self._stop.is_set():
                return False
            match = detail.get("match") if isinstance(detail, Mapping) else None
            if not isinstance(match, Mapping):
                self._set_transient_error("Invalid pending-match response from FCode")
                return False
            self._save_matches([match])
        return True

    def _save_profile(self, profile: Any) -> None:
        if not isinstance(profile, Mapping):
            raise PlatformError(502, "Invalid FCode profile response")
        session = profile.get("session")
        team_raw = profile.get("team")
        if not isinstance(team_raw, Mapping) and isinstance(session, Mapping):
            team_raw = session.get("team")
        if not isinstance(team_raw, Mapping):
            raise PlatformError(400, "The FCode account is not on a team")
        team_id = _canonical_uuid(team_raw.get("id"), "FCode team ID")
        team_name = _text(team_raw.get("name"), limit=_MAX_NAME)
        raw_submission = profile.get("active_submission")
        if raw_submission is not None and not isinstance(raw_submission, Mapping):
            raise PlatformError(502, "Invalid FCode active-submission response")
        submission = raw_submission if isinstance(raw_submission, Mapping) else None
        version = _number(submission.get("version")) if submission else None
        submission_id = _text(submission.get("id"), limit=128) if submission else ""
        submission_name = _text(submission.get("name"), limit=_MAX_NAME) if submission else ""
        submission_status = _text(submission.get("status"), limit=32) if submission else ""
        submission_uploaded_at = (
            _text(submission.get("uploaded_at"), limit=64) if submission else ""
        )
        if submission is not None and (
            version is None
            or version <= 0
            or not submission_id
            or not submission_status
        ):
            raise PlatformError(502, "Invalid FCode active-submission response")
        now = self._clock()
        with self._write_transaction():
            previous = self._settings_locked()
            previous_team_id = previous["team_id"]
            identity_changed = previous_team_id != team_id
            team_changed = bool(previous_team_id and identity_changed)
            self_target = self._conn.execute(
                "SELECT 1 FROM targets WHERE team_id = ? LIMIT 1", (team_id,)
            ).fetchone() is not None

            # Old builds admitted work before learning which authenticated
            # account owned it. Never bind those NULL-team rows to whichever
            # account happens to be active at the next profile refresh.
            self._conn.execute(
                "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                "error = CASE WHEN error = '' THEN "
                "'Scrim request was created before an FCode account identity was established' "
                "ELSE error END WHERE status = 'queued' AND own_team_id IS NULL",
                (now,),
            )
            if identity_changed:
                self._conn.execute(
                    "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                    "error = CASE WHEN error = '' THEN "
                    "'FCode team changed before this request was sent' ELSE error END "
                    "WHERE status = 'queued'",
                    (now,),
                )
            elif self_target:
                self._conn.execute(
                    "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                    "error = CASE WHEN error = '' THEN "
                    "'Autoscrim target became your own team' ELSE error END "
                    "WHERE source = 'auto' AND status = 'queued'",
                    (now,),
                )

            if self_target:
                paused_reason = (
                    "Autoscrim target is now your own team; review scrim settings"
                )
            elif team_changed:
                paused_reason = "FCode team changed; review scrim settings"
            elif identity_changed and previous["enabled"]:
                paused_reason = "FCode account established; review scrim settings"
            elif previous["paused_reason"] in {
                "A scrim request has an unknown outcome",
                "An earlier scrim request has an unknown outcome",
                "FCode team changed; review scrim settings",
                "FCode account established; review scrim settings",
                "Autoscrim target is now your own team; review scrim settings",
            }:
                paused_reason = str(previous["paused_reason"])
            else:
                paused_reason = ""
            self._conn.execute(
                "UPDATE settings SET authenticated = 1, team_id = ?, team_name = ?, "
                "submission_id = ?, submission_version = ?, submission_name = ?, "
                "submission_status = ?, submission_uploaded_at = ?, profile_updated_at = ?, "
                "enabled = CASE WHEN ? THEN 0 ELSE enabled END, "
                "next_auto_at = CASE WHEN ? THEN NULL ELSE next_auto_at END, "
                "paused_reason = ?, "
                "revision = revision + 1 WHERE id = 1",
                (
                    team_id,
                    team_name,
                    submission_id or None,
                    version,
                    submission_name or None,
                    submission_status or None,
                    submission_uploaded_at or None,
                    now,
                    int(identity_changed or self_target),
                    int(identity_changed or self_target),
                    paused_reason,
                ),
            )
            self._conn.execute(
                "UPDATE requests SET own_team_id = ?, own_team_name = ?, "
                "own_submission_id = ?, own_version = ?, own_submission_name = ?, updated_at = ? "
                "WHERE status = 'queued' AND own_team_id = ?",
                (
                    team_id,
                    team_name,
                    submission_id or None,
                    version,
                    submission_name or None,
                    now,
                    team_id,
                ),
            )
        self._profile_fresh = True
        self._emit()

    def _save_matches(self, rows: list[Any]) -> None:
        now = self._clock()
        changed = False
        with self._write_transaction():
            settings = self._settings_locked()
            own_id = settings["team_id"]
            if not isinstance(own_id, str) or not own_id:
                return
            for raw in rows:
                normalized = self._normalize_match(raw, own_id)
                if normalized is None:
                    continue
                self._conn.execute(
                    "INSERT INTO matches (match_id, status, own_team_id, own_team_name, "
                    "own_version, opponent_team_id, opponent_team_name, opponent_version, "
                    "winner_id, score_for, score_against, source_match_own_id, "
                    "source_match_opp_id, error, created_at, completed_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(match_id) DO UPDATE SET "
                    "status = CASE WHEN matches.status IN ('complete', 'error') "
                    "AND excluded.status NOT IN ('complete', 'error') "
                    "THEN matches.status ELSE excluded.status END, "
                    "own_team_id = excluded.own_team_id, "
                    "own_team_name = excluded.own_team_name, "
                    "own_version = COALESCE(excluded.own_version, matches.own_version), "
                    "opponent_team_id = excluded.opponent_team_id, "
                    "opponent_team_name = excluded.opponent_team_name, "
                    "opponent_version = COALESCE(excluded.opponent_version, matches.opponent_version), "
                    "winner_id = CASE WHEN excluded.status IN ('complete', 'error') "
                    "THEN excluded.winner_id ELSE matches.winner_id END, "
                    "score_for = CASE WHEN excluded.status IN ('complete', 'error') "
                    "THEN excluded.score_for ELSE matches.score_for END, "
                    "score_against = CASE WHEN excluded.status IN ('complete', 'error') "
                    "THEN excluded.score_against ELSE matches.score_against END, "
                    "source_match_own_id = COALESCE(excluded.source_match_own_id, matches.source_match_own_id), "
                    "source_match_opp_id = COALESCE(excluded.source_match_opp_id, matches.source_match_opp_id), "
                    "error = CASE WHEN excluded.status IN ('complete', 'error') "
                    "THEN excluded.error ELSE matches.error END, "
                    "created_at = COALESCE(excluded.created_at, matches.created_at), "
                    "completed_at = COALESCE(excluded.completed_at, matches.completed_at), "
                    "updated_at = excluded.updated_at",
                    (*normalized, now),
                )
                match_id = normalized[0]
                match_row = self._conn.execute(
                    "SELECT * FROM matches WHERE match_id = ?", (match_id,)
                ).fetchone()
                if match_row is None:
                    continue
                completed_epoch = _epoch_from_iso(match_row["completed_at"])
                request_status = str(match_row["status"] or "accepted")
                if request_status not in {"running", "complete", "error"}:
                    request_status = "accepted"
                self._conn.execute(
                    "UPDATE requests SET status = ?, opponent_team_name = CASE "
                    "WHEN ? <> '' THEN ? ELSE opponent_team_name END, "
                    "opponent_version = COALESCE(?, opponent_version), score_for = ?, "
                    "score_against = ?, completed_at = ?, error = CASE WHEN ? <> '' THEN ? ELSE error END, "
                    "updated_at = ? WHERE match_id = ?",
                    (
                        request_status,
                        match_row["opponent_team_name"],
                        match_row["opponent_team_name"],
                        match_row["opponent_version"],
                        (
                            match_row["score_for"]
                            if request_status in {"complete", "error"}
                            else None
                        ),
                        (
                            match_row["score_against"]
                            if request_status in {"complete", "error"}
                            else None
                        ),
                        completed_epoch,
                        match_row["error"],
                        match_row["error"],
                        now,
                        match_id,
                    ),
                )
                changed = True
            if changed:
                self._touch_locked()
        if changed:
            self._emit()

    @staticmethod
    def _normalize_match(raw: Any, own_id: str) -> tuple[Any, ...] | None:
        if not isinstance(raw, Mapping):
            return None
        match_id = raw.get("id")
        try:
            match_id = _canonical_uuid(match_id, "match ID")
        except ValueError:
            return None
        match_type = raw.get("type")
        rated = raw.get("rated")
        if not (match_type == "unrated" or (match_type is None and rated is False)):
            return None
        a = raw.get("team_a") if isinstance(raw.get("team_a"), Mapping) else {}
        b = raw.get("team_b") if isinstance(raw.get("team_b"), Mapping) else {}
        if a.get("id") == own_id:
            own, opponent = a, b
            score_for, score_against = _number(raw.get("score_a")), _number(raw.get("score_b"))
            source_own, source_opp = raw.get("source_match_a_id"), raw.get("source_match_b_id")
        elif b.get("id") == own_id:
            own, opponent = b, a
            score_for, score_against = _number(raw.get("score_b")), _number(raw.get("score_a"))
            source_own, source_opp = raw.get("source_match_b_id"), raw.get("source_match_a_id")
        else:
            return None
        opponent_id = opponent.get("id")
        try:
            opponent_id = _canonical_uuid(opponent_id, "opponent team ID")
        except ValueError:
            return None
        return (
            match_id,
            _text(raw.get("status"), limit=32) or "unknown",
            own_id,
            _text(own.get("name"), limit=_MAX_NAME),
            _number(own.get("version")),
            opponent_id,
            _text(opponent.get("name"), limit=_MAX_NAME),
            _number(opponent.get("version")),
            _text(raw.get("winner_id"), limit=128) or None,
            score_for,
            score_against,
            _text(source_own, limit=128) or None,
            _text(source_opp, limit=128) or None,
            _text(raw.get("error")),
            _text(raw.get("created_at"), limit=64) or None,
            _text(raw.get("completed_at"), limit=64) or None,
        )

    def _maybe_enqueue_auto(self, now: float) -> None:
        with self._write_transaction():
            settings = self._settings_locked()
            if not settings["enabled"]:
                return
            if settings["paused_reason"]:
                return
            if settings["backoff_until"] is not None and float(settings["backoff_until"]) > now:
                return
            if settings["next_auto_at"] is not None and float(settings["next_auto_at"]) > now:
                return
            if _number(settings["submission_version"]) is None or settings["submission_status"] != "ready":
                return
            pending = self._conn.execute(
                "SELECT 1 FROM requests WHERE source = 'auto' AND "
                "own_team_id = ? AND "
                "status IN ('queued', 'sending', 'accepted', 'running') LIMIT 1",
                (settings["team_id"],),
            ).fetchone()
            if pending is not None:
                return
            coverage = int(settings["target_matches_per_version"])
            if coverage <= _UNLIMITED_TARGET_MATCHES:
                targets = self._conn.execute(
                    "SELECT t.team_id, t.team_name, t.ordinal, t.last_selected_at, "
                    "COUNT(m.match_id) AS played "
                    "FROM targets t LEFT JOIN matches m ON m.opponent_team_id = t.team_id "
                    "AND m.own_team_id = ? AND m.own_version = ? AND m.status = 'complete' "
                    "GROUP BY t.team_id, t.team_name, t.ordinal, t.last_selected_at "
                    "ORDER BY played, COALESCE(t.last_selected_at, 0), t.ordinal "
                    "LIMIT 1",
                    (
                        settings["team_id"],
                        settings["submission_version"],
                    ),
                ).fetchone()
            else:
                targets = self._conn.execute(
                    "SELECT t.team_id, t.team_name, t.ordinal, t.last_selected_at, COUNT(m.match_id) AS played "
                    "FROM targets t LEFT JOIN matches m ON m.opponent_team_id = t.team_id "
                    "AND m.own_team_id = ? AND m.own_version = ? AND m.status = 'complete' "
                    "GROUP BY t.team_id, t.team_name, t.ordinal, t.last_selected_at "
                    "HAVING played < ? ORDER BY played, COALESCE(t.last_selected_at, 0), t.ordinal LIMIT 1",
                    (
                        settings["team_id"],
                        settings["submission_version"],
                        coverage,
                    ),
                ).fetchone()
            if targets is None:
                self._conn.execute(
                    "UPDATE settings SET next_auto_at = NULL, revision = revision + 1 WHERE id = 1"
                )
                return
            key = str(uuid.uuid4())
            maps = _json_list(settings["map_names_json"])
            self._conn.execute(
                "INSERT INTO requests (request_key, source, requested_at, updated_at, "
                "opponent_team_id, opponent_team_name, map_names_json, status, not_before, "
                "own_team_id, own_team_name, own_submission_id, own_version, own_submission_name) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    "auto",
                    now,
                    now,
                    targets["team_id"],
                    targets["team_name"],
                    _json_names(maps),
                    "queued",
                    now,
                    settings["team_id"],
                    settings["team_name"],
                    settings["submission_id"],
                    settings["submission_version"],
                    settings["submission_name"],
                ),
            )
            self._conn.execute(
                "UPDATE targets SET last_selected_at = ? WHERE team_id = ?",
                (now, targets["team_id"]),
            )
            self._touch_locked()
        self._emit(request_key=key)

    def _next_request(self, now: float) -> sqlite3.Row | None:
        if not self._profile_fresh:
            return None
        with self._write_transaction():
            settings = self._settings_locked()
            if settings["paused_reason"]:
                return None
            if settings["backoff_until"] is not None and float(settings["backoff_until"]) > now:
                return None
            row = self._conn.execute(
                "SELECT * FROM requests WHERE status = 'queued' AND match_id IS NULL "
                "AND not_before <= ? AND own_team_id = ? "
                "AND (source = 'manual' OR ? = 1) "
                "ORDER BY CASE source WHEN 'manual' THEN 0 ELSE 1 END, requested_at LIMIT 1",
                (now, settings["team_id"], int(bool(settings["enabled"]))),
            ).fetchone()
            if row is None:
                return None
            allowance, window = self._quota_locked()
            attempt_rows = self._conn.execute(
                "SELECT COALESCE(finished_at, started_at) AS quota_at FROM attempts "
                "WHERE status <> 'retrying' AND COALESCE(finished_at, started_at) > ? "
                "ORDER BY quota_at",
                (now - window,),
            ).fetchall()
            if len(attempt_rows) >= allowance:
                due = float(attempt_rows[-allowance]["quota_at"]) + window + _RATE_SAFETY_S
                self._conn.execute(
                    "UPDATE requests SET not_before = ?, updated_at = ? WHERE request_key = ?",
                    (due, now, row["request_key"]),
                )
                self._conn.execute(
                    "UPDATE settings SET backoff_until = ?, last_error = ?, "
                    "revision = revision + 1 WHERE id = 1",
                    (due, _quota_wait_text(allowance, window)),
                )
                return None
            return row

    def _dispatch(self, row: sqlite3.Row) -> None:
        # Linearize irreversible dispatch admission with close(). If this lock
        # is ours, shutdown has not begun; close waits through response
        # persistence. If close owns it first, no new POST can start.
        with self._lifecycle_lock:
            if self._closed or self._stop.is_set():
                return
            self._dispatch_admitted(row)

    def _dispatch_admitted(self, row: sqlite3.Row) -> None:
        key = str(row["request_key"])
        now = self._clock()
        cancelled = False
        with self._write_transaction():
            current = self._conn.execute(
                "SELECT * FROM requests WHERE request_key = ?", (key,)
            ).fetchone()
            if (
                current is None
                or current["status"] != "queued"
                or current["match_id"] is not None
            ):
                return
            settings = self._settings_locked()
            if settings["paused_reason"]:
                return
            if current["source"] == "auto" and not settings["enabled"]:
                self._conn.execute(
                    "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                    "error = CASE WHEN error = '' THEN "
                    "'Autoscrim disabled before send' ELSE error END "
                    "WHERE request_key = ? AND status = 'queued'",
                    (now, key),
                )
                self._touch_locked()
                cancelled = True
                current = None
            if cancelled:
                return
            if not settings["authenticated"]:
                self._fail_without_post(key, "Not signed in to FCode", pause_auto=True)
                return
            if settings["submission_version"] is None or settings["submission_status"] != "ready":
                self._fail_without_post(key, "No ready active FCode submission", pause_auto=True)
                return
            if current["opponent_team_id"] == settings["team_id"]:
                self._fail_without_post(key, "Cannot scrim your own team", pause_auto=False)
                return
            if current["own_team_id"] != settings["team_id"]:
                self._fail_without_post(
                    key, "FCode team changed before this request was sent", pause_auto=False
                )
                return
            claimed = self._conn.execute(
                "UPDATE requests SET status = 'sending', attempts = attempts + 1, "
                "last_attempt_at = ?, updated_at = ?, error = '' "
                "WHERE request_key = ? AND status = 'queued' AND match_id IS NULL",
                (now, now, key),
            ).rowcount
            if claimed != 1:
                return
            cursor = self._conn.execute(
                "INSERT INTO attempts (request_key, started_at, status) VALUES (?, ?, 'sending')",
                (key, now),
            )
            attempt_id = int(cursor.lastrowid)
            self._touch_locked()
            current = self._conn.execute(
                "SELECT * FROM requests WHERE request_key = ?", (key,)
            ).fetchone()
        self._emit(request_key=key)
        assert current is not None
        try:
            result = self.platform.request_unrated(
                current["opponent_team_id"],
                source_match_id=current["source_match_id"],
                map_names=tuple(_json_list(current["map_names_json"])),
            )
            match_id = _canonical_uuid(
                result.get("match_id") if isinstance(result, Mapping) else None,
                "match_id",
            )
        except PlatformError as exc:
            self._dispatch_error(current, attempt_id, exc)
            return
        except Exception as exc:
            self._dispatch_error(
                current,
                attempt_id,
                PlatformError(
                    502,
                    _text(str(exc)) or "FCode request failed",
                    outcome_unknown=True,
                ),
            )
            return

        finished = self._clock()
        with self._write_transaction():
            self._conn.execute(
                "UPDATE attempts SET finished_at = ?, status = 'accepted', response_code = 200, "
                "match_id = ? WHERE id = ?",
                (finished, match_id, attempt_id),
            )
            self._conn.execute(
                "UPDATE requests SET status = 'accepted', match_id = ?, updated_at = ?, "
                "error = '' WHERE request_key = ?",
                (match_id, finished, current["request_key"]),
            )
            next_auto = (
                finished + self._auto_cadence_locked()
                if current["source"] == "auto"
                else None
            )
            self._conn.execute(
                "UPDATE settings SET backoff_until = NULL, consecutive_failures = 0, "
                "last_error = '', next_auto_at = CASE WHEN enabled THEN "
                "COALESCE(?, next_auto_at) ELSE NULL END, "
                "revision = revision + 1 WHERE id = 1",
                (next_auto,),
            )
        self._next_sync_at = min(self._next_sync_at, finished + 2.0)
        self._emit(request_key=key, match_id=match_id)

    def _dispatch_error(
        self, row: sqlite3.Row, attempt_id: int, exc: PlatformError
    ) -> None:
        now = self._clock()
        code = exc.code if isinstance(exc.code, int) and not isinstance(exc.code, bool) else 502
        message = _text(exc.message) or "FCode request failed"
        unknown = bool(getattr(exc, "outcome_unknown", False))
        with self._write_transaction():
            if unknown:
                status = "unknown"
                self._conn.execute(
                    "UPDATE requests SET status = 'unknown', updated_at = ?, error = ? WHERE request_key = ?",
                    (now, message, row["request_key"]),
                )
                self._conn.execute(
                    "UPDATE settings SET enabled = 0, paused_reason = ?, last_error = ?, "
                    "consecutive_failures = consecutive_failures + 1, revision = revision + 1 WHERE id = 1",
                    ("A scrim request has an unknown outcome", message),
                )
                self._conn.execute(
                    "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                    "error = CASE WHEN error = '' THEN "
                    "'Autoscrim paused after an unknown request outcome' ELSE error END "
                    "WHERE source = 'auto' AND status = 'queued'",
                    (now,),
                )
            elif code == 429:
                # Reaching the shared quota is an expected part of scrimming, so
                # this only waits and never pauses: the request stays queued, any
                # earlier pause is lifted, and escalation is capped so a busy
                # window cannot compound into a half-hour stall.
                self._learn_quota_locked(message, now)
                window = self._quota_window_locked()
                retry = getattr(exc, "retry_after_s", None)
                retry_s = (
                    float(retry)
                    if isinstance(retry, int) and not isinstance(retry, bool) and retry >= 0
                    else window + _RATE_SAFETY_S
                )
                with_failures = self._settings_locked()["consecutive_failures"] + 1
                exponent = min(max(0, with_failures - 1), _RATE_ESCALATION_MAX)
                retry_s = max(
                    retry_s,
                    min(_MAX_BACKOFF_S, (window + _RATE_SAFETY_S) * (2**exponent)),
                )
                due = now + retry_s
                status = "rate_limited"
                self._conn.execute(
                    "UPDATE requests SET status = 'queued', not_before = ?, updated_at = ?, error = ? "
                    "WHERE request_key = ?",
                    (due, now, message, row["request_key"]),
                )
                self._conn.execute(
                    "UPDATE settings SET backoff_until = ?, consecutive_failures = ?, "
                    "last_error = ?, paused_reason = '', "
                    "next_auto_at = CASE WHEN enabled THEN ? ELSE next_auto_at END, "
                    "revision = revision + 1 WHERE id = 1",
                    (due, with_failures, message, due),
                )
            elif code >= 500:
                # The transport explicitly says the request was not sent. This
                # is the only server failure that may be retried automatically.
                # Lost/invalid responses arrive with outcome_unknown=True and
                # are handled above, permanently, without guessing.
                with_failures = self._settings_locked()["consecutive_failures"] + 1
                exponent = min(max(0, with_failures - 1), 4)
                retry_s = min(_MAX_BACKOFF_S, _PROFILE_RETRY_S * (2**exponent))
                due = now + retry_s
                status = "retrying"
                self._conn.execute(
                    "UPDATE requests SET status = 'queued', not_before = ?, "
                    "updated_at = ?, error = ? WHERE request_key = ?",
                    (due, now, message, row["request_key"]),
                )
                self._conn.execute(
                    "UPDATE settings SET backoff_until = ?, consecutive_failures = ?, "
                    "last_error = ?, revision = revision + 1 WHERE id = 1",
                    (due, with_failures, message),
                )
            else:
                status = "failed"
                self._conn.execute(
                    "UPDATE requests SET status = 'failed', updated_at = ?, error = ? WHERE request_key = ?",
                    (now, message, row["request_key"]),
                )
                if code == 401:
                    reason = "FCode authentication needs attention"
                    self._conn.execute(
                        "UPDATE settings SET enabled = 0, authenticated = 0, "
                        "paused_reason = ?, last_error = ?, revision = revision + 1 WHERE id = 1",
                        (reason, message),
                    )
                    self._conn.execute(
                        "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                        "error = CASE WHEN error = '' THEN ? ELSE error END "
                        "WHERE source = 'auto' AND status = 'queued'",
                        (now, reason),
                    )
                elif row["source"] == "auto":
                    # One rejection says nothing about the next opponent, and
                    # upstream wording changes without notice. Wait, let the
                    # scheduler pick a different target, and only give up once a
                    # run of attempts has failed.
                    with_failures = self._settings_locked()["consecutive_failures"] + 1
                    exponent = min(max(0, with_failures - 1), 4)
                    due = now + min(
                        _MAX_BACKOFF_S, _AUTO_REJECTION_RETRY_S * (2**exponent)
                    )
                    if with_failures >= _AUTO_REJECTION_PAUSE_AFTER:
                        reason = (
                            f"Autoscrim paused after {with_failures} rejected requests"
                        )
                        self._conn.execute(
                            "UPDATE settings SET enabled = 0, paused_reason = ?, "
                            "last_error = ?, consecutive_failures = ?, "
                            "revision = revision + 1 WHERE id = 1",
                            (reason, message, with_failures),
                        )
                        self._conn.execute(
                            "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                            "error = CASE WHEN error = '' THEN ? ELSE error END "
                            "WHERE source = 'auto' AND status = 'queued'",
                            (now, reason),
                        )
                    else:
                        self._conn.execute(
                            "UPDATE settings SET backoff_until = ?, "
                            "consecutive_failures = ?, last_error = ?, "
                            "next_auto_at = CASE WHEN enabled THEN ? ELSE next_auto_at END, "
                            "revision = revision + 1 WHERE id = 1",
                            (due, with_failures, message, due),
                        )
                else:
                    self._touch_locked()
            self._conn.execute(
                "UPDATE attempts SET finished_at = ?, status = ?, response_code = ?, "
                "error = ?, outcome_unknown = ? WHERE id = ?",
                (now, status, code, message, int(unknown), attempt_id),
            )
        self._emit(request_key=str(row["request_key"]))

    # -- learned shared quota -----------------------------------------

    def _learn_quota_locked(self, message: str, now: float) -> None:
        """Record the allowance FCode just told us about.

        The platform states its own limit in the rejection text. Believing that
        over a compiled-in constant is what lets pacing survive the organisers
        retuning the quota mid-season.
        """
        quota = rate_limit_quota(message)
        if quota is None:
            return
        allowance, window = quota
        self._conn.execute(
            "UPDATE settings SET rate_limit_max = ?, rate_limit_window_s = ?, "
            "rate_limit_seen_at = ? WHERE id = 1",
            (int(allowance), float(window), now),
        )

    def _quota_locked(self) -> tuple[int, float]:
        row = self._conn.execute(
            "SELECT rate_limit_max, rate_limit_window_s FROM settings WHERE id = 1"
        ).fetchone()
        allowance = _number(row["rate_limit_max"]) if row is not None else None
        raw_window = row["rate_limit_window_s"] if row is not None else None
        window = (
            float(raw_window)
            if isinstance(raw_window, (int, float)) and not isinstance(raw_window, bool)
            else None
        )
        return (
            int(allowance) if allowance and allowance > 0 else _RATE_LIMIT,
            window if window and window > 0 else _RATE_WINDOW_S,
        )

    def _quota_window_locked(self) -> float:
        return self._quota_locked()[1]

    def _auto_cadence_locked(self) -> float:
        """Space automatic requests so they fit the quota instead of bursting.

        Firing faster than the shared limit allows just trades a short burst for
        a long stall, and every rejected request still spends quota. Spreading
        them evenly keeps a session scrimming continuously.
        """
        allowance, window = self._quota_locked()
        even = window / allowance + _RATE_SAFETY_S if allowance > 0 else _AUTO_CADENCE_S
        return max(_AUTO_CADENCE_S, even)

    def _fail_without_post(self, key: str, message: str, *, pause_auto: bool) -> None:
        now = self._clock()
        self._conn.execute(
            "UPDATE requests SET status = 'failed', updated_at = ?, error = ? WHERE request_key = ?",
            (now, message, key),
        )
        if pause_auto:
            self._conn.execute(
                "UPDATE settings SET enabled = 0, paused_reason = ?, last_error = ?, "
                "revision = revision + 1 WHERE id = 1",
                (message, message),
            )
            self._conn.execute(
                "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                "error = CASE WHEN error = '' THEN ? ELSE error END "
                "WHERE source = 'auto' AND status = 'queued'",
                (now, message),
            )
        else:
            self._touch_locked()
        self._emit(request_key=key)

    # -- state helpers ------------------------------------------------

    def _require_open(self) -> None:
        if self._closed or self._conn_closed:
            raise ValueError("scrim coordinator is closed")

    @contextmanager
    def _read_transaction(self):
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    @contextmanager
    def _write_transaction(self):
        # BEGIN IMMEDIATE makes the decision SELECTs and their following state
        # transition one cross-process operation, including during hot reload.
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    def _statistics(
        self, rows: Sequence[sqlite3.Row], selected_version: int | None
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        total = self._blank_record(selected_version)
        groups: dict[str, dict[str, Any]] = {}
        own_id = None
        for row in rows:
            own_id = row["own_team_id"]
            opponent_id = str(row["opponent_team_id"])
            group = groups.setdefault(
                opponent_id,
                {
                    **self._blank_record(selected_version),
                    "opponent": {
                        "id": opponent_id,
                        "name": row["opponent_team_name"],
                    },
                    "opponent_versions": set(),
                    "last_played_at": None,
                },
            )
            version = _number(row["opponent_version"])
            if version is not None:
                group["opponent_versions"].add(version)
            winner = row["winner_id"]
            if winner == row["own_team_id"]:
                field = "match_wins"
            elif winner:
                field = "match_losses"
            else:
                field = "match_draws"
            total[field] += 1
            group[field] += 1
            score_for = _number(row["score_for"]) or 0
            score_against = _number(row["score_against"]) or 0
            total["games_won"] += score_for
            total["games_lost"] += score_against
            group["games_won"] += score_for
            group["games_lost"] += score_against
            played = row["completed_at"] or row["created_at"]
            if played and (group["last_played_at"] is None or played > group["last_played_at"]):
                group["last_played_at"] = played
        total["matches"] = total["match_wins"] + total["match_losses"] + total["match_draws"]
        games = total["games_won"] + total["games_lost"] + total["games_drawn"]
        total["win_rate"] = total["games_won"] / games if games else None
        output: list[dict[str, Any]] = []
        for group in groups.values():
            group["matches"] = group["match_wins"] + group["match_losses"] + group["match_draws"]
            games = group["games_won"] + group["games_lost"] + group["games_drawn"]
            group["win_rate"] = group["games_won"] / games if games else None
            group["opponent_versions"] = sorted(group["opponent_versions"], reverse=True)
            output.append(group)
        output.sort(key=lambda row: (-row["matches"], (row["opponent"]["name"] or row["opponent"]["id"]).casefold()))
        return total, output

    @staticmethod
    def _blank_record(version: int | None) -> dict[str, Any]:
        return {
            "our_version": version,
            "matches": 0,
            "match_wins": 0,
            "match_losses": 0,
            "match_draws": 0,
            "games_won": 0,
            "games_lost": 0,
            "games_drawn": 0,
            "win_rate": None,
        }

    @staticmethod
    def _request_json(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["request_key"],
            "request_key": row["request_key"],
            "source": row["source"],
            "requested_at": _iso(float(row["requested_at"])),
            "opponent": {
                "id": row["opponent_team_id"],
                "name": row["opponent_team_name"],
            },
            "opponent_team_id": row["opponent_team_id"],
            "opponent_team_name": row["opponent_team_name"],
            "our_submission": {
                "id": row["own_submission_id"],
                "version": row["own_version"],
                "name": row["own_submission_name"],
            },
            "our_version": row["own_version"],
            "opponent_version": row["opponent_version"],
            "source_match_id": row["source_match_id"],
            "map_names": _json_list(row["map_names_json"]),
            "status": row["status"],
            "match_id": row["match_id"],
            "score_for": row["score_for"],
            "score_against": row["score_against"],
            "completed_at": _iso(row["completed_at"]),
            "attempts": int(row["attempts"]),
            "error": row["error"] or None,
        }

    def _state_label(
        self,
        settings: sqlite3.Row,
        *,
        now: float,
        queued: int,
        sending: int,
        selected_version: int | None,
    ) -> str:
        if sending:
            return "submitting"
        if settings["paused_reason"]:
            return "paused"
        if settings["backoff_until"] is not None and float(settings["backoff_until"]) > now:
            return "backoff"
        if queued:
            return "waiting"
        if not settings["enabled"]:
            return "off"
        target_limit = int(settings["target_matches_per_version"])
        if selected_version is not None and target_limit > _UNLIMITED_TARGET_MATCHES:
            with self._lock:
                remaining = self._conn.execute(
                    "SELECT 1 FROM targets t WHERE (SELECT COUNT(*) FROM matches m "
                    "WHERE m.opponent_team_id = t.team_id AND m.own_team_id = ? "
                    "AND m.own_version = ? "
                    "AND m.status = 'complete') < ? LIMIT 1",
                    (
                        settings["team_id"],
                        selected_version,
                        target_limit,
                    ),
                ).fetchone()
            if remaining is None:
                return "coverage_complete"
        return "ready"

    def _save_setting_error(self, message: str, *, pause: str = "") -> None:
        with self._write_transaction():
            self._conn.execute(
                "UPDATE settings SET last_error = ?, paused_reason = CASE WHEN ? <> '' THEN ? ELSE paused_reason END, "
                "revision = revision + 1 WHERE id = 1",
                (_text(message), pause, pause),
            )
        self._emit()

    def _profile_error(self, exc: PlatformError) -> None:
        message = _text(exc.message) or "Could not read FCode profile"
        self._profile_fresh = False
        self._history_fresh = False
        with self._write_transaction():
            if exc.code == 401:
                self._conn.execute(
                    "UPDATE settings SET authenticated = 0, enabled = 0, paused_reason = ?, "
                    "last_error = ?, backoff_until = NULL, revision = revision + 1 WHERE id = 1",
                    ("FCode authentication needs attention", message),
                )
                self._conn.execute(
                    "UPDATE requests SET status = 'cancelled', updated_at = ?, "
                    "error = CASE WHEN error = '' THEN "
                    "'FCode authentication needs attention' ELSE error END "
                    "WHERE source = 'auto' AND status = 'queued'",
                    (self._clock(),),
                )
            else:
                self._conn.execute(
                    "UPDATE settings SET last_error = ?, backoff_until = ?, revision = revision + 1 WHERE id = 1",
                    (message, self._clock() + _PROFILE_RETRY_S),
                )
        self._next_sync_at = self._clock() + _PROFILE_RETRY_S
        self._emit()

    def _set_transient_error(self, message: str) -> None:
        now = self._clock()
        self._history_fresh = False
        with self._write_transaction():
            self._conn.execute(
                "UPDATE settings SET last_error = ?, backoff_until = ?, "
                "revision = revision + 1 WHERE id = 1",
                (_text(message), now + _PROFILE_RETRY_S),
            )
        self._next_sync_at = now + _PROFILE_RETRY_S
        self._emit()

    def _record_background_error(self, exc: Exception) -> None:
        self._save_setting_error(
            f"Scrim coordinator error: {_text(str(exc)) or type(exc).__name__}"
        )

    def _settings_locked(self) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        assert row is not None
        return row

    def _require_ready_identity_locked(self, settings: sqlite3.Row) -> str:
        """Return the freshly verified team bound to any newly created work."""

        if not self._profile_fresh:
            raise ValueError("Refresh your FCode account before requesting scrims")
        if not settings["authenticated"] or not settings["team_id"]:
            raise ValueError("Sign in to FCode before requesting scrims")
        if (
            _number(settings["submission_version"]) is None
            or settings["submission_status"] != "ready"
            or not settings["submission_id"]
        ):
            raise ValueError("A ready active FCode submission is required")
        try:
            return _canonical_uuid(settings["team_id"], "FCode team ID")
        except ValueError as exc:
            raise ValueError(
                "Refresh your FCode account before requesting scrims"
            ) from exc

    def _touch_locked(self) -> None:
        self._conn.execute("UPDATE settings SET revision = revision + 1 WHERE id = 1")

    def _emit(self, **data: Any) -> None:
        if self.bus is None or not hasattr(self.bus, "emit"):
            return
        try:
            self.bus.emit("platform_scrim", **data)
        except Exception:
            pass

    def _enabled(self) -> bool:
        with self._lock:
            return bool(self._settings_locked()["enabled"])

    def _has_due_request(self, now: float) -> bool:
        with self._lock:
            settings = self._settings_locked()
            if settings["team_id"] is None:
                return False
            return self._conn.execute(
                "SELECT 1 FROM requests WHERE status = 'queued' AND match_id IS NULL "
                "AND not_before <= ? AND own_team_id = ? "
                "LIMIT 1",
                (now, settings["team_id"]),
            ).fetchone() is not None

    def _has_pending_match(self) -> bool:
        with self._lock:
            settings = self._settings_locked()
            if settings["team_id"] is None:
                return False
            return self._conn.execute(
                "SELECT 1 FROM requests WHERE own_team_id = ? "
                "AND status IN ('accepted', 'running') LIMIT 1",
                (settings["team_id"],),
            ).fetchone() is not None

    def _has_background_work(self) -> bool:
        with self._lock:
            settings = self._settings_locked()
            if settings["enabled"]:
                return True
            if settings["team_id"] is None:
                # A legacy unbound row may be what wakes the worker so a
                # profile refresh can cancel it, but it is never dispatchable.
                return self._conn.execute(
                    "SELECT 1 FROM requests WHERE status IN "
                    "('queued', 'sending', 'accepted', 'running') LIMIT 1"
                ).fetchone() is not None
            return self._conn.execute(
                "SELECT 1 FROM requests WHERE "
                "own_team_id = ? "
                "AND status IN ('queued', 'sending', 'accepted', 'running') LIMIT 1",
                (settings["team_id"],),
            ).fetchone() is not None

    def _acquire_dispatch_lock(self) -> bool:
        if str(self.path) == ":memory:":
            return True
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(lock_path, flags, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                os.close(fd)
                return False
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            try:
                os.close(fd)
            except (OSError, UnboundLocalError):
                pass
            return False
        self._dispatch_fd = fd
        return True

    def _release_dispatch_lock(self) -> None:
        fd, self._dispatch_fd = self._dispatch_fd, None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
