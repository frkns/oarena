from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from oarena.platform_history import PlatformVersionHistory


MATCH_1 = "00000000-0000-4000-8000-000000000001"
MATCH_2 = "00000000-0000-4000-8000-000000000002"
MATCH_3 = "00000000-0000-4000-8000-000000000003"
TEAM_A = "10000000-0000-4000-8000-000000000001"
TEAM_B = "10000000-0000-4000-8000-000000000002"
TEAM_C = "10000000-0000-4000-8000-000000000003"
# Backfill reasons about "now" against real match timestamps, so its tests need
# a clock on the same scale as the fixtures rather than an arbitrary number.
NOW = 1_785_715_200.0  # 2026-08-03T00:00:00Z
HOUR = 3600.0
DAY = 24.0 * HOUR


class Platform:
    def __init__(self, pages: list[dict[str, Any]] | None = None) -> None:
        self.pages = list(pages or [])
        self.calls: list[dict[str, Any]] = []

    def matches(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self.pages:
            return {"matches": [], "next_cursor": None}
        return self.pages.pop(0)


class TypedPlatform:
    """A platform whose feeds are independent and addressed by cursor.

    The simple fake serves one shared list in call order, which lets a forward
    sync silently consume the page a backfill was about to resume from -- a
    fixture artefact that hides real paging bugs rather than exposing them.
    """

    def __init__(self, feeds: dict[str, dict[Any, dict[str, Any]]]) -> None:
        self.feeds = {kind: dict(pages) for kind, pages in feeds.items()}
        self.calls: list[dict[str, Any]] = []

    def matches(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        pages = self.feeds.get(str(kwargs.get("match_type")), {})
        return pages.get(kwargs.get("cursor"), {"matches": [], "next_cursor": None})

    def calls_for(self, match_type: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["match_type"] == match_type]


def match(
    match_id: str,
    version_a: int,
    when: str,
    *,
    version_b: int = 1,
    kind: str = "ladder",
    source_a: str | None = None,
    source_b: str | None = None,
    winner: str | None = None,
    status: str = "complete",
    score_a: int | None = None,
    score_b: int | None = None,
) -> dict[str, Any]:
    return {
        "id": match_id,
        "type": kind,
        "status": status,
        "source_match_a_id": source_a,
        "source_match_b_id": source_b,
        "winner_id": winner,
        "score_a": score_a,
        "score_b": score_b,
        "created_at": when,
        "completed_at": when,
        "team_a": {"id": TEAM_A, "name": "Alpha", "version": version_a},
        "team_b": {"id": TEAM_B, "name": "Beta", "version": version_b},
    }


def ladder() -> dict[str, Any]:
    return {
        "rankings": [
            {"rank": 1, "team_id": TEAM_A, "team_name": "Alpha", "rating": 1},
            {"rank": 2, "team_id": TEAM_B, "team_name": "Beta", "rating": 0},
        ],
        "total": 2,
    }


def wait_for_refresh(history: PlatformVersionHistory) -> dict[str, Any]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = history.request_refresh()
        if not status["refreshing"]:
            return status
        time.sleep(0.01)
    raise AssertionError("refresh did not finish")


def wait_until_idle(history: PlatformVersionHistory) -> dict[str, Any]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = history.status()
        if not status["refreshing"]:
            return status
        time.sleep(0.01)
    raise AssertionError("refresh did not become idle")


def test_persists_ordered_transitions_and_reactivation(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    history = PlatformVersionHistory(path, Platform())
    original = ladder()
    # Deliberately arrive newest-first. Consecutive observations of v1 are one
    # run, while returning to v1 after v2 is a new, known transition.
    assert history.observe_matches(
        [
            match(MATCH_3, 1, "2026-08-03T00:00:00Z"),
            match(MATCH_1, 1, "2026-08-01T00:00:00Z"),
            match(MATCH_2, 2, "2026-08-02T00:00:00Z"),
        ]
    ) == 6
    assert history.observe_matches([match(MATCH_1, 9, "2026-08-01T00:00:00Z")]) == 0
    history.close()

    reopened = PlatformVersionHistory(path, Platform())
    enriched = reopened.enrich_ladder(original)
    assert enriched is not original
    assert enriched["rankings"] is not original["rankings"]
    alpha = enriched["rankings"][0]
    assert alpha["bot_version"] == 1
    assert alpha["version_first_seen_at"] == "2026-08-03T00:00:00Z"
    assert alpha["version_transition_known"] is True
    # `ordinal` is the stored run index, counting oldest-first, and is what
    # addresses a run when its games are expanded.
    assert alpha["version_history"] == [
        {
            "ordinal": 2,
            "version": 1,
            "first_seen_at": "2026-08-03T00:00:00Z",
            "last_seen_at": "2026-08-03T00:00:00Z",
            "transition_known": True,
        },
        {
            "ordinal": 1,
            "version": 2,
            "first_seen_at": "2026-08-02T00:00:00Z",
            "last_seen_at": "2026-08-02T00:00:00Z",
            "transition_known": True,
        },
        {
            "ordinal": 0,
            "version": 1,
            "first_seen_at": "2026-08-01T00:00:00Z",
            "last_seen_at": "2026-08-01T00:00:00Z",
            "transition_known": False,
        },
    ]
    assert original["rankings"][0].get("bot_version") is None
    reopened.close()

    # Ladder reads use compact transition rows, not the growing match archive.
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM version_runs WHERE team_id = ?", (TEAM_A,)
        ).fetchone()[0] == 3


def test_history_returns_full_runs_newest_first_and_latest_team_name(
    tmp_path: Path,
) -> None:
    platform = Platform()
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", platform)
    rows = []
    for day in range(1, 11):
        row = match(
            f"00000000-0000-4000-8000-{day:012d}",
            1 if day % 2 else 2,
            f"2026-08-{day:02d}T00:00:00Z",
        )
        if day == 10:
            row["team_a"]["name"] = "Alpha Prime"
        rows.append(row)
    assert history.observe_matches(list(reversed(rows))) == 20

    result = history.history()
    assert result["total"] == 2
    assert result["observed_from"] == "2026-08-01T00:00:00Z"
    assert result["observed_through"] == "2026-08-10T00:00:00Z"
    assert [team["team_id"] for team in result["teams"]] == [TEAM_A, TEAM_B]

    alpha = result["teams"][0]
    assert alpha["team_name"] == "Alpha Prime"
    assert alpha["current_version"] == 2
    assert alpha["observed_from"] == "2026-08-01T00:00:00Z"
    assert alpha["observed_through"] == "2026-08-10T00:00:00Z"
    # Unlike the compact ladder annotation, the dedicated read returns every
    # activation run, including both reactivations of the same version.
    assert len(alpha["runs"]) == 10
    assert [run["version"] for run in alpha["runs"]] == [2, 1] * 5
    assert alpha["runs"][0] == {
        "ordinal": 9,
        "version": 2,
        "first_seen_at": "2026-08-10T00:00:00Z",
        "last_seen_at": "2026-08-10T00:00:00Z",
        "transition_known": True,
    }
    assert alpha["runs"][-1] == {
        "ordinal": 0,
        "version": 1,
        "first_seen_at": "2026-08-01T00:00:00Z",
        "last_seen_at": "2026-08-01T00:00:00Z",
        "transition_known": False,
    }
    # Newest first for display, but the ordinals still count from the oldest.
    assert [run["ordinal"] for run in alpha["runs"]] == list(range(9, -1, -1))
    assert result["teams"][1]["runs"] == [
        {
            "ordinal": 0,
            "version": 1,
            "first_seen_at": "2026-08-01T00:00:00Z",
            "last_seen_at": "2026-08-10T00:00:00Z",
            "transition_known": False,
        }
    ]
    assert platform.calls == []
    history.close()


def test_history_filters_bounds_limits_and_empty_results(tmp_path: Path) -> None:
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    assert history.history() == {
        "teams": [],
        "total": 0,
        "observed_from": None,
        "observed_through": None,
    }
    newest = match(MATCH_2, 2, "2026-08-02T00:00:00Z")
    newest["team_b"] = {"id": TEAM_C, "name": "Gamma", "version": 3}
    assert history.observe_matches(
        [newest, match(MATCH_1, 1, "2026-08-01T00:00:00Z")]
    ) == 4

    limited = history.history(limit=2)
    assert limited["total"] == 3
    # Latest activity sorts first; equal timestamps have a stable UUID tie-break.
    assert [team["team_id"] for team in limited["teams"]] == [TEAM_A, TEAM_C]
    # Pagination does not narrow the overall observation window.
    assert limited["observed_from"] == "2026-08-01T00:00:00Z"
    assert limited["observed_through"] == "2026-08-02T00:00:00Z"

    selected = history.history(team_id=TEAM_B.upper(), limit=1)
    assert selected["total"] == 1
    assert [team["team_id"] for team in selected["teams"]] == [TEAM_B]
    assert selected["teams"][0]["current_version"] == 1
    assert selected["observed_from"] == "2026-08-01T00:00:00Z"
    assert selected["observed_through"] == "2026-08-01T00:00:00Z"

    for invalid in (0, 201, True, "1"):
        with pytest.raises(ValueError, match="limit must be between"):
            history.history(limit=invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="team_id must be a UUID"):
        history.history(team_id="not-a-team")
    history.close()


def test_history_read_and_close_are_lifecycle_safe(tmp_path: Path) -> None:
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    assert history.observe_matches(
        [match(MATCH_1, 1, "2026-08-01T00:00:00Z")]
    ) == 2
    entered_read = threading.Event()
    close_started = threading.Event()
    close_done = threading.Event()
    result: list[dict[str, Any]] = []
    errors: list[BaseException] = []
    original_require_open = history._require_open

    def require_open() -> None:
        original_require_open()
        entered_read.set()

    def read() -> None:
        try:
            result.append(history.history())
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    def close() -> None:
        close_started.set()
        history.close()
        close_done.set()

    history._require_open = require_open  # type: ignore[method-assign]
    history._lock.acquire()
    reader = threading.Thread(target=read)
    closer = threading.Thread(target=close)
    try:
        reader.start()
        assert entered_read.wait(1)
        closer.start()
        assert close_started.wait(1)
        assert not close_done.wait(0.05)
    finally:
        history._lock.release()
    reader.join(timeout=1)
    closer.join(timeout=1)

    assert not reader.is_alive()
    assert not closer.is_alive()
    assert errors == []
    assert result[0]["teams"][0]["current_version"] == 1
    with pytest.raises(ValueError, match="closed"):
        history.history()


def test_ignores_unknown_types_and_malformed_rows(tmp_path: Path) -> None:
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    invalid = [
        match(MATCH_1, 1, "2026-08-01T00:00:00Z", kind="scrimmage"),
        match("not-a-uuid", 1, "2026-08-01T00:00:00Z"),
        match(MATCH_1, 0, "2026-08-01T00:00:00Z", version_b=0),
        match(MATCH_1, True, "2026-08-01T00:00:00Z", version_b=True),
        match(MATCH_1, 1, "not-a-date"),
    ]
    too_long = match(MATCH_1, 1, "2026-08-01T00:00:00Z")
    too_long["team_a"]["name"] = "x" * 201
    invalid.append(too_long)
    assert history.observe_matches(invalid) == 0
    assert history.enrich_ladder(ladder())["rankings"][0]["version_history"] == []
    history.close()


def test_unrated_games_are_observed_alongside_ladder_games(tmp_path: Path) -> None:
    """Unrated games run continuously and sharpen when a change is placed."""
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    assert (
        history.observe_matches(
            [
                match(MATCH_1, 1, "2026-08-01T00:00:00Z"),
                match(MATCH_2, 2, "2026-08-01T00:05:00Z", kind="unrated"),
                match(MATCH_3, 2, "2026-08-01T00:10:00Z"),
            ]
        )
        == 6
    )
    runs = history.enrich_ladder(ladder())["rankings"][0]["version_history"]

    assert [run["version"] for run in runs] == [2, 1]
    # The switch is placed by the unrated game, ten minutes before the ladder
    # round that would otherwise have been the first sighting of v2.
    assert runs[0]["first_seen_at"] == "2026-08-01T00:05:00Z"
    history.close()


def test_a_pinned_side_is_skipped_without_discarding_its_opponent(
    tmp_path: Path,
) -> None:
    """One side replaying an old submission must not cost the other its sighting.

    About a fifth of unrated matches pin exactly one side, so dropping the whole
    match would throw away that much of the feed.
    """
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    accepted = history.observe_matches(
        [match(MATCH_1, 9, "2026-08-01T00:00:00Z", kind="unrated", source_a=MATCH_2)]
    )

    assert accepted == 1
    rankings = history.enrich_ladder(ladder())["rankings"]
    # Alpha was pinned to an old v9, so nothing is claimed about it.
    assert rankings[0]["version_history"] == []
    # Beta played live and is recorded.
    assert [run["version"] for run in rankings[1]["version_history"]] == [1]
    history.close()


def test_materialization_migrates_existing_observations(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    history = PlatformVersionHistory(path, Platform())
    assert history.observe_matches(
        [match(MATCH_1, 7, "2026-08-01T00:00:00Z")]
    ) == 2
    history.close()
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM version_runs")
        connection.execute(
            "UPDATE version_sync_state SET runs_schema_version = 0 WHERE id = 1"
        )

    migrated = PlatformVersionHistory(path, Platform())
    assert migrated.enrich_ladder(ladder())["rankings"][0]["bot_version"] == 7
    migrated.close()


def test_refresh_is_bounded_and_cadence_persists(tmp_path: Path) -> None:
    now = [1000.0]
    pages = [
        {"matches": [match(MATCH_1, 1, "2026-08-01T00:00:00Z")], "next_cursor": "a"},
        {"matches": [match(MATCH_2, 2, "2026-08-02T00:00:00Z")], "next_cursor": "b"},
        {"matches": [match(MATCH_3, 3, "2026-08-03T00:00:00Z")], "next_cursor": "c"},
    ]
    platform = Platform(pages)
    path = tmp_path / "history.sqlite3"
    history = PlatformVersionHistory(
        path,
        platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        initial_pages=2,
        # Isolate the forward sync; backfill paging has its own tests.
        backfill_window_s=0.0,
    )
    assert history.request_refresh()["started"] is True
    status = wait_for_refresh(history)
    assert status["initial_sync_complete"] is True
    # Two bounded pages per feed, and nothing beyond them.
    assert len(platform.calls) == 4
    assert platform.calls[0] == {
        "limit": 100,
        "match_type": "ladder",
        "mine": False,
        "team_id": None,
        "cursor": None,
    }
    assert platform.calls[1]["cursor"] == "a"
    assert [call["match_type"] for call in platform.calls] == [
        "ladder",
        "ladder",
        "unrated",
        "unrated",
    ]
    # Each feed is paged from its own head, never continuing the other's cursor.
    assert platform.calls[2]["cursor"] is None
    assert history.request_refresh()["started"] is False
    history.close()

    # Cadence and initial-sync state survive a hot reload/new process. Once the
    # cadence expires, only one recent page is fetched.
    later_platform = Platform(
        [{"matches": [match(MATCH_3, 3, "2026-08-03T00:00:00Z")], "next_cursor": "more"}]
    )
    reopened = PlatformVersionHistory(
        path,
        later_platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        backfill_window_s=0.0,
    )
    assert reopened.request_refresh()["started"] is False
    now[0] += 61
    assert reopened.request_refresh()["started"] is True
    wait_for_refresh(reopened)
    assert len(later_platform.calls) == 2
    reopened.close()


def test_background_errors_are_private_and_do_not_escape(tmp_path: Path) -> None:
    class Broken(Platform):
        def matches(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            raise RuntimeError("secret-token-and-raw-response")

    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3", Broken(), refresh_interval_s=1
    )
    assert history.request_refresh()["started"] is True
    status = wait_for_refresh(history)
    assert status["initial_sync_complete"] is False
    assert status["last_error"] == "refresh failed (RuntimeError)"
    assert status["last_sync_at"] is None
    assert status["last_attempt_at"] is not None
    assert "secret" not in repr(status)
    history.close()


def test_cancellation_between_initial_pages_remains_immediately_due(
    tmp_path: Path,
) -> None:
    platform = Platform(
        [
            {
                "matches": [match(MATCH_1, 1, "2026-08-01T00:00:00Z")],
                "next_cursor": "next",
            }
        ]
    )
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3", platform, initial_pages=2
    )
    observe = history.observe_matches

    def observe_then_cancel(rows: Any) -> int:
        inserted = observe(rows)
        history._stop.set()
        return inserted

    history.observe_matches = observe_then_cancel  # type: ignore[method-assign]
    assert history.request_refresh()["started"] is True
    status = wait_until_idle(history)
    assert status["initial_sync_complete"] is False
    assert status["last_attempt_at"] is None
    assert status["last_error"] is None
    assert status["due"] is True
    assert len(platform.calls) == 1
    history.close()


def test_cancelled_error_retry_preserves_short_retry_cadence(tmp_path: Path) -> None:
    now = [1000.0]

    class Broken(Platform):
        def matches(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            raise RuntimeError("upstream failed")

    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3",
        Broken(),
        clock=lambda: now[0],
        refresh_interval_s=300,
    )
    assert history.request_refresh()["started"] is True
    failed = wait_for_refresh(history)
    assert failed["last_error"] == "refresh failed (RuntimeError)"

    now[0] += 61
    history.platform = Platform(
        [{"matches": [match(MATCH_1, 1, "2026-08-01T00:00:00Z")], "next_cursor": "next"}]
    )
    observe = history.observe_matches

    def observe_then_cancel(rows: Any) -> int:
        inserted = observe(rows)
        history._stop.set()
        return inserted

    history.observe_matches = observe_then_cancel  # type: ignore[method-assign]
    assert history.request_refresh()["started"] is True
    cancelled = wait_until_idle(history)
    assert cancelled["last_error"] == "refresh failed (RuntimeError)"
    assert cancelled["due"] is True
    assert cancelled["next_refresh_at"] == "1970-01-01T00:17:40Z"
    history.close()


def test_refresh_claim_is_cross_instance_and_shutdown_does_not_wait_for_rpc(
    tmp_path: Path,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    class Blocking(Platform):
        def matches(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            entered.set()
            assert release.wait(2)
            return {"matches": [], "next_cursor": None}

    path = tmp_path / "history.sqlite3"
    platform = Blocking()
    first = PlatformVersionHistory(path, platform)
    second = PlatformVersionHistory(path, platform)
    assert first.request_refresh()["started"] is True
    assert entered.wait(1)
    assert second.request_refresh()["started"] is False
    assert second.status()["refreshing"] is True
    assert len(platform.calls) == 1

    worker = first._thread
    started = time.monotonic()
    first.close()
    assert time.monotonic() - started < 1
    release.set()
    assert worker is not None
    worker.join(timeout=2)
    assert not worker.is_alive()

    # Cancellation cleared the abandoned claim, so a replacement process can
    # refresh immediately instead of waiting for the stale-claim timeout.
    replacement_platform = Platform([{"matches": [], "next_cursor": None}])
    replacement = PlatformVersionHistory(path, replacement_platform)
    assert replacement.request_refresh()["started"] is True
    wait_for_refresh(replacement)
    replacement.close()
    second.close()


def test_status_recovers_orphaned_hot_reload_claim(tmp_path: Path) -> None:
    now = [1000.0]
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3", Platform(), clock=lambda: now[0]
    )
    with history._lock, history._conn:
        history._conn.execute(
            "UPDATE version_sync_state SET last_started_at = ?, "
            "last_finished_at = NULL WHERE id = 1",
            (now[0],),
        )

    status = history.status()
    assert status["refreshing"] is False
    assert status["due"] is True
    assert status["next_refresh_at"] == "1970-01-01T00:16:40Z"
    history.close()


def test_backfill_pages_backwards_to_the_window_across_cycles(tmp_path: Path) -> None:
    """Reaching back is spread over cycles and resumes where it stopped.

    Restarting at the head each cycle would re-fetch the same pages forever and
    never reach the rest of the window.
    """
    now = [NOW]
    platform = TypedPlatform(
        {
            "unrated": {
                None: {
                    "matches": [match(MATCH_1, 1, "2026-08-01T12:00:00Z", kind="unrated")],
                    "next_cursor": "older-1",
                },
                "older-1": {
                    "matches": [match(MATCH_2, 1, "2026-08-01T00:00:00Z", kind="unrated")],
                    "next_cursor": "older-2",
                },
            }
        }
    )
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3",
        platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        initial_pages=1,
        # Both fixture matches sit inside this window, so paging never reaches
        # the target and must continue on the next cycle.
        backfill_window_s=30.0 * DAY,
        backfill_pages_per_cycle=1,
    )
    try:
        history.request_refresh()
        wait_for_refresh(history)
        first = {row["match_type"]: row for row in history.backfill_state()}
        assert first["unrated"]["complete"] is False
        assert first["unrated"]["pages_used"] == 1
        assert first["unrated"]["covered_from"] == "2026-08-01T12:00:00Z"

        now[0] += 61
        history.request_refresh()
        wait_for_refresh(history)
        second = {row["match_type"]: row for row in history.backfill_state()}
        assert second["unrated"]["pages_used"] == 2
        assert second["unrated"]["covered_from"] == "2026-08-01T00:00:00Z"
        # A head page per cycle for the forward sync, then a backfill that
        # resumed from the saved cursor rather than restarting at the head.
        assert [call["cursor"] for call in platform.calls_for("unrated")] == [
            None,
            None,
            None,
            "older-1",
        ]
    finally:
        history.close()


def test_backfill_stops_once_the_window_is_covered(tmp_path: Path) -> None:
    now = [NOW]
    platform = TypedPlatform(
        {
            "unrated": {
                None: {
                    # Already older than the window, so one page is enough and
                    # the remaining cursor is deliberately never followed.
                    "matches": [match(MATCH_1, 1, "2026-08-02T00:00:00Z", kind="unrated")],
                    "next_cursor": "older",
                },
                "older": {
                    "matches": [match(MATCH_2, 1, "2026-08-01T00:00:00Z", kind="unrated")],
                    "next_cursor": "older-still",
                },
            }
        }
    )
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3",
        platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        initial_pages=1,
        backfill_window_s=12.0 * HOUR,
        backfill_pages_per_cycle=10,
    )
    try:
        history.request_refresh()
        wait_for_refresh(history)
        state = {row["match_type"]: row for row in history.backfill_state()}
        assert state["unrated"]["complete"] is True
        # Complete because the window is covered, not because the feed ran out.
        assert state["unrated"]["exhausted"] is False
        # The deeper page was never fetched.
        assert "older" not in [call["cursor"] for call in platform.calls_for("unrated")]

        # A later cycle must not start a new walk over a covered window.
        before = len(platform.calls_for("unrated"))
        now[0] += 61
        history.request_refresh()
        wait_for_refresh(history)
        # Only the forward sync's head read.
        assert len(platform.calls_for("unrated")) == before + 1
    finally:
        history.close()


def test_an_existing_database_walks_the_window_once_then_stops(tmp_path: Path) -> None:
    """One pass over the window, not a pass every cycle.

    History collected before outcomes were recorded still needs re-reading once,
    but a walk that has covered the window must not start again on its own.
    """
    now = [NOW]
    path = tmp_path / "history.sqlite3"
    seed = PlatformVersionHistory(path, Platform(), backfill_window_s=0.0)
    seed.observe_matches([match(MATCH_1, 1, "2026-08-01T00:00:00Z")])
    seed.close()

    platform = TypedPlatform(
        {
            "ladder": {
                None: {
                    "matches": [match(MATCH_2, 1, "2026-08-02T00:00:00Z")],
                    "next_cursor": "older",
                },
                "older": {
                    "matches": [match(MATCH_3, 1, "2026-08-01T00:00:00Z")],
                    "next_cursor": None,
                },
            }
        }
    )
    history = PlatformVersionHistory(
        path,
        platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        initial_pages=1,
        backfill_window_s=12.0 * HOUR,
        backfill_pages_per_cycle=10,
    )
    try:
        assert history.backfill_state()[0]["complete"] is False

        history.request_refresh()
        wait_for_refresh(history)
        state = {row["match_type"]: row for row in history.backfill_state()}
        assert state["ladder"]["complete"] is True
        assert state["ladder"]["walked_to"] == "2026-08-02T00:00:00Z"

        after_first = len(platform.calls_for("ladder"))
        now[0] += 61
        history.request_refresh()
        wait_for_refresh(history)
        # Only the forward sync's head read; no second walk.
        assert len(platform.calls_for("ladder")) == after_first + 1
    finally:
        history.close()


def test_outcomes_that_never_settle_do_not_reopen_the_backfill(
    tmp_path: Path,
) -> None:
    """A match that errors upstream never gets a result, and that is not work.

    Treating a nonzero count of missing outcomes as unfinished work would walk
    the same window on every cycle, forever.
    """
    now = [NOW]
    # Inside the window and old enough to be settled, so it is genuinely
    # counted as a missing outcome rather than filtered out by either bound.
    stuck = match(MATCH_1, 1, "2026-08-02T18:00:00Z", status="error")
    platform = TypedPlatform(
        {"ladder": {None: {"matches": [stuck], "next_cursor": None}}}
    )
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3",
        platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        initial_pages=1,
        backfill_window_s=12.0 * HOUR,
        backfill_pages_per_cycle=10,
    )
    try:
        history.request_refresh()
        wait_for_refresh(history)
        state = {row["match_type"]: row for row in history.backfill_state()}

        # The outcome is still missing, and stays missing...
        assert state["ladder"]["missing_results"] == 2
        # ...but the window has been walked, so there is nothing left to do.
        assert state["ladder"]["complete"] is True

        after_first = len(platform.calls_for("ladder"))
        now[0] += 61
        history.request_refresh()
        wait_for_refresh(history)
        assert len(platform.calls_for("ladder")) == after_first + 1
    finally:
        history.close()


