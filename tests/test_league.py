"""`oarena.league`: discovery, planning, the run loop and the rating rules.

Every game here is played by the in-process fake runner (see
``tests/fake_worker.py``), so a full "match" completes in milliseconds while
still going through the pool, the run thread and :meth:`League.finish`.
"""

from __future__ import annotations

import dataclasses
import shutil
import time
from pathlib import Path

import pytest

from conftest import Project, write_bot
from fake_worker import FAKE_FCODE_METADATA, FAKE_FCODE_VERSION
from oarena.bots import BotError
from oarena.league import Job, League, SyncReport
from oarena.runner import GameOutcome, GameSpec, PlayerResult
from oarena.store import Store, StoreBatchError, StoreBusyError


def run(league: League, jobs: list[Job], *, timeout: float = 30.0) -> None:
    """Start a match and block until the run thread has exited."""
    league.start_match(jobs)
    assert league.wait(timeout=timeout), "the run thread did not finish"


def outcome(status: str = "ok", winner: str | None = "a", **kwargs: object) -> GameOutcome:
    kwargs.setdefault("fcode_version", FAKE_FCODE_VERSION)
    kwargs.setdefault("fcode_metadata", FAKE_FCODE_METADATA)
    return GameOutcome(status=status, winner=winner, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# sync
# --------------------------------------------------------------------------- #


def test_sync_registers_every_bot_on_disk(project: Project) -> None:
    report = project.league.sync()

    assert sorted(report.added) == ["alpha", "beta", "gamma"]
    assert report.changed == report.missing == report.unbroken == []
    assert project.names() == ["alpha", "beta", "gamma"]
    assert [e["name"] for e in project.types("bot_added")] == ["alpha", "beta", "gamma"]


def test_sync_is_idempotent(project: Project) -> None:
    project.league.sync()
    again = project.league.sync()

    assert again.empty
    assert isinstance(again, SyncReport)


def test_sync_records_the_initial_rating_and_version(project: Project) -> None:
    project.league.sync()
    bot = project.store.get_bot("alpha")

    assert bot is not None
    assert bot.rating == project.rater.initial()
    assert bot.src_hash
    assert [v[1] for v in project.store.versions("alpha")] == [bot.src_hash]


def test_verify_only_partial_sync_never_rewrites_the_shared_catalog(
    project: Project, tmp_path: Path
) -> None:
    project.league.sync()
    alpha_before = project.store.get_bot("alpha")
    assert alpha_before is not None
    frozen = tmp_path / "frozen-bots"
    shutil.copytree(project.cfg.bots_dir / "alpha", frozen / "alpha")
    cfg = dataclasses.replace(
        project.cfg,
        bots_dir=frozen,
        deactivate_missing_bots=False,
        bot_sync_mode="verify-only",
    )
    shared = League(cfg, project.store, project.bus, project.rater)

    assert shared.sync().empty
    alpha_after = project.store.get_bot("alpha")
    beta_after = project.store.get_bot("beta")
    assert alpha_after is not None and beta_after is not None
    assert (alpha_after.dir, alpha_after.entry, alpha_after.src_hash) == (
        alpha_before.dir,
        alpha_before.entry,
        alpha_before.src_hash,
    )
    assert beta_after.active

    (frozen / "alpha" / "main.py").write_text("# changed after freeze\n", encoding="utf-8")
    with pytest.raises(BotError, match="does not match shared-league hash"):
        shared.sync()


def test_sync_detects_a_source_change_and_reinflates_sigma(project: Project) -> None:
    project.league.sync()
    project.store.set_rating("alpha", project.rater.initial().__class__(30.0, 0.5))

    project.add_bot("alpha", "# rewritten\n")
    report = project.league.sync()

    bot = project.store.get_bot("alpha")
    assert report.changed == ["alpha"]
    assert bot is not None
    assert bot.mu == pytest.approx(30.0)
    assert bot.sigma == pytest.approx(project.rater.sigma0 * project.cfg.sigma_reinflate)
    assert len(project.store.versions("alpha")) == 2
    assert project.types("bot_changed")[-1]["name"] == "alpha"


def test_start_match_rescans_sources_before_its_first_game(project: Project) -> None:
    """An edit between dashboard visits must not require pressing Sync first."""
    project.league.sync()
    project.store.set_rating("alpha", project.rater.initial().__class__(30.0, 0.5))
    project.add_bot("alpha", "# v2\n")

    jobs = project.league.plan_match(
        "alpha", "beta", maps=["sprint"], mirror=False, rated=False
    )
    project.league.start_match(jobs)
    assert project.league.wait(timeout=30.0)

    bot = project.store.get_bot("alpha")
    assert bot is not None
    assert bot.mu == pytest.approx(30.0)
    assert bot.sigma == pytest.approx(project.rater.sigma0 * project.cfg.sigma_reinflate)
    assert len(project.store.versions("alpha")) == 2


def test_force_stop_clears_queued_games(project: Project) -> None:
    project.runner.delay = 0.05
    jobs = project.league.plan_match("alpha", "beta", repeat=40)
    project.league.start_match(jobs, workers=1)
    time.sleep(0.02)

    project.league.force_stop()
    assert project.league.wait(timeout=30.0)
    assert project.store.game_count() < len(jobs)
    assert project.types("run_finished")[-1]["stopped"] is True


def test_shutdown_force_stop_discards_cancelled_game_rows(project: Project) -> None:
    project.runner.delay = 0.1
    jobs = project.league.plan_match("alpha", "beta", repeat=20)
    project.league.start_match(jobs, workers=1)
    time.sleep(0.02)

    project.league.force_stop(discard_cancelled=True)
    assert project.league.wait(timeout=30.0)
    assert project.store.game_count() == 0


def test_a_changed_bot_is_unbroken(project: Project) -> None:
    project.league.sync()
    project.store.set_broken("alpha", True, "ImportError: boom")

    project.add_bot("alpha", "# fixed\n")
    report = project.league.sync()

    bot = project.store.get_bot("alpha")
    assert report.unbroken == ["alpha"]
    assert bot is not None and bot.broken is False
    assert project.types("bot_fixed")[-1]["name"] == "alpha"


def test_sync_deactivates_a_bot_whose_directory_vanished(project: Project) -> None:
    project.league.sync()
    import shutil

    shutil.rmtree(project.cfg.bots_dir / "gamma")

    report = project.league.sync()

    assert report.missing == ["gamma"]
    bot = project.store.get_bot("gamma")
    assert bot is not None and bot.active is False
    # A second sync must not report it again.
    assert project.league.sync().missing == []


def test_sync_refreshes_a_moved_bot_directory(project: Project) -> None:
    project.league.sync()
    project.store.set_paths("alpha", "/stale", "/stale/main.py")

    project.league.sync()

    bot = project.store.get_bot("alpha")
    assert bot is not None
    assert bot.dir == str(project.cfg.bots_dir / "alpha")


def test_resolve_syncs_on_a_miss(project: Project) -> None:
    project.add_bot("delta")
    src = project.league.resolve("delta")

    assert src.name == "delta"
    assert project.store.get_bot("delta") is not None


def test_resolve_raises_for_an_unknown_bot(project: Project) -> None:
    with pytest.raises(BotError):
        project.league.resolve("nonexistent")


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #


def test_plan_match_counts_maps_rounds_and_sides(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", repeat=2, mirror=True)

    assert len(jobs) == 3 * 2 * 2  # 3 maps × 2 rounds × 2 sides
    assert {j.map for j in jobs} == {"sprint", "duel", "pinch"}
    assert all(j.rated and j.tag == "match" for j in jobs)


def test_plan_match_without_mirroring(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", mirror=False)

    assert len(jobs) == 3
    assert all((j.a, j.b) == ("alpha", "beta") for j in jobs)


def test_plan_match_mirrors_on_the_same_map_and_seed(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", maps=["sprint"], mirror=True)

    first, second = jobs
    assert (first.a, first.b) == ("alpha", "beta")
    assert (second.a, second.b) == ("beta", "alpha")
    assert first.map == second.map
    assert first.seed == second.seed


def test_plan_match_is_map_major(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", repeat=2, mirror=False)
    # Round 1 covers every map before round 2 starts.
    assert [j.map for j in jobs[:3]] == ["sprint", "duel", "pinch"]
    assert [j.map for j in jobs[3:]] == ["sprint", "duel", "pinch"]


def test_plan_match_honours_a_map_request(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", maps=["duel"], mirror=False)
    assert {j.map for j in jobs} == {"duel"}


def test_plan_match_can_run_an_extra_map(project: Project) -> None:
    project.cfg.extra_maps_dir.mkdir(parents=True)
    extra = project.cfg.extra_maps_dir / "generated.map26"
    shutil.copy2(project.cfg.maps_dir / "sprint.map26", extra)

    jobs = project.league.plan_match(
        "alpha", "beta", maps=["generated"], mirror=False, rated=False
    )

    assert len(jobs) == 1
    assert jobs[0].map_path == str(extra.resolve())
    run(project.league, jobs)
    assert project.runner.calls[-1].map.path == extra.resolve()


def test_match_executes_an_external_map_path(project: Project, tmp_path: Path) -> None:
    external = tmp_path / "fresh" / "unseen.map26"
    external.parent.mkdir()
    shutil.copy2(project.cfg.maps_dir / "sprint.map26", external)

    jobs = project.league.plan_match(
        "alpha", "beta", maps=[str(external)], mirror=False, rated=False
    )

    assert len(jobs) == 1
    assert jobs[0].map == "unseen"
    assert jobs[0].map_path == str(external.resolve())
    run(project.league, jobs)
    assert project.runner.calls[-1].map.path == external.resolve()


def test_plan_match_forces_a_self_match_unrated(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "alpha", maps=["sprint"], rated=True)
    assert jobs and all(j.rated is False for j in jobs)


def test_plan_match_uses_fixed_seeds_when_configured(project: Project) -> None:
    cfg = dataclasses.replace(project.cfg, seed_policy="fixed", seed=100)
    league = League(cfg, project.store, project.bus, project.rater)

    jobs = league.plan_match("alpha", "beta", maps=["sprint"], repeat=3, mirror=False)

    assert [j.seed for j in jobs] == [100, 101, 102]


def test_plan_match_uses_random_seeds_by_default(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", repeat=4, mirror=False)
    seeds = {j.seed for j in jobs}
    assert len(seeds) > 1
    assert all(1 <= s < 2**31 for s in seeds)


def test_plan_match_uses_the_config_mirror_default(project: Project) -> None:
    cfg = dataclasses.replace(project.cfg, mirror=False)
    league = League(cfg, project.store, project.bus, project.rater)
    assert len(league.plan_match("alpha", "beta", maps=["sprint"])) == 1


# --------------------------------------------------------------------------- #
# the run loop
# --------------------------------------------------------------------------- #


def test_a_match_plays_every_job_and_stores_it(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", maps=["sprint", "duel"])
    run(project.league, jobs)

    assert project.store.game_count() == len(jobs)
    assert len(project.runner.calls) == len(jobs)
    assert project.league.running is False
    assert project.league.status["done"] == len(jobs)
    assert project.league.status["total"] == len(jobs)


def test_a_match_emits_the_run_lifecycle(project: Project) -> None:
    jobs = project.league.plan_match("alpha", "beta", maps=["sprint"], mirror=False)
    run(project.league, jobs)

    started = project.types("run_started")
    finished = project.types("run_finished")
    assert started and started[0] == {
        "mode": "match",
        "total": 1,
        "label": "alpha vs beta · 1 game",
        "batch_tag": None,
    }
    assert finished and finished[0] == {
        "mode": "match",
        "played": 1,
        "stopped": False,
        "batch_tag": None,
    }
    assert len(project.types("game_started")) == 1
    assert len(project.types("game_finished")) == 1
    assert project.types("status")


def test_tagged_match_has_immutable_batch_ordinals_and_source_hashes(
    project: Project,
) -> None:
    jobs = project.league.plan_match("alpha", "beta", maps=["sprint"])
    project.league.start_match(jobs, batch_tag="codex_gate_alpha_v1")
    assert project.league.wait(timeout=30.0)

    assert project.types("run_started")[-1]["batch_tag"] == "codex_gate_alpha_v1"
    assert project.types("run_finished")[-1]["batch_tag"] == "codex_gate_alpha_v1"

    games = sorted(
        project.store.list_games(tag="codex_gate_alpha_v1"),
        key=lambda game: game.batch_ordinal if game.batch_ordinal is not None else -1,
    )
    assert [game.batch_ordinal for game in games] == list(range(len(jobs)))
    hashes = {
        name: project.store.get_bot(name).src_hash  # type: ignore[union-attr]
        for name in ("alpha", "beta")
    }
    for game in games:
        assert game.a_src_hash == hashes[game.a]
        assert game.b_src_hash == hashes[game.b]
    batch = project.store.batch("codex_gate_alpha_v1")
    assert batch is not None
    assert (
        batch["mode"],
        batch["status"],
        batch["requested_games"],
        batch["played_games"],
    ) == ("match", "completed", len(jobs), len(jobs))

    with pytest.raises(StoreBatchError, match="already reserved"):
        project.league.start_match(jobs, batch_tag="codex_gate_alpha_v1")


def test_run_writer_lease_blocks_a_separate_store_for_the_whole_run(
    project: Project,
) -> None:
    project.runner.delay = 0.2
    other = Store(project.cfg.db_path)
    jobs = project.league.plan_match("alpha", "beta", maps=["sprint"])
    project.league.start_match(jobs, workers=1, batch_tag="codex_lock_test_v1")
    try:
        deadline = time.monotonic() + 5.0
        while not project.league.running and time.monotonic() < deadline:
            time.sleep(0.01)
        assert other.get_bot("alpha") is not None
        with pytest.raises(StoreBusyError):
            project.store.set_note("alpha", "wrong thread")
        with pytest.raises(StoreBusyError):
            other.set_note("alpha", "must wait")
    finally:
        project.league.stop()
        assert project.league.wait(timeout=30.0)
        other.close()


def test_game_finished_carries_the_game_and_the_score_deltas(project: Project) -> None:
    run(project.league, project.league.plan_match("alpha", "beta", maps=["sprint"], mirror=False))

    payload = project.types("game_finished")[-1]
    assert payload["game"]["a"] == "alpha"
    assert payload["game"]["winner"] == "a"
    assert set(payload["delta"]) == {"alpha", "beta"}
    assert payload["delta"]["alpha"] > 0


def test_the_spec_handed_to_the_runner_reflects_the_config(project: Project) -> None:
    run(project.league, project.league.plan_match("alpha", "beta", maps=["sprint"], mirror=False))

    spec: GameSpec = project.runner.calls[0]
    assert spec.a.name == "alpha" and spec.b.name == "beta"
    assert spec.map.name == "sprint"
    assert spec.tle_ms == project.cfg.tle_ms
    assert spec.timeout_s == project.cfg.game_timeout_s
    assert spec.cwd == project.cfg.root
    assert spec.tmp_dir == project.cfg.tmp_dir


def test_starting_a_second_run_is_refused(project: Project) -> None:
    project.runner.delay = 0.2
    jobs = project.league.plan_match("alpha", "beta")
    project.league.start_match(jobs)
    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            project.league.start_match(jobs)
    finally:
        project.league.stop()
        project.league.wait(timeout=30.0)


def test_stop_ends_a_run_early(project: Project) -> None:
    project.runner.delay = 0.05
    jobs = project.league.plan_match("alpha", "beta", repeat=40)
    project.league.start_match(jobs, workers=1)
    time.sleep(0.15)
    project.league.stop()

    assert project.league.wait(timeout=30.0)
    assert project.store.game_count() < len(jobs)
    assert project.types("run_finished")[-1]["stopped"] is True


def test_stop_is_a_no_op_when_idle(project: Project) -> None:
    project.league.stop()
    assert project.league.running is False


def test_an_arena_stops_after_its_game_limit(project: Project) -> None:
    project.league.sync()
    project.league.start_arena("ladder", limit=6)
    assert project.league.wait(timeout=30.0)

    assert project.store.game_count() == 6
    assert project.league.status["mode"] == "arena"


def test_an_arena_queues_mirrored_pairs(project: Project) -> None:
    project.league.sync()
    project.league.start_arena("rr", limit=4)
    assert project.league.wait(timeout=30.0)

    # Games run concurrently, so completion order says nothing about submission
    # order — the invariant is on the multiset: every (map, seed) group must hold
    # both orderings of the same pair, which is what cancels turn-order bias.
    groups: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for game in project.store.list_games(limit=10):
        groups.setdefault((game.map, game.seed), []).append((game.a, game.b))

    assert groups, "the arena recorded no games"
    for (game_map, seed), sides in groups.items():
        assert len(sides) == 2, f"{game_map}/{seed} is not a mirrored pair: {sides}"
        (a1, b1), (a2, b2) = sides
        assert (a1, b1) == (b2, a2), f"{game_map}/{seed} was not mirrored: {sides}"


def test_a_vs_arena_always_involves_its_target(project: Project) -> None:
    project.league.sync()
    project.league.start_arena("vs", target="beta", limit=4)
    assert project.league.wait(timeout=30.0)

    for game in project.store.list_games(limit=10):
        assert "beta" in (game.a, game.b)
    assert project.league.status["mode"] == "vs"


def test_a_vs_arena_keeps_matching_a_broken_target(project: Project) -> None:
    project.league.sync()
    project.store.set_broken("beta", True, "SyntaxError")
    project.runner.status_for["beta"] = "loadfail"

    project.league.start_arena("vs", target="beta", limit=4)
    assert project.league.wait(timeout=30.0)

    games = project.store.list_games(limit=10)
    assert len(games) == 4
    assert all("beta" in (game.a, game.b) for game in games)
    assert all(game.rated and game.a_errors + game.b_errors == 1 for game in games)
    assert project.store.get_bot("beta").broken is True  # type: ignore[union-attr]


def test_an_unknown_matchmaker_is_rejected_before_the_thread_starts(project: Project) -> None:
    with pytest.raises(ValueError):
        project.league.start_arena("nonsense")
    assert project.league.running is False


def test_status_shape(project: Project) -> None:
    status = project.league.status
    for key in (
        "running", "mode", "label", "queued", "in_flight", "done", "total",
        "started", "rate", "workers", "stopping", "live",
    ):
        assert key in status, key
    assert status["running"] is False
    assert status["live"] == []


def test_status_reports_live_games(project: Project) -> None:
    project.runner.delay = 0.3
    project.league.start_match(project.league.plan_match("alpha", "beta"), workers=2)
    try:
        deadline = time.monotonic() + 5.0
        live: list[dict] = []
        while time.monotonic() < deadline and not live:
            live = project.league.status["live"]
            time.sleep(0.02)
        assert live
        assert set(live[0]) == {"a", "b", "map", "seed", "since"}
        assert project.league.status["workers"] == 2
    finally:
        project.league.stop()
        project.league.wait(timeout=30.0)


# --------------------------------------------------------------------------- #
# finish(): the rating rules
# --------------------------------------------------------------------------- #


def test_a_rated_game_moves_both_ratings(project: Project) -> None:
    project.league.sync()
    before_a = project.store.get_bot("alpha").rating  # type: ignore[union-attr]
    before_b = project.store.get_bot("beta").rating  # type: ignore[union-attr]

    game = project.league.finish(Job("alpha", "beta", "sprint", 1), outcome())

    after_a = project.store.get_bot("alpha").rating  # type: ignore[union-attr]
    after_b = project.store.get_bot("beta").rating  # type: ignore[union-attr]
    assert game.rated is True
    assert after_a.mu > before_a.mu and after_b.mu < before_b.mu
    assert game.a_mu_before == pytest.approx(before_a.mu)
    assert game.a_mu_after == pytest.approx(after_a.mu)
    assert game.b_mu_before == pytest.approx(before_b.mu)
    assert game.b_mu_after == pytest.approx(after_b.mu)
    published = project.types("game_finished")[-1]["game"]
    assert published["fcode_version"] == FAKE_FCODE_VERSION
    assert published["has_fcode_metadata"] is True
    assert "fcode_metadata" not in published


def test_an_unrated_job_never_touches_the_ladder(project: Project) -> None:
    project.league.sync()
    before = project.store.get_bot("alpha").rating  # type: ignore[union-attr]

    game = project.league.finish(Job("alpha", "beta", "sprint", 1, rated=False), outcome())

    assert game.rated is False
    assert game.a_mu_after is None
    assert project.store.get_bot("alpha").rating == before  # type: ignore[union-attr]


def test_a_self_match_is_forced_unrated(project: Project) -> None:
    project.league.sync()
    before = project.store.get_bot("alpha").rating  # type: ignore[union-attr]

    game = project.league.finish(Job("alpha", "alpha", "sprint", 1, rated=True), outcome())

    assert game.rated is False
    assert project.store.get_bot("alpha").rating == before  # type: ignore[union-attr]


def test_a_coinflip_stays_rated_but_becomes_a_draw(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(winner="a", win_condition="coinflip"),
    )

    assert game.rated is True
    assert game.winner == "draw"
    assert game.win_condition == "coinflip"


def test_a_coinflip_is_kept_when_the_config_says_so(project: Project) -> None:
    cfg = dataclasses.replace(project.cfg, coinflip_is_draw=False)
    league = League(cfg, project.store, project.bus, project.rater)
    league.sync()

    game = league.finish(
        Job("alpha", "beta", "sprint", 1), outcome(winner="a", win_condition="coinflip")
    )

    assert game.winner == "a"


def test_a_load_failure_is_a_counted_loss_and_breaks_the_bot(project: Project) -> None:
    project.league.sync()
    before = project.store.get_bot("alpha").rating  # type: ignore[union-attr]

    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(status="loadfail_a", winner=None, error="ImportError: boom"),
    )

    bot = project.store.get_bot("alpha")
    assert game.rated is True
    assert game.winner == "b"
    assert game.win_condition == "bot_error"
    assert (game.a_errors, game.b_errors) == (1, 0)
    assert bot is not None and bot.broken is True
    assert bot.broken_reason == "ImportError: boom"
    assert bot.rating.score < before.score
    assert project.types("bot_broken")[-1] == {"name": "alpha", "reason": "ImportError: boom"}


def test_a_load_failure_on_side_b_is_a_loss_for_the_right_bot(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(status="loadfail_b", winner=None, error="SyntaxError"),
    )

    assert game.winner == "a"
    assert (game.a_errors, game.b_errors) == (0, 1)
    assert project.store.get_bot("beta").broken is True  # type: ignore[union-attr]
    assert project.store.get_bot("alpha").broken is False  # type: ignore[union-attr]


def test_both_load_failures_are_counted_broken_and_unrated(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(
            status="loadfail_both",
            winner=None,
            error="A=SyntaxError: bad A; B=SyntaxError: bad B",
        ),
    )

    assert game.rated is False
    assert game.winner is None
    assert game.win_condition == "bot_error_both"
    assert (game.a_errors, game.b_errors) == (1, 1)
    assert project.store.get_bot("alpha").broken is True  # type: ignore[union-attr]
    assert project.store.get_bot("beta").broken is True  # type: ignore[union-attr]


def test_both_load_failures_in_a_self_match_count_once(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "alpha", "sprint", 1),
        outcome(status="loadfail_both", winner=None, error="both invalid"),
    )

    assert game.rated is False
    assert game.winner is None
    assert (game.a_errors, game.b_errors) == (1, 0)
    assert [event["name"] for event in project.types("bot_broken")] == ["alpha"]


def test_one_sided_runtime_error_overrides_the_engine_winner(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(
            winner="a",
            win_condition="coinflip",
            a=PlayerResult(errors=2),
        ),
    )

    assert game.status == "ok"
    assert game.rated is True
    assert game.winner == "b"
    assert game.win_condition == "bot_error"
    assert game.a_errors == 2


def test_attributed_error_that_panics_the_engine_is_a_loss(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(
            status="engine_error",
            winner=None,
            error="RuntimeError: panic",
            a=PlayerResult(errors=1),
        ),
    )

    assert game.rated is True
    assert game.winner == "b"
    assert game.win_condition == "bot_error"


def test_errors_on_both_sides_have_no_winner_or_rating(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(a=PlayerResult(errors=1), b=PlayerResult(errors=3)),
    )

    assert game.rated is False
    assert game.winner is None
    assert game.win_condition == "bot_error_both"


def test_runtime_error_in_a_self_match_has_no_winner_or_rating(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "alpha", "sprint", 1),
        outcome(a=PlayerResult(errors=1)),
    )

    assert game.rated is False
    assert game.winner is None


def test_an_errored_clean_result_does_not_clear_that_bots_broken_flag(
    project: Project,
) -> None:
    project.league.sync()
    project.store.set_broken("alpha", True, "old load failure")
    project.store.set_broken("beta", True, "old load failure")

    project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(a=PlayerResult(errors=1)),
    )

    assert project.store.get_bot("alpha").broken is True  # type: ignore[union-attr]
    assert project.store.get_bot("beta").broken is False  # type: ignore[union-attr]


def test_a_clean_game_unbreaks_both_bots(project: Project) -> None:
    project.league.sync()
    project.store.set_broken("alpha", True, "ImportError")

    project.league.finish(Job("alpha", "beta", "sprint", 1), outcome())

    assert project.store.get_bot("alpha").broken is False  # type: ignore[union-attr]
    assert project.types("bot_fixed")[-1]["name"] == "alpha"


@pytest.mark.parametrize("status", ["timeout", "killed", "engine_error"])
def test_engine_failures_are_unrated_and_logged(project: Project, status: str) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1), outcome(status=status, winner=None, error="boom")
    )

    assert game.rated is False
    assert game.status == status
    warnings = [e for e in project.types("log") if e["level"] == "warn"]
    assert warnings and status in warnings[-1]["msg"]


def test_error_counts_and_engine_numbers_are_persisted(project: Project) -> None:
    project.league.sync()
    game = project.league.finish(
        Job("alpha", "beta", "sprint", 42, tag="vs"),
        outcome(
            turns=812,
            duration_ms=999,
            resign_message="gave up",
            a=PlayerResult(titanium=1, mined=2, units=3, buildings=4, errors=5),
            b=PlayerResult(titanium=6, mined=7, units=8, buildings=9, errors=10),
        ),
    )

    stored = project.store.get_game(game.id)
    assert stored is not None
    assert (stored.a_titanium, stored.a_mined, stored.a_units) == (1, 2, 3)
    assert (stored.a_errors, stored.b_errors) == (5, 10)
    assert stored.turns == 812 and stored.duration_ms == 999
    assert stored.resign_message == "gave up"
    assert stored.seed == 42 and stored.tag == "vs"


# --------------------------------------------------------------------------- #
# finish(): files
# --------------------------------------------------------------------------- #


def _temp_files(project: Project) -> tuple[Path, Path]:
    project.cfg.tmp_dir.mkdir(parents=True, exist_ok=True)
    replay = project.cfg.tmp_dir / "scratch.replay26"
    log = project.cfg.tmp_dir / "scratch.log"
    replay.write_bytes(b"R" * 128)
    log.write_text("Traceback (most recent call last):\nValueError\n", encoding="utf-8")
    return replay, log


def test_a_clean_game_keeps_its_replay_and_log_under_the_game_id(project: Project) -> None:
    project.league.sync()
    replay, log = _temp_files(project)

    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1), outcome(replay_path=replay, log_path=log)
    )

    assert game.replay == f"{game.id}.replay26"
    assert game.log == f"{game.id}.log"
    assert (project.cfg.replay_dir / game.replay).is_file()
    assert (project.cfg.log_dir / game.log).is_file()
    assert not replay.exists() and not log.exists()
    stored = project.store.get_game(game.id)
    assert stored is not None and stored.replay == game.replay
    assert stored.fcode_version == FAKE_FCODE_VERSION
    assert stored.fcode_metadata_json == (
        '{"direction_deltas":{},"enums":{},"game_constants":{"MAX_TURNS":1000},'
        '"metadata_version":1,"version":"test-fcode-1"}'
    )


