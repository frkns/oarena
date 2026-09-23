"""Durability, rate limiting, reconciliation and stats for platform scrims."""

from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from oarena.fcode_platform import PlatformError
from oarena.platform_scrims import ScrimCoordinator


OWN = "11111111-1111-4111-8111-111111111111"
OPPONENT = "3a7b78b8-5d79-4e55-94a3-7732fcaa4105"
SECOND = "7fd91e77-812c-44da-bce7-457be94d2548"


class FakePlatform:
    def __init__(self) -> None:
        self.profile_calls = 0
        self.match_calls = 0
        self.request_calls: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.request_errors: list[PlatformError] = []
        self.team_id = OWN
        self.team_name = "Alpha"
        self.submission_status: str | None = "ready"
        self.next_match_id: str | None = None

    def scrim_profile(self) -> dict[str, Any]:
        self.profile_calls += 1
        return {
            "team": {"id": self.team_id, "name": self.team_name},
            "active_submission": {
                "id": str(uuid.uuid4()),
                "version": 7,
                "name": "rush",
                "status": self.submission_status,
                "uploaded_at": "2026-08-05T20:00:00Z",
            },
        }

    def matches(self, **kwargs: Any) -> dict[str, Any]:
        self.match_calls += 1
        assert kwargs["match_type"] == "unrated"
        assert kwargs["mine"] is True
        return {"matches": list(self.rows), "next_cursor": None}

    def match(self, match_id: str) -> dict[str, Any]:
        row = next((row for row in self.rows if row.get("id") == match_id), None)
        if row is None:
            return {
                "match": {
                    "id": match_id,
                    "status": "queued",
                    "type": "unrated",
                    "rated": False,
                    "team_a": {"id": OWN, "name": "Alpha", "version": 7},
                    "team_b": {"id": OPPONENT, "name": "Pantheon", "version": None},
                    "winner_id": None,
                    "score_a": None,
                    "score_b": None,
                },
                "games": [],
            }
        return {"match": row, "games": []}

    def request_unrated(
        self,
        opponent_team_id: str,
        *,
        source_match_id: str | None = None,
        map_names: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        self.request_calls.append(
            {
                "opponent_team_id": opponent_team_id,
                "source_match_id": source_match_id,
                "map_names": map_names,
            }
        )
        if self.request_errors:
            raise self.request_errors.pop(0)
        return {"match_id": self.next_match_id or str(uuid.uuid4())}


def wait_for(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


def request_key() -> str:
    return str(uuid.uuid4())


def establish_identity(coordinator: ScrimCoordinator) -> None:
    coordinator.refresh()
    wait_for(lambda: coordinator._profile_fresh)


def test_fresh_coordinator_is_local_and_lazy(tmp_path: Path) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        snapshot = coordinator.snapshot()
        assert snapshot["autoscrim"]["enabled"] is False
        assert snapshot["autoscrim"]["state"] == "off"
        assert snapshot["requests"] == []
        assert platform.profile_calls == 0
        assert platform.match_calls == 0
    finally:
        coordinator.close()


def test_new_scrim_work_requires_a_fresh_ready_account_identity(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        with pytest.raises(ValueError, match="Refresh your FCode account"):
            coordinator.enqueue_manual(request_key(), OPPONENT)
        with pytest.raises(ValueError, match="Refresh your FCode account"):
            coordinator.configure_autoscrim(
                True,
                target_team_ids=(OPPONENT,),
                target_team_names={OPPONENT: "Pantheon"},
            )
        with pytest.raises(ValueError, match="Refresh your FCode account"):
            coordinator.configure_autoscrim(
                False,
                target_team_ids=(OPPONENT,),
                target_team_names={OPPONENT: "Pantheon"},
            )

        # The narrow emergency-off operation remains available even when the
        # current process has not verified the persisted account identity.
        assert coordinator.disable_autoscrim()["enabled"] is False
        assert coordinator.snapshot()["requests"] == []
        assert platform.profile_calls == 0

        establish_identity(coordinator)
        queued = coordinator.enqueue_manual(request_key(), OPPONENT)
        assert queued["our_version"] == 7
        with coordinator._lock:
            bound_team = coordinator._conn.execute(
                "SELECT own_team_id FROM requests WHERE request_key = ?",
                (queued["id"],),
            ).fetchone()[0]
        assert bound_team == OWN
    finally:
        coordinator.close()


def test_legacy_null_team_request_is_cancelled_not_adopted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scrims.db"
    initial = ScrimCoordinator(path, FakePlatform())
    initial.close()
    key = request_key()
    now = time.time()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO requests (request_key, source, requested_at, updated_at, "
            "opponent_team_id, status, not_before) VALUES (?,?,?,?,?,'queued',?)",
            (key, "manual", now, now, OPPONENT, now - 1),
        )

    platform = FakePlatform()
    coordinator = ScrimCoordinator(path, platform)
    try:
        wait_for(lambda: coordinator._profile_fresh)
        with sqlite3.connect(path) as connection:
            row = connection.execute(
                "SELECT status, own_team_id, error FROM requests WHERE request_key = ?",
                (key,),
            ).fetchone()
        assert row is not None
        assert row[0] == "cancelled"
        assert row[1] is None
        assert "before an FCode account identity" in row[2]
        assert coordinator.snapshot()["requests"] == []
        assert platform.request_calls == []
    finally:
        coordinator.close()


def test_non_ready_submission_cannot_create_scrim_work(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.submission_status = "processing"
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        with pytest.raises(ValueError, match="ready active FCode submission"):
            coordinator.enqueue_manual(request_key(), OPPONENT)
        with pytest.raises(ValueError, match="ready active FCode submission"):
            coordinator.configure_autoscrim(
                True,
                target_team_ids=(OPPONENT,),
                target_team_names={OPPONENT: "Pantheon"},
            )
        assert coordinator.snapshot()["requests"] == []
        assert platform.request_calls == []
    finally:
        coordinator.close()


def test_manual_request_is_persisted_and_idempotent(tmp_path: Path) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    key = request_key()
    try:
        establish_identity(coordinator)
        queued = coordinator.enqueue_manual(
            key,
            OPPONENT,
            opponent_team_name="Pantheon",
            map_names=("atoll",),
        )
        assert queued["status"] == "queued"
        wait_for(lambda: coordinator.snapshot()["requests"][0]["status"] == "accepted")
        accepted = coordinator.snapshot()["requests"][0]
        assert accepted["match_id"]
        assert accepted["our_version"] == 7
        assert platform.request_calls == [
            {
                "opponent_team_id": OPPONENT,
                "source_match_id": None,
                "map_names": ("atoll",),
            }
        ]

        duplicate = coordinator.enqueue_manual(
            key,
            OPPONENT,
            opponent_team_name="Pantheon",
            map_names=("atoll",),
        )
        assert duplicate["match_id"] == accepted["match_id"]
        assert len(platform.request_calls) == 1

        with pytest.raises(ValueError, match="different scrim request"):
            coordinator.enqueue_manual(key, SECOND)
    finally:
        coordinator.close()


def test_rate_limit_is_requeued_with_durable_backoff(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.request_errors.append(
        PlatformError(429, "five per ten minutes", retry_after_s=10)
    )
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.enqueue_manual(request_key(), OPPONENT)
        wait_for(lambda: coordinator.snapshot()["requests"][0]["attempts"] == 1)
        snapshot = coordinator.snapshot()
        assert snapshot["requests"][0]["status"] == "queued"
        assert snapshot["requests"][0]["error"] == "five per ten minutes"
        assert snapshot["autoscrim"]["state"] == "backoff"
        backoff = datetime.fromisoformat(
            snapshot["autoscrim"]["backoff_until"].replace("Z", "+00:00")
        ).timestamp()
        assert backoff > time.time() + 590
        assert len(platform.request_calls) == 1
    finally:
        coordinator.close()


def test_ambiguous_post_is_never_retried_and_pauses_auto(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.request_errors.append(
        PlatformError(504, "timed out", outcome_unknown=True)
    )
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.enqueue_manual(request_key(), OPPONENT)
        wait_for(lambda: coordinator.snapshot()["requests"][0]["status"] == "unknown")
        first = coordinator.snapshot()
        time.sleep(0.05)
        second = coordinator.snapshot()
        assert first["requests"][0]["attempts"] == 1
        assert second["requests"][0]["attempts"] == 1
        assert len(platform.request_calls) == 1
        assert second["autoscrim"]["state"] == "paused"
        assert second["autoscrim"]["can_request"] is False
    finally:
        coordinator.close()


def test_known_pre_send_transport_failure_is_safely_requeued(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.request_errors.append(
        PlatformError(502, "sidecar unavailable", outcome_unknown=False)
    )
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.enqueue_manual(request_key(), OPPONENT)
        wait_for(lambda: coordinator.snapshot()["requests"][0]["attempts"] == 1)
        snapshot = coordinator.snapshot()
        assert snapshot["requests"][0]["status"] == "queued"
        assert snapshot["requests"][0]["error"] == "sidecar unavailable"
        assert snapshot["autoscrim"]["state"] == "backoff"
        assert snapshot["autoscrim"]["enabled"] is False
        assert len(platform.request_calls) == 1
    finally:
        coordinator.close()


def test_restart_marks_interrupted_send_unknown(tmp_path: Path) -> None:
    path = tmp_path / "scrims.db"
    coordinator = ScrimCoordinator(path, FakePlatform())
    coordinator.close()
    now = time.time()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO requests (request_key, source, requested_at, updated_at, "
            "opponent_team_id, status, not_before) VALUES (?,?,?,?,?,'sending',?)",
            (request_key(), "manual", now, now, OPPONENT, now),
        )

    recovered = ScrimCoordinator(path, FakePlatform())
    try:
        def recovered_status() -> str | None:
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    "SELECT status FROM requests LIMIT 1"
                ).fetchone()
            return None if row is None else str(row[0])

        wait_for(lambda: recovered_status() == "unknown")
        snapshot = recovered.snapshot()
        with sqlite3.connect(path) as connection:
            row = connection.execute(
                "SELECT status, error FROM requests LIMIT 1"
            ).fetchone()
        assert row is not None and row[0] == "unknown"
        assert "restarted" in row[1].lower()
        assert snapshot["requests"] == []
        assert snapshot["autoscrim"]["state"] == "paused"
    finally:
        recovered.close()


def test_reconciliation_resolves_side_and_groups_official_versions(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    platform.rows = [
        {
            "id": str(uuid.uuid4()),
            "status": "complete",
            "type": "unrated",
            "rated": False,
            "team_a": {"id": OPPONENT, "name": "Pantheon", "version": 29},
            "team_b": {"id": OWN, "name": "Alpha", "version": 7},
            "winner_id": OPPONENT,
            "score_a": 4,
            "score_b": 1,
            "created_at": "2026-08-05T20:00:00Z",
            "completed_at": "2026-08-05T20:01:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "status": "complete",
            "type": "unrated",
            "rated": False,
            "team_a": {"id": OWN, "name": "Alpha", "version": 7},
            "team_b": {"id": OPPONENT, "name": "Pantheon", "version": 30},
            "winner_id": OWN,
            "score_a": 5,
            "score_b": 0,
            "created_at": "2026-08-05T21:00:00Z",
            "completed_at": "2026-08-05T21:01:00Z",
        },
    ]
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        coordinator.refresh()
        wait_for(lambda: coordinator.snapshot()["summary"]["matches"] == 2)
        snapshot = coordinator.snapshot()
        assert snapshot["summary"] == {
            "our_version": 7,
            "matches": 2,
            "match_wins": 1,
            "match_losses": 1,
            "match_draws": 0,
            "games_won": 6,
            "games_lost": 4,
            "games_drawn": 0,
            "win_rate": 0.6,
        }
        row = snapshot["by_opponent"][0]
        assert row["opponent"] == {"id": OPPONENT, "name": "Pantheon"}
        assert row["opponent_versions"] == [30, 29]
        assert row["last_played_at"] == "2026-08-05T21:01:00Z"
    finally:
        coordinator.close()


def test_only_official_unrated_rows_enter_scrim_statistics(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.rows = [
        {
            "id": str(uuid.uuid4()),
            "status": "complete",
            "type": "test",
            "rated": False,
            "team_a": {"id": OWN, "name": "Alpha", "version": 7},
            "team_b": {"id": OPPONENT, "name": "Pantheon", "version": 30},
            "winner_id": OWN,
            "score_a": 5,
            "score_b": 0,
        }
    ]
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        coordinator.refresh()
        wait_for(lambda: platform.match_calls >= 1)
        assert coordinator.snapshot()["summary"]["matches"] == 0
    finally:
        coordinator.close()


def test_pending_zero_scores_are_null_and_terminal_state_never_regresses(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    match_id = str(uuid.uuid4())
    platform.next_match_id = match_id
    queued = {
        "id": match_id,
        "status": "queued",
        "type": "unrated",
        "rated": False,
        "team_a": {"id": OWN, "name": "Alpha", "version": 7},
        "team_b": {"id": OPPONENT, "name": "Pantheon", "version": 30},
        "winner_id": None,
        "score_a": 0,
        "score_b": 0,
    }
    platform.rows = [queued]
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    key = request_key()
    try:
        establish_identity(coordinator)
        coordinator.enqueue_manual(key, OPPONENT)
        wait_for(lambda: coordinator.snapshot()["requests"][0]["status"] == "accepted")
        coordinator.refresh()
        wait_for(lambda: platform.match_calls >= 2)
        pending = coordinator.snapshot()["requests"][0]
        assert pending["score_for"] is None
        assert pending["score_against"] is None

        platform.rows = [
            {
                **queued,
                "status": "complete",
                "winner_id": OWN,
                "score_a": 5,
                "score_b": 0,
                "completed_at": "2026-08-06T03:55:00Z",
            }
        ]
        previous_calls = platform.match_calls
        coordinator.refresh()
        wait_for(lambda: platform.match_calls > previous_calls)
        wait_for(
            lambda: coordinator.snapshot()["requests"][0]["status"] == "complete"
        )

        platform.rows = [queued]
        previous_calls = platform.match_calls
        coordinator.refresh()
        wait_for(lambda: platform.match_calls > previous_calls)
        completed = coordinator.snapshot()["requests"][0]
        assert completed["status"] == "complete"
        assert completed["score_for"] == 5
        assert completed["score_against"] == 0
    finally:
        coordinator.close()


def test_malformed_active_submission_never_dispatches(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.submission_status = None
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        coordinator.refresh()
        wait_for(
            lambda: coordinator.snapshot()["autoscrim"]["last_error"]
            == "Invalid FCode active-submission response"
        )
        with pytest.raises(ValueError, match="Refresh your FCode account"):
            coordinator.enqueue_manual(request_key(), OPPONENT)
        snapshot = coordinator.snapshot()
        assert snapshot["autoscrim"]["can_request"] is False
        assert platform.request_calls == []
    finally:
        coordinator.close()


def test_team_change_pauses_autoscrim_and_scopes_stats(tmp_path: Path) -> None:
    platform = FakePlatform()
    platform.rows = [
        {
            "id": str(uuid.uuid4()),
            "status": "complete",
            "type": "unrated",
            "rated": False,
            "team_a": {"id": OWN, "name": "Alpha", "version": 7},
            "team_b": {"id": OPPONENT, "name": "Pantheon", "version": 30},
            "winner_id": OWN,
            "score_a": 5,
            "score_b": 0,
        }
    ]
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.configure_autoscrim(
            True,
            target_team_ids=(OPPONENT,),
            target_team_names={OPPONENT: "Pantheon"},
        )
        wait_for(lambda: coordinator.snapshot()["summary"]["matches"] == 1)

        platform.team_id = SECOND
        platform.team_name = "new team"
        platform.rows = []
        coordinator.refresh()
        wait_for(lambda: coordinator.snapshot()["session"]["team"]["id"] == SECOND)

        snapshot = coordinator.snapshot()
        assert snapshot["summary"]["matches"] == 0
        assert snapshot["autoscrim"]["enabled"] is False
        assert snapshot["autoscrim"]["state"] == "paused"
        assert "team changed" in snapshot["autoscrim"]["blocked_reason"].lower()
    finally:
        coordinator.close()


def test_identity_change_disables_self_target_without_scheduling_a_loop(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.configure_autoscrim(
            False,
            target_team_ids=(SECOND,),
            target_team_names={SECOND: "new team"},
        )

        platform.team_id = SECOND
        platform.team_name = "new team"
        coordinator.refresh()
        wait_for(lambda: coordinator.snapshot()["session"]["team"]["id"] == SECOND)

        snapshot = coordinator.snapshot()
        assert snapshot["autoscrim"]["enabled"] is False
        assert snapshot["autoscrim"]["state"] == "paused"
        assert "own team" in snapshot["autoscrim"]["blocked_reason"].lower()
        assert snapshot["autoscrim"]["target_team_ids"] == [SECOND]
        assert platform.request_calls == []
    finally:
        coordinator.close()


def test_local_rolling_gate_stops_after_five_posts(tmp_path: Path) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        for index in range(6):
            coordinator.enqueue_manual(
                request_key(),
                OPPONENT if index % 2 == 0 else SECOND,
            )
        wait_for(lambda: len(platform.request_calls) == 5)
        wait_for(lambda: coordinator.snapshot()["autoscrim"]["state"] == "backoff")
        snapshot = coordinator.snapshot()
        assert len(platform.request_calls) == 5
        assert sum(row["status"] == "queued" for row in snapshot["requests"]) == 1
    finally:
        coordinator.close()


def test_autoscrim_uses_explicit_target_and_can_be_disabled(tmp_path: Path) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        configured = coordinator.configure_autoscrim(
            True,
            target_team_ids=(OPPONENT,),
            target_team_names={OPPONENT: "Pantheon"},
            target_matches_per_version=2,
        )
        assert configured["enabled"] is True
        wait_for(lambda: len(platform.request_calls) == 1)
        snapshot = coordinator.snapshot()
        assert snapshot["requests"][0]["source"] == "auto"
        assert snapshot["requests"][0]["opponent"]["name"] == "Pantheon"

        disabled = coordinator.configure_autoscrim(
            False,
            target_team_ids=(OPPONENT,),
            target_team_names={OPPONENT: "Pantheon"},
            target_matches_per_version=2,
        )
        assert disabled["enabled"] is False

        preserved = coordinator.disable_autoscrim()
        assert preserved["enabled"] is False
        assert preserved["target_team_ids"] == [OPPONENT]
    finally:
        coordinator.close()


def test_rate_limit_never_pauses_autoscrim_and_learns_the_stated_quota(
    tmp_path: Path,
) -> None:
    """A retuned upstream quota must slow autoscrim down, not stop it.

    The platform restates its limit whenever the organisers change it. Treating
    an unfamiliar wording as a rejection used to disable autoscrim overnight,
    which is the failure this guards.
    """
    platform = FakePlatform()
    platform.request_errors.append(
        PlatformError(
            429, "Rate limit exceeded: max 3 test/unrated matches per 5 minutes"
        )
    )
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.configure_autoscrim(
            True,
            target_team_ids=(OPPONENT,),
            target_team_names={OPPONENT: "Pantheon"},
        )
        wait_for(lambda: len(platform.request_calls) == 1)
        wait_for(lambda: coordinator.snapshot()["autoscrim"]["state"] == "backoff")

        snapshot = coordinator.snapshot()
        auto = snapshot["autoscrim"]
        assert auto["enabled"] is True
        assert auto["state"] == "backoff"
        assert auto["rate_limited"] is True
        assert auto["blocked_reason"] == "FCode request cooldown"
        # The request keeps its place in the queue instead of being cancelled.
        assert snapshot["requests"][0]["status"] == "queued"
        # Pacing now follows the quota FCode actually stated.
        assert snapshot["quota"] == {
            "limit": 3,
            "window_s": 300.0,
            "used": 1,
            "learned": True,
        }
        backoff = datetime.fromisoformat(
            auto["backoff_until"].replace("Z", "+00:00")
        ).timestamp()
        assert time.time() + 290 < backoff < time.time() + 700
    finally:
        coordinator.close()


def test_a_single_rejected_auto_request_backs_off_and_keeps_going(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    platform.request_errors.append(PlatformError(400, "Opponent is unavailable"))
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        coordinator.configure_autoscrim(
            True,
            target_team_ids=(OPPONENT, SECOND),
            target_team_names={OPPONENT: "Pantheon", SECOND: "Something Else"},
        )
        wait_for(lambda: len(platform.request_calls) == 1)
        wait_for(lambda: coordinator.snapshot()["autoscrim"]["state"] == "backoff")

        auto = coordinator.snapshot()["autoscrim"]
        assert auto["enabled"] is True
        assert auto["consecutive_failures"] == 1
        assert auto["rate_limited"] is False
    finally:
        coordinator.close()


def test_autoscrim_stops_once_rejections_are_clearly_persistent(
    tmp_path: Path,
) -> None:
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        with coordinator._lock:
            coordinator._conn.execute(
                "UPDATE settings SET consecutive_failures = 4 WHERE id = 1"
            )
            coordinator._conn.commit()
        platform.request_errors.append(PlatformError(400, "Opponent is unavailable"))
        coordinator.configure_autoscrim(
            True,
            target_team_ids=(OPPONENT,),
            target_team_names={OPPONENT: "Pantheon"},
        )
        wait_for(lambda: coordinator.snapshot()["autoscrim"]["state"] == "paused")

        auto = coordinator.snapshot()["autoscrim"]
        assert auto["enabled"] is False
        assert "rejected requests" in auto["blocked_reason"]
    finally:
        coordinator.close()


def test_autoscrim_paces_itself_to_the_learned_quota(tmp_path: Path) -> None:
    """Spread requests across the window instead of bursting into a stall."""
    platform = FakePlatform()
    coordinator = ScrimCoordinator(tmp_path / "scrims.db", platform)
    try:
        establish_identity(coordinator)
        # Default guess: 5 per 10 minutes -> 125s floor still applies.
        with coordinator._lock:
            assert coordinator._auto_cadence_locked() == 125.0
            coordinator._conn.execute(
                "UPDATE settings SET rate_limit_max = 5, rate_limit_window_s = 1200.0 "
                "WHERE id = 1"
            )
            coordinator._conn.commit()
            # 5 per 20 minutes is one every 4 minutes, plus the safety margin.
            assert coordinator._auto_cadence_locked() == 245.0
    finally:
        coordinator.close()