def test_run_games_lists_only_the_games_played_on_that_version(
    tmp_path: Path,
) -> None:
    # An hour after the last fixture match, so results are settled but the
    # "never recorded" fallback has not kicked in.
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3", Platform(), clock=lambda: 1_785_542_400.0 + 1800
    )
    try:
        history.observe_matches(
            [
                match(MATCH_1, 5, "2026-08-01T00:00:00Z", winner=TEAM_A,
                      score_a=5, score_b=0),
                match(MATCH_2, 5, "2026-08-01T00:10:00Z", kind="unrated",
                      winner=TEAM_B, score_a=2, score_b=3),
                match(MATCH_3, 6, "2026-08-01T00:20:00Z", winner=None,
                      score_a=2, score_b=2),
            ]
        )

        first = history.run_games(team_id=TEAM_A, ordinal=0)
        assert first["version"] == 5
        assert first["total"] == 2
        assert first["record"] == {
            "wins": 1,
            "losses": 1,
            "draws": 0,
            "undecided": 0,
            "unknown": 0,
        }
        # Newest first, matching the timeline it expands from.
        assert [game["match_id"] for game in first["games"]] == [MATCH_2, MATCH_1]
        assert first["games"][0]["match_type"] == "unrated"
        assert first["games"][0]["opponent_name"] == "Beta"
        # A 5-0 must survive: zero is a score, not a missing value.
        assert first["games"][1]["score_for"] == 5
        assert first["games"][1]["score_against"] == 0

        second = history.run_games(team_id=TEAM_A, ordinal=1)
        assert second["version"] == 6
        assert [game["match_id"] for game in second["games"]] == [MATCH_3]
        assert second["record"]["draws"] == 1

        assert history.run_games(team_id=TEAM_A, ordinal=9)["games"] == []
    finally:
        history.close()


