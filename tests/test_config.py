"""`oarena.config`: defaults, fcode.toml detection and the generated template."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from oarena import config
from oarena.config import Config, ConfigError, TrueSkillConfig


def _write(root: Path, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / config.CONFIG_NAME
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# defaults
# --------------------------------------------------------------------------- #


def test_empty_config_uses_documented_defaults(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, ""))

    assert cfg.root == tmp_path.resolve()
    assert cfg.bots_dir == tmp_path.resolve() / "bots"
    assert cfg.maps_dir == tmp_path.resolve() / "maps"
    assert cfg.extra_maps_dir == tmp_path.resolve() / "more_maps"
    assert cfg.workers == 0
    assert cfg.tle_ms == 50
    assert cfg.game_timeout_s == 300.0
    assert cfg.maps == []
    assert cfg.mirror is True
    assert cfg.seed_policy == "random"
    assert cfg.seed == 1
    assert cfg.coinflip_is_draw is True
    assert cfg.python_dont_write_bytecode is False
    assert cfg.replay_budget_mb == 512
    assert cfg.sigma_reinflate == 0.5
    assert cfg.ui_theme == "dark"
    assert cfg.deactivate_missing_bots is True
    assert cfg.bot_sync_mode == "update"
    assert cfg.owns_state_dir is True


def test_trueskill_defaults_and_beta_falls_back_to_half_sigma(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, ""))
    ts = cfg.trueskill

    assert ts.mu == 25.0
    assert ts.sigma == pytest.approx(25.0 / 3.0)
    assert ts.tau == pytest.approx(25.0 / 300.0)
    assert ts.draw_prob == pytest.approx(0.02)
    assert ts.beta == pytest.approx(ts.sigma / 2.0)


def test_beta_defaults_to_half_of_a_custom_sigma(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, "[trueskill]\nsigma = 10.0\n"))
    assert cfg.trueskill.beta == pytest.approx(5.0)


def test_explicit_beta_wins(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, "[trueskill]\nsigma = 10.0\nbeta = 1.5\n"))
    assert cfg.trueskill.beta == pytest.approx(1.5)


def test_derived_paths_and_scalars(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, "workers = 3\nreplay_budget_mb = 2\n"))
    root = tmp_path.resolve()

    assert cfg.state_dir == root / ".oarena"
    assert cfg.db_path == root / ".oarena" / "oarena.db"
    assert cfg.replay_dir == root / ".oarena" / "replays"
    assert cfg.log_dir == root / ".oarena" / "logs"
    assert cfg.tmp_dir == root / ".oarena" / "tmp"
    assert cfg.n_workers == 3
    assert cfg.replay_budget_bytes == 2 * 1024 * 1024


def test_python_dont_write_bytecode_is_explicit_opt_in(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, "python_dont_write_bytecode = true\n"))
    assert cfg.python_dont_write_bytecode is True


def test_zero_workers_means_one_per_core(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, "workers = 0\n"))
    assert cfg.n_workers == (os.cpu_count() or 1)
    assert cfg.n_workers >= 1


def test_absolute_dirs_are_kept_and_relative_ones_resolved(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    cfg = config.from_file(
        _write(
            tmp_path / "p",
            f'bots_dir = "{elsewhere}"\n'
            'maps_dir = "../shared"\n'
            'extra_maps_dir = "../generated"\n',
        )
    )
    assert cfg.bots_dir == elsewhere
    assert cfg.maps_dir == (tmp_path / "shared").resolve()
    assert cfg.extra_maps_dir == (tmp_path / "generated").resolve()


def test_external_state_and_partial_catalog_options_are_explicit(tmp_path: Path) -> None:
    shared = tmp_path / "owner" / ".oarena"
    cfg = config.from_file(
        _write(
            tmp_path / "gate",
            f'state_dir = "{shared}"\n'
            "deactivate_missing_bots = false\n"
            'bot_sync_mode = "verify-only"\n',
        )
    )

    assert cfg.state_dir == shared
    assert cfg.db_path == shared / "oarena.db"
    assert cfg.deactivate_missing_bots is False
    assert cfg.bot_sync_mode == "verify-only"
    assert cfg.owns_state_dir is False


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        'seed_policy = "sideways"',
        "mirror = 1",
        'workers = "many"',
        "workers = -1",
        "trueskill = 3",
        "maps = [1, 2]",
        "game_timeout_s = 0",
        'bot_sync_mode = "invent"',
        "state_dir = 7",
    ],
)
def test_bad_values_raise_config_error(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigError):
        config.from_file(_write(tmp_path, text + "\n"))


def test_broken_toml_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid TOML"):
        config.from_file(_write(tmp_path, "bots_dir = [\n"))


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        config.from_file(tmp_path / "nope.toml")


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def test_find_config_walks_up(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert config.find_config(deep) == path


def test_find_config_returns_none_outside_a_project(tmp_path: Path) -> None:
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    # tmp_path itself must not be inside an oarena project for this to mean
    # anything; pytest's tmpdir never is.
    assert config.find_config(lonely) is None


def test_load_explains_how_to_create_a_project(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="oarena init"):
        config.load(tmp_path)


def test_load_finds_the_nearest_project(tmp_path: Path) -> None:
    _write(tmp_path, 'bots_dir = "robots"\n')
    deep = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    assert config.load(deep).bots_dir == tmp_path.resolve() / "robots"


# --------------------------------------------------------------------------- #
# fcode.toml detection
# --------------------------------------------------------------------------- #


def test_detect_fcode_reads_the_project_dirs(tmp_path: Path) -> None:
    (tmp_path / "fcode.toml").write_text(
        'bots_dir = "agents"\nmaps_dir = "arenas"\nseed = 1\n', encoding="utf-8"
    )
    assert config.detect_fcode(tmp_path) == ("agents", "arenas")


def test_detect_fcode_defaults_missing_keys(tmp_path: Path) -> None:
    (tmp_path / "fcode.toml").write_text("seed = 1\n", encoding="utf-8")
    assert config.detect_fcode(tmp_path) == ("bots", "maps")


def test_detect_fcode_returns_none_without_fcode_toml(tmp_path: Path) -> None:
    assert config.detect_fcode(tmp_path) is None


def test_detect_fcode_survives_a_broken_file(tmp_path: Path) -> None:
    (tmp_path / "fcode.toml").write_text("nonsense = [", encoding="utf-8")
    assert config.detect_fcode(tmp_path) is None


# --------------------------------------------------------------------------- #
# the generated template
# --------------------------------------------------------------------------- #


def test_default_toml_round_trips_to_the_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path, config.default_toml())
    cfg = config.from_file(path)
    blank = config.from_file(_write(tmp_path / "blank", ""))

    for field in (
        "workers", "tle_ms", "game_timeout_s", "maps", "mirror", "seed_policy",
        "seed", "coinflip_is_draw", "replay_budget_mb",
        "sigma_reinflate", "ui_theme", "deactivate_missing_bots", "bot_sync_mode",
    ):
        assert getattr(cfg, field) == getattr(blank, field), field
    assert cfg.trueskill == blank.trueskill == TrueSkillConfig()


def test_default_toml_substitutes_the_directories(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, config.default_toml("agents", "arenas")))
    assert cfg.bots_dir == tmp_path.resolve() / "agents"
    assert cfg.maps_dir == tmp_path.resolve() / "arenas"
    assert cfg.extra_maps_dir == tmp_path.resolve() / "more_maps"


def test_unlimited_replay_budget_round_trips_and_preserves_other_toml(tmp_path: Path) -> None:
    path = _write(tmp_path, "workers = 3\nreplay_budget_mb = 12  # hand edit\n")

    config.set_replay_budget(path, None)
    uncapped = config.from_file(path)
    assert uncapped.replay_budget_mb is None
    assert uncapped.replay_budget_bytes is None
    assert "workers = 3" in path.read_text(encoding="utf-8")
    assert 'replay_budget_mb = "unlimited"' in path.read_text(encoding="utf-8")

    config.set_replay_budget(path, 42)
    assert config.from_file(path).replay_budget_mb == 42


def test_ui_theme_round_trips_and_preserves_other_toml(tmp_path: Path) -> None:
    path = _write(tmp_path, 'workers = 3\nui_theme = "dark"  # hand edit\n')

    config.set_ui_theme(path, "light")
    assert config.from_file(path).ui_theme == "light"
    assert "workers = 3" in path.read_text(encoding="utf-8")

    with pytest.raises(ConfigError, match="ui_theme"):
        config.set_ui_theme(path, "violet")


def test_config_update_falls_back_when_parent_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, 'workers = 3\nui_theme = "dark"\n')
    original_write_text = Path.write_text

    def sandboxed_write_text(candidate: Path, *args: object, **kwargs: object) -> int:
        if candidate == path.with_name(f".{path.name}.tmp"):
            raise OSError(errno.EROFS, "read-only parent")
        return original_write_text(candidate, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", sandboxed_write_text)
    config.set_ui_theme(path, "light")

    assert config.from_file(path).ui_theme == "light"
    assert not path.with_name(f".{path.name}.tmp").exists()


def test_ensure_dirs_is_idempotent(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, ""))
    config.ensure_dirs(cfg)
    config.ensure_dirs(cfg)
    for directory in (
        cfg.state_dir, cfg.replay_dir, cfg.log_dir, cfg.tmp_dir
    ):
        assert directory.is_dir()


def test_config_is_frozen(tmp_path: Path) -> None:
    cfg = config.from_file(_write(tmp_path, ""))
    assert isinstance(cfg, Config)
    with pytest.raises(Exception):
        cfg.workers = 4  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# locating fcode
# --------------------------------------------------------------------------- #


def test_check_fcode_reports_a_version_or_explains_itself() -> None:
    try:
        version = config.check_fcode()
    except RuntimeError as exc:
        assert "pip install fcode" in str(exc)
    else:
        assert isinstance(version, str) and version


def test_visualiser_dist_is_a_directory_or_none() -> None:
    dist = config.visualiser_dist()
    assert dist is None or (dist / "index.html").is_file()
