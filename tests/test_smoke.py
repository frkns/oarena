"""One real fcode game, end to end.

Deselected by default (``addopts = "-m 'not slow'"`` in ``pyproject.toml``)
because a real game costs several seconds.  Run it deliberately::

    PYTHONPATH=src python -m pytest tests/test_smoke.py -m slow

It is the only test in the suite that touches the engine, and it exists to catch
what a fake never can: that ``python -m oarena._worker`` still resolves, that
``run_game``'s signature has not moved, and that a real replay lands in the
store under its game id.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest

from conftest import STOCK_MAPS, make_project
from oarena import maps as mapsmod
from oarena.config import Config
from oarena.events import EventBus
from oarena.league import League
from oarena.ratings import Rater
from oarena.runner import GameSpec, run_one
from oarena.store import Store

pytestmark = pytest.mark.slow


@dataclass
class RealProject:
    cfg: Config
    store: Store
    league: League


def _starter_source() -> Path | None:
    """The starter bot shipped with the installed fcode package, if present."""
    try:
        import fcode
    except Exception:  # noqa: BLE001 - the caller skips
        return None
    candidate = Path(fcode.__file__).resolve().parent / "data" / "starter_bot.py"
    return candidate if candidate.is_file() else None


@pytest.fixture
def real_project(tmp_path: Path) -> Iterator[RealProject]:
    pytest.importorskip("fcode", reason="the smoke test needs the real engine")
    starter = _starter_source()
    if starter is None or STOCK_MAPS is None:
        pytest.skip("no starter bot or stock maps available")

    cfg = make_project(tmp_path / "smoke", bots=(), map_names=("sprint",))
    for name in ("one", "two"):
        directory = cfg.bots_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(starter, directory / "main.py")

    store = Store(cfg.db_path)
    league = League(cfg, store, EventBus(), Rater(cfg.trueskill))
    league.sync()
    try:
        yield RealProject(cfg=cfg, store=store, league=league)
    finally:
        league.stop()
        league.wait(timeout=180.0)
        store.close()


def test_one_real_game_lands_a_replay_in_the_store(real_project: RealProject) -> None:
    cfg, store, league = real_project.cfg, real_project.store, real_project.league
    jobs = league.plan_match("one", "two", maps=["sprint"], mirror=False)
    assert len(jobs) == 1

    league.start_match(jobs)
    assert league.wait(timeout=180.0), "the real game never finished"

    games = store.list_games(limit=5)
    assert len(games) == 1
    game = games[0]

    assert game.status == "ok", f"{game.status}: {game.error}"
    assert game.winner in ("a", "b", "draw")
    assert game.turns > 0
    assert game.duration_ms > 0
    assert game.win_condition
    assert game.replay == f"{game.id}.replay26"

    replay = cfg.replay_dir / game.replay
    assert replay.is_file()
    assert replay.stat().st_size > 10_000, "a real replay is hundreds of kilobytes"
    assert list(cfg.tmp_dir.glob("*")) == [], "scratch files were left behind"


def test_run_one_against_the_real_engine(real_project: RealProject) -> None:
    cfg, league = real_project.cfg, real_project.league
    spec = GameSpec(
        a=league.resolve("one"),
        b=league.resolve("two"),
        map=mapsmod.resolve(cfg.maps_dir, "sprint"),
        seed=7,
        tle_ms=cfg.tle_ms,
        timeout_s=180.0,
        cwd=cfg.root,
        tmp_dir=cfg.tmp_dir,
    )

    outcome = run_one(spec)
    try:
        assert outcome.status == "ok", f"{outcome.status}: {outcome.error}"
        assert outcome.winner in ("a", "b", "draw")
        assert outcome.turns > 0
        assert outcome.replay_path is not None and outcome.replay_path.is_file()
        assert outcome.a.buildings + outcome.b.buildings > 0
    finally:
        for path in (outcome.replay_path, outcome.log_path):
            if path is not None:
                path.unlink(missing_ok=True)