def test_run_games_separates_a_reactivated_version_from_its_first_run(
    tmp_path: Path,
) -> None:
    """v5 -> v6 -> v5 is three runs, and the two v5 runs are not merged.

    Selecting by version and time range would pull both v5 runs together; runs
    are recomputed instead so each expansion shows only its own games.
    """
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    try:
        history.observe_matches(
            [
                match(MATCH_1, 5, "2026-08-01T00:00:00Z"),
                match(MATCH_2, 6, "2026-08-01T00:10:00Z"),
                match(MATCH_3, 5, "2026-08-01T00:20:00Z"),
            ]
        )

        assert history.run_games(team_id=TEAM_A, ordinal=0)["version"] == 5
        assert [
            game["match_id"] for game in history.run_games(team_id=TEAM_A, ordinal=0)["games"]
        ] == [MATCH_1]
        assert [
            game["match_id"] for game in history.run_games(team_id=TEAM_A, ordinal=2)["games"]
        ] == [MATCH_3]
    finally:
        history.close()


def test_run_games_rejects_bad_input(tmp_path: Path) -> None:
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    try:
        with pytest.raises(ValueError, match="team_id"):
            history.run_games(team_id="nope", ordinal=0)
        with pytest.raises(ValueError, match="ordinal"):
            history.run_games(team_id=TEAM_A, ordinal=-1)
        with pytest.raises(ValueError, match="limit"):
            history.run_games(team_id=TEAM_A, ordinal=0, limit=0)
    finally:
        history.close()


