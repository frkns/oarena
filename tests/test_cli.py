"""`oarena.cli`: help for every command, JSON shapes, and the error mapping.

Commands are driven through :class:`click.testing.CliRunner` inside a real
throwaway project, with the in-process fake runner standing in for the engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner, Result

from conftest import HAVE_FCODE, Project, copy_maps, make_project, write_bot
from oarena import cli as climod
from oarena import config as configmod
from oarena.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def invoke(runner: CliRunner, args: list[str], **kwargs: Any) -> Result:
    return runner.invoke(main, args, catch_exceptions=False, **kwargs)


def payload(result: Result) -> Any:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.fixture
def cwd(project: Project, monkeypatch: pytest.MonkeyPatch) -> Project:
    """Run the CLI inside the throwaway project.

    The CLI opens its own :class:`~oarena.store.Store` on the same file, so
    assertions about persisted state go through :func:`fresh_store` rather than
    the fixture's (possibly stale) connection.
    """
    monkeypatch.chdir(project.root)
    return project


def fresh_store(project: Project):
    """A new connection to the project's database, seeing what the CLI wrote."""
    from oarena.store import Store

    return Store(project.cfg.db_path)


def interrupt_stop_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record graceful/forced CLI stops while keeping a failing test prompt.

    On the old graceful-stop path, delegate to the real force stop so an
    interrupt regression fails its assertions instead of draining a fake game
    for the configured engine timeout.
    """
    from oarena.league import League

    calls: list[str] = []
    real_force_stop = League.force_stop

    def force_stop(league: League) -> int:
        calls.append("force")
        return real_force_stop(league)

    def graceful_stop(league: League) -> None:
        calls.append("graceful")
        real_force_stop(league)

    monkeypatch.setattr(League, "force_stop", force_stop)
    monkeypatch.setattr(League, "stop", graceful_stop)
    return calls


# --------------------------------------------------------------------------- #
# help
# --------------------------------------------------------------------------- #


def _command_paths(command: click.Command, prefix: tuple[str, ...] = ()) -> list[list[str]]:
    here = [*prefix, command.name] if command.name != "main" else list(prefix)
    paths = [here]
    if isinstance(command, click.Group):
        for name in command.list_commands(None):  # type: ignore[arg-type]
            sub = command.get_command(None, name)  # type: ignore[arg-type]
            if sub is not None:
                paths.extend(_command_paths(sub, tuple(here)))
    return paths


ALL_COMMANDS = _command_paths(main)


def test_every_command_is_reachable() -> None:
    names = {" ".join(path) for path in ALL_COMMANDS}
    assert {
        "", "init", "ladder", "refresh", "match", "arena", "vs", "bots", "bot", "bot info",
        "bot hash", "bot enable", "bot disable", "bot rm", "bot note",
        "maps", "batch", "games", "game", "log", "watch", "matrix", "serve",
        "recompute", "reset", "gc", "bench", "doctor",
    } <= names


@pytest.mark.parametrize("path", ALL_COMMANDS, ids=lambda p: " ".join(p) or "root")
def test_help_works_for_every_command(runner: CliRunner, path: list[str]) -> None:
    result = invoke(runner, [*path, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


def test_version_option(runner: CliRunner) -> None:
    from oarena import __version__

    result = invoke(runner, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_aliases_resolve_to_the_ladder(runner: CliRunner, cwd: Project) -> None:
    for alias in ("show", "ls"):
        result = invoke(runner, [alias, "--json"])
        assert result.exit_code == 0, result.output
        assert isinstance(json.loads(result.output), list)


def test_unambiguous_root_command_prefix_resolves(runner: CliRunner) -> None:
    result = invoke(runner, ["s", "--help"])
    assert result.exit_code == 0, result.output
    assert "Run the web dashboard." in result.output


def test_ambiguous_root_command_prefix_explains_the_choices(runner: CliRunner) -> None:
    result = invoke(runner, ["b", "--help"])
    assert result.exit_code == 2
    assert "ambiguous command 'b'" in result.output
    assert "bench" in result.output and "bot" in result.output and "bots" in result.output


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #


def test_init_writes_a_loadable_config(runner: CliRunner, tmp_path: Path,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "fresh"
    root.mkdir()
    write_bot(root / "bots", "alpha")
    copy_maps(root / "maps", ("sprint",))
    monkeypatch.chdir(root)

    result = invoke(runner, ["init"])

    assert result.exit_code == 0, result.output
    cfg = configmod.from_file(root / "oarena.toml")
    assert cfg.bots_dir == root.resolve() / "bots"
    assert cfg.state_dir.is_dir()
    assert (cfg.state_dir / ".gitignore").read_text() == "*\n"
    assert cfg.db_path.is_file()


def test_init_inherits_the_fcode_directories(runner: CliRunner, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "fcodeproj"
    root.mkdir()
    (root / "fcode.toml").write_text('bots_dir = "agents"\nmaps_dir = "arenas"\n', encoding="utf-8")
    monkeypatch.chdir(root)

    result = invoke(runner, ["init"])

    assert result.exit_code == 0, result.output
    cfg = configmod.from_file(root / "oarena.toml")
    assert cfg.bots_dir == root.resolve() / "agents"
    assert cfg.maps_dir == root.resolve() / "arenas"


def test_init_refuses_to_overwrite_without_force(runner: CliRunner, tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "again"
    root.mkdir()
    (root / "oarena.toml").write_text('bots_dir = "keepme"\n', encoding="utf-8")
    monkeypatch.chdir(root)

    result = invoke(runner, ["init"])

    assert result.exit_code == 0
    assert "already exists" in result.output
    assert configmod.from_file(root / "oarena.toml").bots_dir.name == "keepme"

    assert invoke(runner, ["init", "--force"]).exit_code == 0
    assert configmod.from_file(root / "oarena.toml").bots_dir.name == "bots"


# --------------------------------------------------------------------------- #
# JSON listings
# --------------------------------------------------------------------------- #


def test_ladder_json_shape(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["refresh"])
    rows = payload(invoke(runner, ["ladder", "--json"]))

    assert [r["name"] for r in rows] == ["alpha", "beta", "gamma"]
    assert set(rows[0]) >= {
        "rank", "name", "score", "lcb95", "mu", "sigma", "games", "winrate",
        "source_updated", "source_version_id",
    }
    assert rows[0]["lcb95"] == pytest.approx(rows[0]["score"])


def test_ladder_ranks_by_mu_when_lcb95_disagrees(
    runner: CliRunner, cwd: Project,
) -> None:
    from oarena.ratings import Rating

    invoke(runner, ["refresh"])
    with fresh_store(cwd) as store:
        # alpha has the largest mean but, because it is uncertain, by far the
        # smallest legacy conservative score.  The public order must follow μ.
        store.set_rating("alpha", Rating(mu=30.0, sigma=10.0))
        store.set_rating("beta", Rating(mu=29.0, sigma=1.0))
        store.set_rating("gamma", Rating(mu=28.0, sigma=1.0))

    rows = payload(invoke(runner, ["ladder", "--json"]))

    assert [row["name"] for row in rows] == ["alpha", "beta", "gamma"]
    assert rows[0]["score"] < rows[1]["score"]
    assert all(row["lcb95"] == pytest.approx(row["score"]) for row in rows)


def test_ladder_limit_is_applied_after_mu_ordering(
    runner: CliRunner, cwd: Project,
) -> None:
    from oarena.ratings import Rating

    for index in range(12):
        cwd.add_bot(f"extra_{index:02d}")
    invoke(runner, ["refresh"])

    with fresh_store(cwd) as store:
        names = [bot.name for bot in store.bots()]
        for index, name in enumerate(names):
            store.set_rating(name, Rating(mu=float(index), sigma=1.0))
        expected = list(reversed(names))[:10]

    rows = payload(invoke(runner, ["ls", "--top", "10", "--json"]))

    assert [row["name"] for row in rows] == expected
    assert [row["rank"] for row in rows] == list(range(1, 11))


def test_ladder_top_requires_a_positive_limit(runner: CliRunner) -> None:
    result = invoke(runner, ["ls", "--top", "0"])

    assert result.exit_code == 2
    assert "not in the range x>=1" in result.output


def test_ladder_prints_a_table(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["refresh"])
    result = invoke(runner, ["ladder"])
    assert result.exit_code == 0
    assert "MU" in result.output and "LCB95" in result.output and "RATED" in result.output
    assert "alpha" in result.output


def test_ladder_of_an_empty_project(runner: CliRunner, tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "bare"
    make_project(root, bots=(), map_names=())
    monkeypatch.chdir(root)

    result = invoke(runner, ["ladder"])

    assert result.exit_code == 0
    assert "no bots" in result.output


def test_bots_json_shape(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["refresh"])
    rows = payload(invoke(runner, ["bots", "--json"]))
    assert {r["name"] for r in rows} == {"alpha", "beta", "gamma"}
    assert set(rows[0]) >= {"name", "dir", "entry", "active", "broken", "src_hash"}


def test_maps_json_shape(runner: CliRunner, cwd: Project) -> None:
    rows = payload(invoke(runner, ["maps", "--json"]))
    assert {r["name"] for r in rows} == {"sprint", "duel", "pinch"}
    assert all({"width", "height", "tiles", "games"} <= set(r) for r in rows)


def test_games_json_is_empty_before_anything_is_played(runner: CliRunner, cwd: Project) -> None:
    assert payload(invoke(runner, ["games", "--json"])) == []


def test_maps_table(runner: CliRunner, cwd: Project) -> None:
    result = invoke(runner, ["maps"])
    assert result.exit_code == 0
    assert "sprint" in result.output and "ORE" in result.output


# --------------------------------------------------------------------------- #
# playing
# --------------------------------------------------------------------------- #


def test_session_close_force_stops_and_reaps_before_closing_the_store() -> None:
    events: list[object] = []

    class ActiveLeague:
        running = True
        waits = 0

        def force_stop(self) -> int:
            events.append("force")
            return 1

        def wait(self, timeout: float | None = None) -> bool:
            events.append(("wait", timeout))
            self.waits += 1
            if self.waits == 1:
                raise KeyboardInterrupt
            return self.waits >= 3

    class RecordingStore:
        def close(self) -> None:
            events.append("close")

    session = climod.Session(
        cfg=None,  # type: ignore[arg-type]
        store=RecordingStore(),  # type: ignore[arg-type]
        bus=None,  # type: ignore[arg-type]
        rater=None,  # type: ignore[arg-type]
        league=ActiveLeague(),  # type: ignore[arg-type]
    )

    session.close()

    assert events == [
        "force",
        ("wait", 0.25),
        "force",
        ("wait", 0.25),
        ("wait", 0.25),
        "close",
    ]


def test_import_db_updates_the_project_ladder_and_resumes(
    runner: CliRunner, cwd: Project, tmp_path: Path
) -> None:
    from oarena import bots as botsmod
    from oarena.store import Game, Store

    cwd.league.sync()
    source_path = tmp_path / "calibration" / ".oarena" / "oarena.db"
    source = Store(source_path)
    try:
        for bot_source in botsmod.discover(cwd.cfg.bots_dir):
            source.upsert_bot(bot_source, cwd.rater.initial())
        source.add_game(
            Game(
                a="alpha", b="beta", map="fresh-01", seed=41, rated=True,
                status="ok", winner="a", tag="rated-calibration",
            )
        )

        first = payload(
            invoke(
                runner,
                [
                    "import-db", str(source_path), "--source-key", "rated-v1",
                    "--through", "1", "--json",
                ],
            )
        )
        assert (first["selected"], first["imported"], first["skipped"]) == (1, 1, 0)
        second = payload(
            invoke(
                runner,
                [
                    "import-db", str(source_path), "--source-key", "rated-v1",
                    "--through", "1", "--json",
                ],
            )
        )
        assert (second["selected"], second["imported"], second["skipped"]) == (1, 0, 1)

        with fresh_store(cwd) as destination:
            assert destination.game_count() == 1
            assert destination.get_bot("alpha").rating != cwd.rater.initial()  # type: ignore[union-attr]
    finally:
        source.close()


def test_match_plays_and_summarises(runner: CliRunner, cwd: Project) -> None:
    result = invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])

    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    store = fresh_store(cwd)
    try:
        assert store.game_count() == 2  # mirrored
        assert store.get_bot("alpha").rating.score > store.get_bot("beta").rating.score  # type: ignore[union-attr]
    finally:
        store.close()


def test_match_ctrl_c_aborts_in_flight_games_immediately(
    runner: CliRunner,
    cwd: Project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd.runner.delay = 0.2
    stop_calls = interrupt_stop_spy(monkeypatch)

    def interrupt_progress(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(climod, "_match_progress", interrupt_progress)

    result = invoke(
        runner, ["match", "alpha", "beta", "-m", "sprint", "-w", "1"]
    )

    assert result.exit_code == 130
    assert "force" in stop_calls
    assert "graceful" not in stop_calls
    assert "aborting" in result.output.lower()
    assert "letting in-flight games finish" not in result.output


def test_match_ctrl_c_before_run_thread_exists_does_not_hang(
    runner: CliRunner,
    cwd: Project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from oarena.league import League

    monkeypatch.setattr(
        League,
        "_launch",
        lambda _league: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    result = invoke(
        runner, ["match", "alpha", "beta", "-m", "sprint", "-w", "1"]
    )

    assert result.exit_code == 130
    assert "aborting" in result.output.lower()
    with fresh_store(cwd) as store:
        assert store.game_count() == 0


def test_match_tag_is_a_queryable_immutable_batch(
    runner: CliRunner, cwd: Project
) -> None:
    tag = "codex_cli_gate_v1"
    first = invoke(
        runner,
        ["match", "alpha", "beta", "-m", "sprint", "--tag", tag, "-q"],
    )
    assert first.exit_code == 0, first.output

    games = payload(invoke(runner, ["games", "--tag", tag, "--json"]))
    assert len(games) == 2
    assert sorted(game["batch_ordinal"] for game in games) == [0, 1]
    assert all(game["a_src_hash"] and game["b_src_hash"] for game in games)
    batch = payload(invoke(runner, ["batch", tag, "--json"]))
    assert (
        batch["mode"],
        batch["status"],
        batch["requested_games"],
        batch["played_games"],
        batch["stored_games"],
    ) == ("match", "completed", 2, 2, 2)

    with fresh_store(cwd) as store:
        alpha_before = store.get_bot("alpha")
        assert alpha_before is not None
    entry = cwd.cfg.bots_dir / "alpha" / "main.py"
    entry.write_text(entry.read_text(encoding="utf-8") + "# after batch\n", encoding="utf-8")
    reused = runner.invoke(
        main,
        ["match", "alpha", "beta", "-m", "sprint", "--tag", tag, "-q"],
    )
    assert reused.exit_code == 2
    assert "already reserved" in reused.output
    with fresh_store(cwd) as store:
        assert store.game_count(tag=tag) == 2
        alpha_after = store.get_bot("alpha")
        assert alpha_after is not None
        assert alpha_after.src_hash == alpha_before.src_hash
        assert alpha_after.rating == alpha_before.rating


def test_match_unrated_leaves_the_ladder_alone(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["refresh"])
    before = {row["name"]: row for row in payload(invoke(runner, ["ladder", "--json"]))}
    result = invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "--unrated", "-q"])
    after = {row["name"]: row for row in payload(invoke(runner, ["ladder", "--json"]))}

    assert result.exit_code == 0, result.output
    ladder_fields = ("score", "mu", "sigma", "games", "wins", "losses", "draws", "winrate")
    for name in ("alpha", "beta"):
        assert {key: after[name][key] for key in ladder_fields} == {
            key: before[name][key] for key in ladder_fields
        }
    store = fresh_store(cwd)
    try:
        assert store.game_count() == 2
        assert all(not g.rated for g in store.list_games())
    finally:
        store.close()


def test_ladder_is_read_only_until_an_explicit_refresh(
    runner: CliRunner, cwd: Project
) -> None:
    invoke(runner, ["refresh"])
    cwd.store.set_rating("alpha", cwd.rater.initial().__class__(31.0, 1.0))
    before = cwd.store.get_bot("alpha")
    assert before is not None
    cwd.add_bot("alpha", "# edited but not refreshed\n")

    result = invoke(runner, ["ladder", "--json"])
    assert result.exit_code == 0
    with fresh_store(cwd) as store:
        unchanged = store.get_bot("alpha")
        assert unchanged is not None
        assert unchanged.src_hash == before.src_hash
        assert unchanged.rating == before.rating

    invoke(runner, ["refresh"])
    with fresh_store(cwd) as store:
        changed = store.get_bot("alpha")
        assert changed is not None
        assert changed.src_hash != before.src_hash
        assert changed.sigma > before.sigma


def test_match_with_an_unknown_bot_exits_two(runner: CliRunner, cwd: Project) -> None:
    result = runner.invoke(main, ["match", "alpha", "ghost", "-m", "sprint"])
    assert result.exit_code == 2


def test_arena_stops_after_n_games(runner: CliRunner, cwd: Project) -> None:
    result = invoke(runner, ["arena", "-n", "4", "-w", "2"])

    assert result.exit_code == 0, result.output
    assert "top 10 · opening" in result.output
    assert "top 10 · final · 4 games" in result.output
    assert "results" in result.output
    assert "4 decisive" in result.output
    store = fresh_store(cwd)
    try:
        assert store.game_count() == 4
    finally:
        store.close()


def test_arena_live_loop_does_not_rebuild_the_ladder(
    runner: CliRunner,
    cwd: Project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_ladder_view = climod._ladder_view
    calls: list[tuple[int | None, str | None]] = []

    def ladder_view(
        store: Any,
        *,
        limit: int | None = None,
        title: str | None = None,
    ) -> Any:
        calls.append((limit, title))
        return real_ladder_view(store, limit=limit, title=title)

    monkeypatch.setattr(climod, "_ladder_view", ladder_view)

    result = invoke(runner, ["arena", "-n", "8", "-w", "2"])

    assert result.exit_code == 0, result.output
    assert calls == [
        (10, "top 10 · opening"),
        (10, "top 10 · final · 8 games"),
    ]


def test_arena_stats_and_snapshot_cadence() -> None:
    from oarena.store import Game

    stats = climod._ArenaStats()
    stats.add(
        [
            Game(status="ok", winner="a", rated=True, turns=100, duration_ms=1_000),
            Game(
                status="ok",
                winner="draw",
                rated=False,
                turns=200,
                duration_ms=3_000,
                a_errors=2,
            ),
            Game(status="timeout", winner=None, rated=False, duration_ms=9_000),
        ]
    )

    assert stats.games == 3
    assert stats.rated == 1
    assert stats.ok == 1
    assert stats.decisive == 1
    assert stats.draws == 0
    assert stats.failed == 2
    assert stats.bot_errors == 2
    assert stats.average_turns == pytest.approx(100.0)
    assert stats.average_duration_ms == 1_000
    assert "2 failed" in climod._arena_results_line(stats).plain
    average = climod._arena_average_line(stats)
    assert average is not None
    assert "100 turns" in average.plain and "1.0s/game" in average.plain

    assert not climod._arena_snapshot_due(
        now=59.9, last_at=0.0, games=20, last_games=10, interval=60.0
    )
    assert not climod._arena_snapshot_due(
        now=60.0, last_at=0.0, games=10, last_games=10, interval=60.0
    )
    assert climod._arena_snapshot_due(
        now=60.0, last_at=0.0, games=11, last_games=10, interval=60.0
    )


def test_crash_table_attributes_dual_load_failure_to_each_unique_bot(
    project: Project,
) -> None:
    from oarena.store import Game

    table = climod._crash_table(
        project.cfg,
        [
            Game(
                id=71,
                a="alpha",
                b="beta",
                status="loadfail_both",
                error="A: SyntaxError; B: SyntaxError",
            ),
            Game(
                id=72,
                a="syntax",
                b="syntax",
                status="loadfail_both",
                error="A: SyntaxError; B: SyntaxError",
            ),
        ],
    )

    assert table is not None
    assert [cell.plain for cell in table.columns[0].cells] == ["alpha", "beta", "syntax"]
    assert [str(cell) for cell in table.columns[1].cells] == ["load failure"] * 3
    assert [str(cell) for cell in table.columns[2].cells] == ["1"] * 3


def test_arena_drain_paginates_without_losing_a_large_burst() -> None:
    from oarena.store import Game

    games = [
        Game(id=gid, status="ok", winner="a", tag="arena-run")
        for gid in range(1, 1_206)
    ]

    class BurstyStore:
        def list_games_after(
            self,
            after_id: int,
            *,
            limit: int,
            tag: str | None = None,
        ) -> list[Game]:
            return [
                game
                for game in games
                if game.id > after_id and (not tag or game.tag == tag)
            ][:limit]

    fresh, cursor = climod._drain(
        BurstyStore(), 0, tag="arena-run"  # type: ignore[arg-type]
    )

    assert [game.id for game in fresh] == list(range(1, 1_206))
    assert cursor == 1_205


def test_arena_ctrl_c_aborts_in_flight_games_immediately(
    runner: CliRunner,
    cwd: Project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd.runner.delay = 0.2
    stop_calls = interrupt_stop_spy(monkeypatch)

    class InterruptingLive:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> InterruptingLive:
            return self

        def __exit__(self, *_exc_info: object) -> bool:
            return False

        def update(self, *_args: object, **_kwargs: object) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(climod, "Live", InterruptingLive)

    result = invoke(runner, ["arena", "-w", "1"])

    assert result.exit_code == 130
    assert "force" in stop_calls
    assert "graceful" not in stop_calls
    assert "aborting" in result.output.lower()
    assert "letting in-flight games finish" not in result.output


def test_arena_rejects_mutually_exclusive_matchmakers(runner: CliRunner, cwd: Project) -> None:
    result = runner.invoke(main, ["arena", "--rr", "--top", "2"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_games_and_game_and_log_after_a_match(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])

    rows = payload(invoke(runner, ["games", "--json"]))
    assert len(rows) == 2
    assert set(rows[0]) >= {"id", "a", "b", "map", "winner", "status", "turns", "ts"}

    gid = rows[0]["id"]
    detail = payload(invoke(runner, ["game", str(gid), "--json"]))
    assert detail["id"] == gid

    result = invoke(runner, ["game", str(gid)])
    assert result.exit_code == 0 and f"game #{gid}" in result.output

    result = invoke(runner, ["log", str(gid)])
    assert result.exit_code == 0


def test_game_of_an_unknown_id_fails(runner: CliRunner, cwd: Project) -> None:
    result = runner.invoke(main, ["game", "999"])
    assert result.exit_code != 0
    assert "no game #999" in result.output


def test_matrix_after_a_match(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])
    result = invoke(runner, ["matrix"])

    assert result.exit_code == 0
    assert "alpha" in result.output


def test_recompute_reports_the_rebuild(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])
    result = invoke(runner, ["recompute"])

    assert result.exit_code == 0
    assert "rebuilt" in result.output


# --------------------------------------------------------------------------- #
# bot management
# --------------------------------------------------------------------------- #


def test_bot_info(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])
    result = invoke(runner, ["bot", "info", "alpha"])

    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "record" in result.output


def test_bot_info_json(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["refresh"])
    detail = payload(invoke(runner, ["bot", "info", "alpha", "--json"]))
    assert set(detail) == {"bot", "record", "h2h", "maps", "history", "versions", "crashes"}


def test_bot_hash_checks_and_records_source_changes(runner: CliRunner, cwd: Project) -> None:
    first = payload(invoke(runner, ["bot", "hash", "alpha", "--json"]))
    assert first["name"] == "alpha"
    assert first["changed"] is False
    assert first["versions"] == 1

    entry = cwd.cfg.bots_dir / "alpha" / "main.py"
    entry.write_text(entry.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    changed = payload(invoke(runner, ["bot", "hash", "alpha", "--json"]))
    assert changed["changed"] is True
    assert changed["versions"] == 2
    assert changed["hash"] != first["hash"]


def test_bot_enable_disable(runner: CliRunner, cwd: Project) -> None:
    assert invoke(runner, ["bot", "disable", "gamma"]).exit_code == 0
    rows = payload(invoke(runner, ["bots", "--json"]))
    assert next(r for r in rows if r["name"] == "gamma")["active"] is False

    assert invoke(runner, ["bot", "enable", "gamma"]).exit_code == 0
    rows = payload(invoke(runner, ["bots", "--json"]))
    assert next(r for r in rows if r["name"] == "gamma")["active"] is True


def test_bot_note(runner: CliRunner, cwd: Project) -> None:
    assert invoke(runner, ["bot", "note", "alpha", "the", "incumbent"]).exit_code == 0
    rows = payload(invoke(runner, ["bots", "--json"]))
    assert next(r for r in rows if r["name"] == "alpha")["note"] == "the incumbent"


def test_bot_rm_deletes_the_row_and_warns_about_re_registration(
    runner: CliRunner, cwd: Project
) -> None:
    result = invoke(runner, ["bot", "rm", "gamma", "--yes"])

    assert result.exit_code == 0
    assert "deleted gamma" in result.output
    store = fresh_store(cwd)
    try:
        assert store.get_bot("gamma") is None
    finally:
        store.close()
    # The directory is still on disk, so an explicit refresh re-registers it;
    # `bot disable` is the way to keep a bot out of the ladder for good.
    assert "re-registered" in result.output
    invoke(runner, ["refresh"])
    assert {r["name"] for r in payload(invoke(runner, ["bots", "--json"]))} == {
        "alpha", "beta", "gamma"
    }


def test_unknown_bot_commands_exit_two(runner: CliRunner, cwd: Project) -> None:
    for args in (["bot", "note", "ghost", "x"], ["bot", "enable", "ghost"],
                 ["bot", "rm", "ghost", "--yes"]):
        assert runner.invoke(main, args).exit_code == 2, args


# --------------------------------------------------------------------------- #
# maintenance
# --------------------------------------------------------------------------- #


def test_reset_clears_history(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])
    result = invoke(runner, ["reset", "--yes"])

    assert result.exit_code == 0
    assert payload(invoke(runner, ["games", "--json"])) == []
    rows = payload(invoke(runner, ["ladder", "--json"]))
    assert all(r["games"] == 0 for r in rows)


def test_reset_clean_removes_all_arena_state_but_not_sources(runner: CliRunner, cwd: Project) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])
    (cwd.cfg.tmp_dir / "scratch").write_text("temporary", encoding="utf-8")

    result = invoke(runner, ["reset", "--clean", "--yes"])

    assert result.exit_code == 0, result.output
    assert cwd.cfg.state_dir.is_dir()
    assert {p.name for p in cwd.cfg.state_dir.iterdir()} <= {"writer.lock"}
    assert (cwd.cfg.bots_dir / "alpha" / "main.py").is_file()
    # Explicit refresh recreates the DB catalog from the project bots directory.
    invoke(runner, ["refresh"])
    rows = payload(invoke(runner, ["bots", "--json"]))
    assert {row["name"] for row in rows} == {"alpha", "beta", "gamma"}


def test_external_shared_config_cannot_destroy_the_owning_state(
    runner: CliRunner, cwd: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoke(runner, ["match", "alpha", "beta", "-m", "sprint", "-q"])
    gate = cwd.root / "gate"
    gate.mkdir()
    gate_bots = gate / "bots"
    write_bot(gate_bots, "alpha", "def main():\n    return 'borrower edit'\n")
    (gate / "oarena.toml").write_text(
        f'state_dir = "{cwd.cfg.state_dir}"\n'
        f'bots_dir = "{gate_bots}"\n'
        f'maps_dir = "{cwd.cfg.maps_dir}"\n',
        encoding="utf-8",
    )
    with fresh_store(cwd) as store:
        before = {
            bot.name: (bot.active, bot.dir, bot.entry, bot.src_hash, bot.mu, bot.sigma)
            for bot in store.bots()
        }
    monkeypatch.chdir(gate)

    reset_result = runner.invoke(main, ["reset", "--clean", "--yes"])
    delete_result = runner.invoke(main, ["bot", "rm", "alpha", "--yes"])

    assert reset_result.exit_code == 2
    assert "external shared state" in reset_result.output
    assert delete_result.exit_code == 2
    assert "external shared state" in delete_result.output
    with fresh_store(cwd) as store:
        assert store.game_count() == 2
        assert store.get_bot("alpha") is not None
        after = {
            bot.name: (bot.active, bot.dir, bot.entry, bot.src_hash, bot.mu, bot.sigma)
            for bot in store.bots()
        }
        assert after == before


def test_gc_reports_nothing_to_collect(runner: CliRunner, cwd: Project) -> None:
    result = invoke(runner, ["gc", "--yes"])
    assert result.exit_code == 0
    assert "nothing to collect" in result.output


def test_gc_removes_orphans(runner: CliRunner, cwd: Project) -> None:
    (cwd.cfg.replay_dir / "999.replay26").write_bytes(b"orphan")
    result = invoke(runner, ["gc", "--yes"])

    assert result.exit_code == 0
    assert not (cwd.cfg.replay_dir / "999.replay26").exists()


def test_bench_ctrl_c_force_stops_its_pool(
    runner: CliRunner,
    cwd: Project,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class InterruptingFuture:
        def result(self) -> None:
            raise KeyboardInterrupt

    class RecordingPool:
        def __init__(self, workers: int) -> None:
            events.append(("pool", workers))

        def submit(self, _spec: object) -> InterruptingFuture:
            return InterruptingFuture()

        def force_stop(self) -> int:
            events.append("force")
            return 1

        def shutdown(self, *, wait: bool = True) -> None:
            events.append(("shutdown", wait))

    monkeypatch.setattr(climod, "Pool", RecordingPool)

    result = invoke(runner, ["bench", "-w", "1", "-n", "2"])

    assert result.exit_code == 130
    assert "force" in events
    assert ("shutdown", True) not in events
    assert "aborting" in result.output.lower()
    assert "letting in-flight games finish" not in result.output


def test_watch_without_games_fails_cleanly(runner: CliRunner, cwd: Project) -> None:
    result = runner.invoke(main, ["watch"])
    assert result.exit_code != 0
    assert "no games to watch" in result.output


# --------------------------------------------------------------------------- #
# doctor and the error mapping
# --------------------------------------------------------------------------- #


def test_doctor_passes_in_a_healthy_project(runner: CliRunner, cwd: Project) -> None:
    if not HAVE_FCODE:
        pytest.skip("doctor cannot pass without fcode")
    result = runner.invoke(main, ["doctor"])

    for check in ("oarena.toml found", "fcode importable", "maps present",
                  "bots present", "database writable"):
        assert check in result.output
    assert result.exit_code == 0, result.output
    assert "all good" in result.output


def test_doctor_fails_outside_a_project(runner: CliRunner, tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    monkeypatch.chdir(lonely)

    result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 1
    assert "oarena init" in result.output


def test_commands_outside_a_project_exit_two(runner: CliRunner, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    lonely = tmp_path / "nowhere"
    lonely.mkdir()
    monkeypatch.chdir(lonely)

    result = runner.invoke(main, ["ladder"])

    assert result.exit_code == 2
    assert "oarena init" in result.output


def test_a_match_without_maps_exits_two(runner: CliRunner, tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch,
                                        fake_runner: Any) -> None:
    root = tmp_path / "nomaps"
    make_project(root, bots=("alpha", "beta"), map_names=())
    monkeypatch.chdir(root)

    result = runner.invoke(main, ["match", "alpha", "beta"])

    assert result.exit_code == 2
    assert "no maps" in result.output