def test_a_clean_game_without_provenance_is_rated_but_drops_its_replay(
    project: Project,
) -> None:
    project.league.sync()
    replay, log = _temp_files(project)

    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(
            replay_path=replay,
            log_path=log,
            fcode_version="",
            fcode_metadata=None,
        ),
    )

    assert game.rated is True
    assert game.status == "ok"
    assert game.replay == ""
    assert game.log == f"{game.id}.log"
    assert not replay.exists()
    stored = project.store.get_game(game.id)
    assert stored is not None
    assert stored.fcode_version == ""
    assert stored.fcode_metadata_json == ""
    warnings = [event for event in project.types("log") if event["level"] == "warn"]
    assert "valid per-game fcode metadata was unavailable" in warnings[-1]["msg"]


def test_a_failed_game_keeps_the_log_but_drops_the_replay(project: Project) -> None:
    project.league.sync()
    replay, log = _temp_files(project)

    game = project.league.finish(
        Job("alpha", "beta", "sprint", 1),
        outcome(status="timeout", winner=None, replay_path=replay, log_path=log),
    )

    assert game.replay == ""
    assert game.log == f"{game.id}.log"
    assert not replay.exists()
    assert list(project.cfg.replay_dir.glob("*.replay26")) == []


def test_the_replay_budget_prunes_the_oldest(project: Project) -> None:
    cfg = dataclasses.replace(project.cfg, replay_budget_mb=1)
    league = League(cfg, project.store, project.bus, project.rater)
    league.sync()

    ids: list[int] = []
    for _ in range(3):
        replay = cfg.tmp_dir / "big.replay26"
        replay.write_bytes(b"R" * 600_000)
        ids.append(league.finish(Job("alpha", "beta", "sprint", 1), outcome(replay_path=replay)).id)

    pruned = league.enforce_replay_budget()

    assert pruned == 2  # 3 × 600 KB > 1 MB, so only the newest survives
    kept = dict(project.store.replay_files())
    assert list(kept) == [ids[-1]]
    assert not (cfg.replay_dir / f"{ids[0]}.replay26").exists()
    assert (cfg.replay_dir / f"{ids[-1]}.replay26").exists()