def test_an_unfinished_match_settles_its_result_without_moving_the_run(
    tmp_path: Path,
) -> None:
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3", Platform(), clock=lambda: 1_785_542_400.0 + 60
    )
    try:
        running = match(MATCH_1, 5, "2026-08-01T00:00:00Z", status="running")
        assert history.observe_matches([running]) == 2
        assert history.run_games(team_id=TEAM_A, ordinal=0)["record"]["undecided"] == 1

        finished = match(
            MATCH_1, 5, "2026-08-01T00:00:00Z", winner=TEAM_A, score_a=5, score_b=1
        )
        # Already known, so nothing new is inserted...
        assert history.observe_matches([finished]) == 0
        # ...but the outcome is allowed to settle.
        run = history.run_games(team_id=TEAM_A, ordinal=0)
        assert run["record"] == {
            "wins": 1,
            "losses": 0,
            "draws": 0,
            "undecided": 0,
            "unknown": 0,
        }
        assert run["games"][0]["score_for"] == 5
    finally:
        history.close()


def test_a_stale_backfill_table_shape_is_replaced_not_fatal(tmp_path: Path) -> None:
    """An older progress table must not stop the tracker from opening.

    The table carries only resumable paging state, so replacing it costs one
    re-page and loses nothing that was observed.
    """
    path = tmp_path / "history.sqlite3"
    seed = PlatformVersionHistory(path, Platform(), backfill_window_s=0.0)
    seed.observe_matches([match(MATCH_1, 1, "2026-08-01T00:00:00Z")])
    seed.close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE version_backfill")
        connection.execute(
            "CREATE TABLE version_backfill (match_type TEXT PRIMARY KEY, "
            "covered_from REAL, cursor TEXT NOT NULL DEFAULT '', "
            "pages_used INTEGER NOT NULL DEFAULT 0, "
            "done INTEGER NOT NULL DEFAULT 0, updated_at REAL)"
        )
        connection.execute(
            "INSERT INTO version_backfill (match_type, done) VALUES ('ladder', 1)"
        )

    reopened = PlatformVersionHistory(path, Platform(), backfill_window_s=0.0)
    try:
        state = {row["match_type"]: row for row in reopened.backfill_state()}
        assert set(state) == {"ladder", "unrated"}
        # The observations, which are the actual data, are untouched.
        assert state["ladder"]["covered_from"] == "2026-08-01T00:00:00Z"
    finally:
        reopened.close()


