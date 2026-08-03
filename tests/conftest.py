"""Shared fixtures.

The expensive thing in oarena is the fcode engine, so the whole unit suite runs
against :mod:`tests.fake_worker`:

* :func:`fake_runner` swaps :func:`oarena.runner.run_one` (and the copy the pool
  holds) for an in-process fake, which is what makes the league, server and CLI
  tests finish in milliseconds;
* :func:`worker_script` instead rewrites the supervisor's argv so the *real*
  ``run_one`` spawns ``tests/fake_worker.py`` — used only by ``test_runner.py``,
  where the subprocess supervision is the thing under test.

:func:`project` builds a complete throwaway oarena project (config, bots, real
``.map26`` files, store, bus, league) and is the base of almost everything.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest

from oarena import config as configmod
from oarena import pool as poolmod
from oarena import runner as runnermod
from oarena.config import Config
from oarena.events import EventBus
from oarena.league import League
from oarena.ratings import Rater
from oarena.store import Store

from fake_worker import FakeRunner

FAKE_WORKER = Path(__file__).resolve().parent / "fake_worker.py"

DEFAULT_MAPS = ("sprint", "duel", "pinch")
"""Maps copied into a test project — three is enough to exercise map-major planning."""

TRIVIAL_BOT = "def main():\n    pass\n"


# --------------------------------------------------------------------------- #
# locating the real stock maps
# --------------------------------------------------------------------------- #


def _stock_maps_dir() -> Path | None:
    """The directory holding the 15 stock ``.map26`` files, if one is reachable."""
    candidates: list[Path] = []
    try:
        import fcode  # noqa: PLC0415 - optional, and pure Python

        candidates.append(Path(fcode.__file__).resolve().parent / "data" / "maps")
    except Exception:  # noqa: BLE001 - fcode is optional for most of the suite
        pass
    # fcode 2.3+ no longer bundles stock maps.  In the monorepo, use the
    # project's checked-in map pool without depending on a developer's home.
    candidates.append(Path(__file__).resolve().parents[3] / "maps")
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.map26")):
            return candidate
    return None


STOCK_MAPS = _stock_maps_dir()

requires_maps = pytest.mark.skipif(STOCK_MAPS is None, reason="no stock .map26 files available")


def _have_fcode() -> bool:
    try:
        import fcode  # noqa: F401,PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


HAVE_FCODE = _have_fcode()


# --------------------------------------------------------------------------- #
# project scaffolding
# --------------------------------------------------------------------------- #


def write_bot(bots_dir: Path, name: str, body: str = TRIVIAL_BOT) -> Path:
    """Create ``bots_dir/name/main.py`` and return the bot directory."""
    directory = bots_dir / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.py").write_text(body, encoding="utf-8")
    return directory


def copy_maps(dest: Path, names: tuple[str, ...] | None = None) -> list[str]:
    """Copy real ``.map26`` files into *dest*; returns the map names copied."""
    dest.mkdir(parents=True, exist_ok=True)
    if STOCK_MAPS is None:
        return []
    wanted = names if names is not None else tuple(p.stem for p in STOCK_MAPS.glob("*.map26"))
    copied: list[str] = []
    for stem in wanted:
        source = STOCK_MAPS / f"{stem}.map26"
        if source.is_file():
            shutil.copy2(source, dest / source.name)
            copied.append(stem)
    return copied


def make_project(
    root: Path,
    *,
    bots: tuple[str, ...] = ("alpha", "beta", "gamma"),
    map_names: tuple[str, ...] | None = DEFAULT_MAPS,
    extra_toml: str = "",
) -> Config:
    """Write a complete oarena project under *root* and return its config."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "oarena.toml").write_text(
        configmod.default_toml("bots", "maps") + extra_toml, encoding="utf-8"
    )
    for name in bots:
        write_bot(root / "bots", name)
    copy_maps(root / "maps", map_names)
    cfg = configmod.from_file(root / "oarena.toml")
    configmod.ensure_dirs(cfg)
    return cfg