def test_an_unlimited_replay_budget_never_auto_prunes(project: Project) -> None:
    cfg = dataclasses.replace(project.cfg, replay_budget_mb=None)
    league = League(cfg, project.store, project.bus, project.rater)
    league.sync()
    replay = cfg.tmp_dir / "retained.replay26"
    replay.write_bytes(b"R" * 2_000_000)
    game = league.finish(Job("alpha", "beta", "sprint", 1), outcome(replay_path=replay))

    assert league.enforce_replay_budget() == 0
    assert (cfg.replay_dir / game.replay).is_file()


def test_the_budget_sweep_forgets_a_replay_that_vanished(project: Project) -> None:
    project.league.sync()
    replay, _log = _temp_files(project)
    game = project.league.finish(Job("alpha", "beta", "sprint", 1), outcome(replay_path=replay))
    (project.cfg.replay_dir / game.replay).unlink()

    project.league.enforce_replay_budget()

    stored = project.store.get_game(game.id)
    assert stored is not None and stored.replay == ""


# --------------------------------------------------------------------------- #
# end to end through the fake runner
# --------------------------------------------------------------------------- #


def test_a_full_match_leaves_a_consistent_ladder(project: Project) -> None:
    project.league.sync()
    jobs = project.league.plan_match("alpha", "beta", repeat=2)
    run(project.league, jobs)

    alpha = project.store.get_bot("alpha")
    beta = project.store.get_bot("beta")
    assert alpha is not None and beta is not None
    # The fake always lets the alphabetically smaller name win, whichever slot
    # it plays, so alpha must end up ahead of beta.
    assert alpha.rating.score > beta.rating.score
    record = project.store.record("alpha")
    assert record.wins == len(jobs) and record.losses == 0