def test_a_long_finished_match_without_an_outcome_is_unknown_not_running(
    tmp_path: Path,
) -> None:
    """Rows stored before outcomes were tracked must not claim to be in progress."""
    history = PlatformVersionHistory(
        tmp_path / "history.sqlite3",
        Platform(),
        # A week after the match: nothing that old is still being played.
        clock=lambda: 1_785_542_400.0 + 7 * DAY,
    )
    try:
        history.observe_matches(
            [match(MATCH_1, 5, "2026-08-01T00:00:00Z", status="running")]
        )
        run = history.run_games(team_id=TEAM_A, ordinal=0)

        assert run["games"][0]["result"] == "unknown"
        assert run["record"]["unknown"] == 1
        assert run["record"]["undecided"] == 0
    finally:
        history.close()


def test_missing_outcomes_inside_the_window_keep_the_backfill_working(
    tmp_path: Path,
) -> None:
    """Coverage alone is not enough: a run of blank results is not usable.

    Ladder history collected before outcomes were recorded reaches far enough
    back but expands into games with no result, so filling those counts as work.
    """
    now = [NOW]
    path = tmp_path / "history.sqlite3"
    seed = PlatformVersionHistory(path, Platform(), backfill_window_s=0.0)
    # Old enough to be settled, recent enough to sit inside the window.
    seed.observe_matches(
        [match(MATCH_1, 1, "2026-08-02T12:00:00Z", status="running")]
    )
    seed.close()

    platform = TypedPlatform(
        {
            "ladder": {
                None: {
                    "matches": [
                        match(
                            MATCH_1,
                            1,
                            "2026-08-02T12:00:00Z",
                            winner=TEAM_A,
                            score_a=5,
                            score_b=2,
                        )
                    ],
                    "next_cursor": None,
                }
            }
        }
    )
    history = PlatformVersionHistory(
        path,
        platform,
        clock=lambda: now[0],
        refresh_interval_s=60,
        initial_pages=1,
        backfill_window_s=2.0 * DAY,
        backfill_pages_per_cycle=5,
    )
    try:
        before = {row["match_type"]: row for row in history.backfill_state()}
        # One match, but a row per team.
        assert before["ladder"]["missing_results"] == 2
        assert before["ladder"]["complete"] is False

        history.request_refresh()
        wait_for_refresh(history)

        after = {row["match_type"]: row for row in history.backfill_state()}
        # The walk re-read the window and the outcome settled in passing.
        assert after["ladder"]["missing_results"] == 0
        assert after["ladder"]["complete"] is True
        run = history.run_games(team_id=TEAM_A, ordinal=0)
        assert run["record"]["wins"] == 1
    finally:
        history.close()