@dataclass
class Project:
    """A throwaway oarena project with everything wired together."""

    root: Path
    cfg: Config
    store: Store
    bus: EventBus
    rater: Rater
    league: League
    runner: FakeRunner

    # -- convenience -------------------------------------------------------
    def types(self, kind: str) -> list[dict[str, Any]]:
        """Payloads of every emitted event of one type, in order."""
        return [e.data for e in self.bus.since(0, limit=10_000) if e.type == kind]

    def names(self) -> list[str]:
        return [b.name for b in self.store.bots()]

    def add_bot(self, name: str, body: str = TRIVIAL_BOT) -> Path:
        return write_bot(self.cfg.bots_dir, name, body)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_runner(monkeypatch: pytest.MonkeyPatch) -> FakeRunner:
    """Replace the game supervisor with the in-process fake, everywhere it is used."""
    fake = FakeRunner()
    monkeypatch.setattr(poolmod, "run_one", fake)
    monkeypatch.setattr(runnermod, "run_one", fake)
    return fake


@pytest.fixture
def project(tmp_path: Path, fake_runner: FakeRunner) -> Iterator[Project]:
    """A fresh project with three bots, three maps, and a league on the fake runner."""
    root = tmp_path / "proj"
    cfg = make_project(root)
    store = Store(cfg.db_path)
    bus = EventBus()
    rater = Rater(cfg.trueskill)
    league = League(cfg, store, bus, rater)
    try:
        yield Project(
            root=root, cfg=cfg, store=store, bus=bus, rater=rater,
            league=league, runner=fake_runner,
        )
    finally:
        league.stop()
        league.wait(timeout=15.0)
        store.close()


@pytest.fixture
def league(project: Project) -> League:
    """The wired-up :class:`~oarena.league.League` of :func:`project`."""
    return project.league


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    """A bare store on its own database file."""
    st = Store(tmp_path / "state" / "oarena.db")
    try:
        yield st
    finally:
        st.close()


@pytest.fixture
def rater() -> Rater:
    from oarena.config import TrueSkillConfig

    return Rater(TrueSkillConfig())


@pytest.fixture
def worker_script(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the *real* supervisor at ``tests/fake_worker.py`` instead of the engine.

    Only the argv is rewritten, so everything else :func:`oarena.runner.run_one`
    does — the job on stdin, the result file, the wall-clock deadline, the
    process-group kill — is exercised for real.
    """
    real_popen = subprocess.Popen

    def popen(argv: Any, *args: Any, **kwargs: Any) -> Any:
        if list(argv[1:3]) == ["-m", "oarena._worker"]:
            argv = [argv[0], str(FAKE_WORKER)]
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(runnermod.subprocess, "Popen", popen)


@pytest.fixture
def spec_factory(tmp_path: Path):
    """Build :class:`~oarena.runner.GameSpec` objects for arbitrary bot names."""
    from oarena.bots import BotSource
    from oarena.maps import GameMap

    root = tmp_path / "specs"
    (root / "maps").mkdir(parents=True, exist_ok=True)
    map_path = root / "maps" / "sprint.map26"
    map_path.write_bytes(b"\x08\x02\x10\x02" + b"\x1a\x04\x0a\x02\x00\x00" * 2)

    def build(a: str, b: str, *, seed: int = 7, timeout_s: float = 30.0) -> Any:
        from oarena.runner import GameSpec

        sources = []
        for name in (a, b):
            directory = root / "bots" / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "main.py").write_text(TRIVIAL_BOT, encoding="utf-8")
            sources.append(
                BotSource(
                    name=name,
                    dir=directory,
                    entry=directory / "main.py",
                    src_hash="deadbeef",
                )
            )
        game_map = GameMap(
            name="sprint", path=map_path, width=2, height=2, tiles=b"\0\0\0\0",
            spawns=((0, 0), (1, 1)),
        )
        return GameSpec(
            a=sources[0],
            b=sources[1],
            map=game_map,
            seed=seed,
            tle_ms=10,
            timeout_s=timeout_s,
            cwd=root,
            tmp_dir=root / "tmp",
        )

    return build