def test_a_broken_bot_takes_losses_for_already_planned_games(project: Project) -> None:
    project.league.sync()
    project.runner.status_for["beta"] = "loadfail"
    jobs = project.league.plan_match("alpha", "beta", maps=["sprint"], mirror=True)
    run(project.league, jobs)

    beta = project.store.get_bot("beta")
    alpha = project.store.get_bot("alpha")
    assert beta is not None and beta.broken is True
    assert alpha is not None and alpha.rating.score > beta.rating.score
    games = project.store.list_games()
    assert all(game.rated for game in games)
    assert all(game.a_errors + game.b_errors == 1 for game in games)
    assert all(
        (game.winner == "a" and game.b == "beta")
        or (game.winner == "b" and game.a == "beta")
        for game in games
    )


def test_recompute_reproduces_a_played_match(project: Project) -> None:
    project.league.sync()
    run(project.league, project.league.plan_match("alpha", "beta", repeat=2))
    before = {b.name: (b.mu, b.sigma) for b in project.store.bots()}

    project.store.recompute(project.rater)

    after = {b.name: (b.mu, b.sigma) for b in project.store.bots()}
    for name, (mu, sigma) in before.items():
        assert after[name][0] == pytest.approx(mu)
        assert after[name][1] == pytest.approx(sigma)


def test_a_runner_that_raises_becomes_an_engine_error(project: Project) -> None:
    project.league.sync()

    def boom(_spec: GameSpec) -> GameOutcome:
        raise RuntimeError("pool exploded")

    project.runner.hook = boom
    run(project.league, project.league.plan_match("alpha", "beta", maps=["sprint"], mirror=False))

    games = project.store.list_games()
    assert len(games) == 1
    assert games[0].status == "engine_error"
    assert "pool exploded" in games[0].error


def test_a_job_naming_a_missing_bot_is_skipped_not_fatal(project: Project) -> None:
    project.league.sync()
    run(project.league, [Job("alpha", "ghost", "sprint", 1)])

    assert project.store.game_count() == 0
    errors = [e for e in project.types("log") if e["level"] == "error"]
    assert errors and "ghost" in errors[-1]["msg"]


@pytest.mark.parametrize("limit", [1, 3, 5, 7])
def test_an_odd_game_limit_is_respected_exactly(project: Project, limit: int) -> None:
    project.league.sync()
    project.league.start_arena("ladder", limit=limit)
    assert project.league.wait(timeout=30.0)

    assert project.store.game_count() == limit