def test_match_runs_reports_what_each_team_played_in_one_match(
    tmp_path: Path,
) -> None:
    """The match detail has no versions upstream; the observation does."""
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    try:
        history.observe_matches(
            [
                match(MATCH_1, 5, "2026-08-01T00:00:00Z", version_b=20),
                match(MATCH_2, 6, "2026-08-01T00:10:00Z", version_b=21),
            ]
        )

        result = history.match_runs(match_id=MATCH_2)
        assert result["match_id"] == MATCH_2
        played = {row["team_id"]: row for row in result["teams"]}
        assert played[TEAM_A]["version"] == 6
        assert played[TEAM_A]["ordinal"] == 1
        assert played[TEAM_B]["version"] == 21
        assert played[TEAM_B]["ordinal"] == 1

        earlier = {row["team_id"]: row for row in history.match_runs(match_id=MATCH_1)["teams"]}
        assert earlier[TEAM_A] == {"team_id": TEAM_A, "version": 5, "ordinal": 0}
    finally:
        history.close()


def test_match_runs_picks_the_right_run_of_a_reactivated_version(
    tmp_path: Path,
) -> None:
    """Position in the series, not the version, identifies the run.

    A whole ladder round shares one timestamp, so locating a reactivated version
    by time could land on the wrong run; the match's own place in the series
    cannot.
    """
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    try:
        history.observe_matches(
            [
                match(MATCH_1, 5, "2026-08-01T00:00:00Z"),
                match(MATCH_2, 6, "2026-08-01T00:00:00Z"),
                match(MATCH_3, 5, "2026-08-01T00:00:00Z"),
            ]
        )

        first = history.match_runs(match_id=MATCH_1)["teams"][0]
        again = history.match_runs(match_id=MATCH_3)["teams"][0]

        assert first["version"] == again["version"] == 5
        # Same version, same second, different runs.
        assert first["ordinal"] == 0
        assert again["ordinal"] == 2
    finally:
        history.close()


def test_match_runs_is_empty_for_a_match_that_was_never_observed(
    tmp_path: Path,
) -> None:
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    try:
        assert history.match_runs(match_id=MATCH_1) == {
            "match_id": MATCH_1,
            "teams": [],
        }
        with pytest.raises(ValueError, match="match_id"):
            history.match_runs(match_id="not-a-uuid")
    finally:
        history.close()


def test_match_runs_omits_a_pinned_side(tmp_path: Path) -> None:
    """A side replaying an old submission was never recorded, so it is absent."""
    history = PlatformVersionHistory(tmp_path / "history.sqlite3", Platform())
    try:
        history.observe_matches(
            [match(MATCH_1, 9, "2026-08-01T00:00:00Z", kind="unrated", source_a=MATCH_2)]
        )
        teams = history.match_runs(match_id=MATCH_1)["teams"]

        assert [row["team_id"] for row in teams] == [TEAM_B]
    finally:
        history.close()
