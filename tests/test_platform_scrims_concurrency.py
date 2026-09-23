"""Concurrency and ordering regressions for the durable scrim coordinator."""

from __future__ import annotations

import fcntl
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from oarena.fcode_platform import PlatformError
from oarena.platform_scrims import ScrimCoordinator


OWN = "11111111-1111-4111-8111-111111111111"
OPPONENT = "3a7b78b8-5d79-4e55-94a3-7732fcaa4105"
SECOND = "7fd91e77-812c-44da-bce7-457be94d2548"
SUBMISSION = "f536f8ac-1713-4819-b727-82ab310714d1"
MATCH = "be826129-0aed-4c72-aa0c-70b85d77ba3f"


class ControlledPlatform:
    """Small event-driven platform double used to expose worker races."""

    def __init__(self, *, block_profile: bool = False) -> None:
        self.block_profile = block_profile
        self.profile_started = threading.Event()
        self.profile_release = threading.Event()
        self.history_called = threading.Event()
        self.request_started = threading.Event()
        self.duplicate_request_started = threading.Event()
        self.detail_called = threading.Event()

        self.profile_calls = 0
        self.match_list_calls = 0
        self.detail_calls: list[str] = []
        self.request_calls: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.details: dict[str, dict[str, Any]] = {}
        self.history_error: PlatformError | None = None
        self.request_errors: list[PlatformError] = []
        self._guard = threading.Lock()

    def scrim_profile(self) -> dict[str, Any]:
        with self._guard:
            self.profile_calls += 1
        self.profile_started.set()
        if self.block_profile and not self.profile_release.wait(2.0):
            raise PlatformError(502, "profile fixture was not released")
        return {
            "team": {"id": OWN, "name": "Alpha"},
            "active_submission": {
                "id": SUBMISSION,
                "version": 7,
                "name": "rush",
                "status": "ready",
                "uploaded_at": "2026-08-05T20:00:00Z",
            },
        }

    def matches(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["match_type"] == "unrated"
        assert kwargs["mine"] is True
        with self._guard:
            self.match_list_calls += 1
            rows = list(self.rows)
            error = self.history_error
        self.history_called.set()
        if error is not None:
            raise error
        return {"matches": rows, "next_cursor": None}

    def match(self, match_id: str) -> dict[str, Any]:
        with self._guard:
            self.detail_calls.append(match_id)
            detail = self.details.get(match_id)
        self.detail_called.set()
        if detail is None:
            raise PlatformError(404, "match not found")
        return detail

    def request_unrated(
        self,
        opponent_team_id: str,
        *,
        source_match_id: str | None = None,
        map_names: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        call = {
            "opponent_team_id": opponent_team_id,
            "source_match_id": source_match_id,
            "map_names": map_names,
        }
        with self._guard:
            self.request_calls.append(call)
            count = len(self.request_calls)
            error = self.request_errors.pop(0) if self.request_errors else None
        self.request_started.set()
        if count > 1:
            self.duplicate_request_started.set()
        if error is not None:
            raise error
        return {"match_id": MATCH}


def wait_for(predicate: Any, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


def request_key() -> str:
    return str(uuid.uuid4())


def request_by_key(coordinator: ScrimCoordinator, key: str) -> dict[str, Any]:
    return next(row for row in coordinator.snapshot()["requests"] if row["id"] == key)


def establish_identity(coordinator: ScrimCoordinator) -> None:
    coordinator._save_profile(
        {
            "team": {"id": OWN, "name": "Alpha"},
            "active_submission": {
                "id": SUBMISSION,
                "version": 7,
                "name": "rush",
                "status": "ready",
                "uploaded_at": "2026-08-05T20:00:00Z",
            },
        }
    )


def initialize_database(path: Path) -> None:
    coordinator = ScrimCoordinator(path, ControlledPlatform())
    coordinator.close()


def ready_settings(connection: sqlite3.Connection, *, enabled: bool) -> None:
    connection.execute(
        "UPDATE settings SET enabled = ?, authenticated = 1, team_id = ?, "
        "team_name = 'Alpha', submission_id = ?, submission_version = 7, "
        "submission_name = 'rush', submission_status = 'ready' WHERE id = 1",
        (int(enabled), OWN, SUBMISSION),
    )


def insert_request(
    connection: sqlite3.Connection,
    *,
    key: str,
    source: str,
    status: str,
    opponent: str = OPPONENT,
    requested_at: float | None = None,
) -> None:
    now = time.time() if requested_at is None else requested_at
    connection.execute(
        "INSERT INTO requests (request_key, source, requested_at, updated_at, "
        "opponent_team_id, opponent_team_name, status, not_before, own_team_id, "
        "own_team_name, own_submission_id, own_version, own_submission_name) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            key,
            source,
            now,
            now,
            opponent,
            "Pantheon" if opponent == OPPONENT else "Second",
            status,
            now - 1.0,
            OWN,
            "Alpha",
            SUBMISSION,
            7,
            "rush",
        ),
    )


def complete_match(match_id: str = MATCH) -> dict[str, Any]:
    return {
        "id": match_id,
        "status": "complete",
        "type": "unrated",
        "rated": False,
        "team_a": {"id": OWN, "name": "Alpha", "version": 7},
        "team_b": {"id": OPPONENT, "name": "Pantheon", "version": 31},
        "winner_id": OWN,
        "score_a": 4,
        "score_b": 1,
        "created_at": "2026-08-05T20:00:00Z",
        "completed_at": "2026-08-05T20:01:00Z",
    }


def test_remote_queued_status_never_requeues_an_already_posted_request(
    tmp_path: Path,
) -> None:
    platform = ControlledPlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    key = request_key()
    try:
        establish_identity(coordinator)
        coordinator.enqueue_manual(key, OPPONENT)
        wait_for(lambda: request_by_key(coordinator, key)["status"] == "accepted")
        platform.rows = [
            {
                **complete_match(),
                "status": "queued",
                "winner_id": None,
                "score_a": None,
                "score_b": None,
                "completed_at": None,
            }
        ]
        previous_history_calls = platform.match_list_calls

        coordinator.refresh()
        wait_for(lambda: platform.match_list_calls > previous_history_calls)

        assert not platform.duplicate_request_started.wait(0.35)
        assert len(platform.request_calls) == 1
        assert request_by_key(coordinator, key)["status"] != "queued"
    finally:
        coordinator.close()


def test_stale_sending_is_recovered_only_after_dispatch_flock_is_owned(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scrims.db"
    initialize_database(path)
    key = request_key()
    with sqlite3.connect(path) as connection:
        ready_settings(connection, enabled=False)
        insert_request(connection, key=key, source="manual", status="sending")

    lock_path = path.with_suffix(path.suffix + ".lock")
    holder = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    coordinator: ScrimCoordinator | None = None
    try:
        coordinator = ScrimCoordinator(path, ControlledPlatform())
        # This is the hot-reload overlap: the retiring process still owns the
        # dispatch lock, so the replacement must not declare its POST lost.
        assert request_by_key(coordinator, key)["status"] == "sending"

        fcntl.flock(holder, fcntl.LOCK_UN)
        coordinator._wake.set()
        wait_for(lambda: request_by_key(coordinator, key)["status"] == "unknown")
    finally:
        try:
            fcntl.flock(holder, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(holder)
        if coordinator is not None:
            coordinator.close()


def test_close_while_profile_is_blocked_never_starts_a_post(tmp_path: Path) -> None:
    platform = ControlledPlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    closer: threading.Thread | None = None
    try:
        establish_identity(coordinator)
        platform.block_profile = True
        coordinator.enqueue_manual(request_key(), OPPONENT)
        assert platform.profile_started.wait(1.0)

        closer = threading.Thread(target=coordinator.close)
        closer.start()
        wait_for(coordinator._stop.is_set)
        platform.profile_release.set()
        closer.join(timeout=2.0)

        assert not closer.is_alive()
        assert not platform.request_started.is_set()
        assert platform.request_calls == []
    finally:
        platform.profile_release.set()
        if closer is not None:
            closer.join(timeout=2.0)
        coordinator.close()


def test_unknown_outcome_disables_auto_and_cancels_all_unsent_auto_work(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scrims.db"
    initialize_database(path)
    manual_key = request_key()
    auto_key = request_key()
    now = time.time()
    with sqlite3.connect(path) as connection:
        ready_settings(connection, enabled=True)
        insert_request(
            connection,
            key=manual_key,
            source="manual",
            status="queued",
            requested_at=now,
        )
        insert_request(
            connection,
            key=auto_key,
            source="auto",
            status="queued",
            opponent=SECOND,
            requested_at=now + 0.01,
        )

    platform = ControlledPlatform()
    platform.request_errors.append(
        PlatformError(504, "response was lost", outcome_unknown=True)
    )
    coordinator = ScrimCoordinator(path, platform)
    try:
        wait_for(lambda: request_by_key(coordinator, manual_key)["status"] == "unknown")
        wait_for(lambda: request_by_key(coordinator, auto_key)["status"] == "cancelled")

        snapshot = coordinator.snapshot()
        assert snapshot["autoscrim"]["enabled"] is False
        assert snapshot["autoscrim"]["state"] == "paused"
        assert len(platform.request_calls) == 1
    finally:
        coordinator.close()


def test_identical_autoscrim_save_preserves_cadence_and_target_rotation(
    tmp_path: Path,
) -> None:
    platform = ControlledPlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    config = {
        "target_team_ids": (OPPONENT,),
        "target_team_names": {OPPONENT: "Pantheon"},
        "target_matches_per_version": 4,
        "map_names": ("sprint",),
    }
    try:
        establish_identity(coordinator)
        coordinator.configure_autoscrim(True, **config)
        wait_for(
            lambda: coordinator.snapshot()["requests"]
            and coordinator.snapshot()["requests"][0]["status"] == "accepted"
        )
        with coordinator._lock:
            before_next = coordinator._conn.execute(
                "SELECT next_auto_at FROM settings WHERE id = 1"
            ).fetchone()[0]
            before_selected = coordinator._conn.execute(
                "SELECT last_selected_at FROM targets WHERE team_id = ?", (OPPONENT,)
            ).fetchone()[0]
        assert before_next is not None
        assert before_selected is not None

        coordinator.configure_autoscrim(True, **config)

        with coordinator._lock:
            after_next = coordinator._conn.execute(
                "SELECT next_auto_at FROM settings WHERE id = 1"
            ).fetchone()[0]
            after_selected = coordinator._conn.execute(
                "SELECT last_selected_at FROM targets WHERE team_id = ?", (OPPONENT,)
            ).fetchone()[0]
        assert after_next == before_next
        assert after_selected == before_selected
    finally:
        coordinator.close()


def test_concurrent_same_key_enqueue_across_coordinators_is_idempotent(
    tmp_path: Path,
) -> None:
    platform = ControlledPlatform(block_profile=True)
    path = tmp_path / "scrims.db"
    coordinators = (
        ScrimCoordinator(path, platform),
        ScrimCoordinator(path, platform),
    )
    for coordinator in coordinators:
        establish_identity(coordinator)
    key = request_key()
    barrier = threading.Barrier(12)

    def enqueue(index: int) -> dict[str, Any]:
        barrier.wait(timeout=1.5)
        return coordinators[index % len(coordinators)].enqueue_manual(
            key,
            OPPONENT,
            opponent_team_name="Pantheon",
            map_names=("sprint",),
        )

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(enqueue, index) for index in range(12)]
            results = [future.result(timeout=2.0) for future in futures]
        assert all(row["request_key"] == key for row in results)
        assert [row["id"] for row in coordinators[0].snapshot()["requests"]] == [key]

        platform.profile_release.set()
        wait_for(
            lambda: request_by_key(coordinators[0], key)["status"] == "accepted"
        )
        assert len(platform.request_calls) == 1
    finally:
        platform.profile_release.set()
        for coordinator in coordinators:
            coordinator.close()


def test_accepted_request_reconciles_by_exact_match_when_absent_from_newest_list(
    tmp_path: Path,
) -> None:
    platform = ControlledPlatform()
    platform.details[MATCH] = {"match": complete_match(), "games": []}
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    key = request_key()
    try:
        establish_identity(coordinator)
        coordinator.enqueue_manual(key, OPPONENT)
        wait_for(lambda: request_by_key(coordinator, key)["status"] == "accepted")
        assert platform.rows == []

        coordinator.refresh()
        assert platform.detail_called.wait(1.5)
        wait_for(lambda: request_by_key(coordinator, key)["status"] == "complete")

        snapshot = coordinator.snapshot()
        assert platform.detail_calls == [MATCH]
        assert len(platform.request_calls) == 1
        assert snapshot["summary"]["matches"] == 1
        assert snapshot["summary"]["match_wins"] == 1
    finally:
        coordinator.close()


def test_history_sync_failure_does_not_dispatch_autoscrim(tmp_path: Path) -> None:
    platform = ControlledPlatform()
    platform.history_error = PlatformError(502, "history unavailable")
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.configure_autoscrim(
            True,
            target_team_ids=(OPPONENT,),
            target_team_names={OPPONENT: "Pantheon"},
            target_matches_per_version=2,
        )
        assert platform.history_called.wait(1.0)
        wait_for(
            lambda: coordinator.snapshot()["autoscrim"]["last_error"]
            == "history unavailable"
        )

        assert not platform.request_started.wait(0.35)
        assert platform.request_calls == []
    finally:
        coordinator.close()
