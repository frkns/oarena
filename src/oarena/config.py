"""Project configuration and engine discovery.

An oarena project is any directory containing an ``oarena.toml``; everything
oarena writes lives under ``<root>/.oarena/``.  This module also owns the three
helpers that locate the ambient fcode installation (:func:`check_fcode`,
:func:`fcode_engine_root`, :func:`visualiser_dist`) so the runner and the HTTP
server resolve the engine identically.

Nothing here may ever import ``fcode.fcode_engine``: a bot that fails to import
takes the whole interpreter down with it, so only worker subprocesses touch the
native extension.  ``import fcode`` itself is pure Python and safe.
"""

from __future__ import annotations

import errno
import importlib
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "oarena.toml"
STATE_DIR = ".oarena"

FCODE_CONFIG_NAME = "fcode.toml"

_SEED_POLICIES = ("random", "fixed")
_UI_THEMES = ("dark", "light")
_BOT_SYNC_MODES = ("update", "verify-only")


class ConfigError(RuntimeError):
    """Raised when a project is missing or its ``oarena.toml`` is unusable."""


# --------------------------------------------------------------------------- #
# dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TrueSkillConfig:
    """TrueSkill environment parameters.

    ``beta`` defaults to ``sigma / 2`` when the key is absent from the file,
    which is the library default and keeps the skill/uncertainty scales tied.
    """

    mu: float = 25.0
    sigma: float = 25.0 / 3.0
    beta: float = 25.0 / 6.0
    tau: float = 25.0 / 300.0
    draw_prob: float = 0.02


@dataclass(frozen=True)
class Config:
    """A fully resolved project configuration. All paths are absolute."""

    root: Path
    bots_dir: Path
    maps_dir: Path
    extra_maps_dir: Path
    workers: int
    tle_ms: int
    game_timeout_s: float
    maps: list[str]
    mirror: bool
    seed_policy: str
    seed: int
    coinflip_is_draw: bool
    python_dont_write_bytecode: bool
    replay_budget_mb: int | None
    sigma_reinflate: float
    ui_theme: str
    state_dir_override: Path | None = None
    deactivate_missing_bots: bool = True
    bot_sync_mode: str = "update"
    trueskill: TrueSkillConfig = field(default_factory=TrueSkillConfig)

    # --- derived paths ---------------------------------------------------- #

    @property
    def state_dir(self) -> Path:
        return self.state_dir_override or (self.root / STATE_DIR)

    @property
    def db_path(self) -> Path:
        return self.state_dir / "oarena.db"

    @property
    def replay_dir(self) -> Path:
        return self.state_dir / "replays"

    @property
    def log_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def tmp_dir(self) -> Path:
        return self.state_dir / "tmp"

    @property
    def owns_state_dir(self) -> bool:
        """Whether destructive maintenance targets this config's own project."""

        try:
            return self.state_dir.resolve() == (self.root / STATE_DIR).resolve()
        except OSError:
            return self.state_dir == self.root / STATE_DIR

    @property
    def config_path(self) -> Path:
        return self.root / CONFIG_NAME

    # --- derived scalars --------------------------------------------------- #

    @property
    def n_workers(self) -> int:
        """Effective parallelism; ``workers = 0`` means one game per core."""
        return self.workers or (os.cpu_count() or 1)

    @property
    def replay_budget_bytes(self) -> int | None:
        """Replay cap in bytes, or ``None`` when automatic pruning is off."""
        return None if self.replay_budget_mb is None else self.replay_budget_mb * 1024 * 1024


# --------------------------------------------------------------------------- #
# typed TOML access
# --------------------------------------------------------------------------- #


def _get(data: dict[str, Any], key: str, default: Any) -> Any:
    value = data.get(key, default)
    return default if value is None else value


def _as_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = _get(data, key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key!r} must be true or false, got {value!r}")
    return value


def _as_int(data: dict[str, Any], key: str, default: int, *, minimum: int | None = None) -> int:
    value = _get(data, key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key!r} must be an integer, got {value!r}")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{key!r} must be >= {minimum}, got {value!r}")
    return value


def _as_float(
    data: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = _get(data, key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key!r} must be a number, got {value!r}")
    value = float(value)
    if minimum is not None and value < minimum:
        raise ConfigError(f"{key!r} must be >= {minimum}, got {value!r}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{key!r} must be <= {maximum}, got {value!r}")
    return value


def _as_str(data: dict[str, Any], key: str, default: str) -> str:
    value = _get(data, key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key!r} must be a string, got {value!r}")
    return value


def _as_str_list(data: dict[str, Any], key: str) -> list[str]:
    value = _get(data, key, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key!r} must be a list of strings, got {value!r}")
    return list(value)


def _as_replay_budget(data: dict[str, Any]) -> int | None:
    """An MB cap, with ``\"unlimited\"`` spelling an uncapped replay store."""
    value = _get(data, "replay_budget_mb", 512)
    if isinstance(value, str) and value.strip().lower() in {"unlimited", "uncapped", "none"}:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError("'replay_budget_mb' must be a non-negative integer or 'unlimited'")
    return value


def _as_ui_theme(data: dict[str, Any]) -> str:
    """The project-wide dashboard theme, independent of the serving port."""
    theme = _as_str(data, "ui_theme", "dark").strip().lower()
    if theme not in _UI_THEMES:
        raise ConfigError(f"'ui_theme' must be one of {' | '.join(_UI_THEMES)}, got {theme!r}")
    return theme


def _as_bot_sync_mode(data: dict[str, Any]) -> str:
    """How discovery may reconcile source rows with the shared bot catalog."""

    mode = _as_str(data, "bot_sync_mode", "update").strip().lower()
    if mode not in _BOT_SYNC_MODES:
        raise ConfigError(
            f"'bot_sync_mode' must be one of {' | '.join(_BOT_SYNC_MODES)}, got {mode!r}"
        )
    return mode


def _resolve_dir(root: Path, value: str, key: str) -> Path:
    if not value:
        raise ConfigError(f"{key!r} must not be empty")
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = root / p
    return Path(os.path.normpath(p))


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) looking for ``oarena.toml``."""
    here = Path(start).expanduser() if start is not None else Path.cwd()
    try:
        here = here.resolve()
    except OSError:  # pragma: no cover - unreadable cwd
        return None
    if here.is_file():
        here = here.parent
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load(start: Path | None = None) -> Config:
    """Find and parse the nearest project config, or explain how to make one."""
    path = find_config(start)
    if path is None:
        where = Path(start) if start is not None else Path.cwd()
        raise ConfigError(
            f"no {CONFIG_NAME} found in {where} or any parent directory — "
            "run `oarena init` in your project root"
        )
    return from_file(path)


def from_file(path: Path) -> Config:
    """Parse a specific ``oarena.toml``; its directory becomes the project root."""
    path = Path(path).expanduser()
    try:
        path = path.resolve()
    except OSError as exc:  # pragma: no cover - exotic filesystems
        raise ConfigError(f"cannot resolve {path}: {exc}") from exc
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="replace"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    root = path.parent
    ts_raw = _get(data, "trueskill", {})
    if not isinstance(ts_raw, dict):
        raise ConfigError("'trueskill' must be a table")

    sigma = _as_float(ts_raw, "sigma", TrueSkillConfig.sigma, minimum=1e-9)
    trueskill = TrueSkillConfig(
        mu=_as_float(ts_raw, "mu", TrueSkillConfig.mu),
        sigma=sigma,
        beta=_as_float(ts_raw, "beta", sigma / 2.0, minimum=1e-9),
        tau=_as_float(ts_raw, "tau", TrueSkillConfig.tau, minimum=0.0),
        draw_prob=_as_float(ts_raw, "draw_prob", TrueSkillConfig.draw_prob, minimum=0.0, maximum=0.999),
    )

    seed_policy = _as_str(data, "seed_policy", "random").strip().lower()
    if seed_policy not in _SEED_POLICIES:
        raise ConfigError(
            f"'seed_policy' must be one of {' | '.join(_SEED_POLICIES)}, got {seed_policy!r}"
        )

    state_dir_raw = _as_str(data, "state_dir", "").strip()
    state_dir_override = (
        _resolve_dir(root, state_dir_raw, "state_dir") if state_dir_raw else None
    )

    return Config(
        root=root,
        bots_dir=_resolve_dir(root, _as_str(data, "bots_dir", "bots"), "bots_dir"),
        maps_dir=_resolve_dir(root, _as_str(data, "maps_dir", "maps"), "maps_dir"),
        extra_maps_dir=_resolve_dir(
            root,
            _as_str(data, "extra_maps_dir", "more_maps"),
            "extra_maps_dir",
        ),
        workers=_as_int(data, "workers", 0, minimum=0),
        tle_ms=_as_int(data, "tle_ms", 50, minimum=0),
        game_timeout_s=_as_float(data, "game_timeout_s", 300.0, minimum=1.0),
        maps=_as_str_list(data, "maps"),
        mirror=_as_bool(data, "mirror", True),
        seed_policy=seed_policy,
        seed=_as_int(data, "seed", 1),
        coinflip_is_draw=_as_bool(data, "coinflip_is_draw", True),
        python_dont_write_bytecode=_as_bool(
            data, "python_dont_write_bytecode", False
        ),
        replay_budget_mb=_as_replay_budget(data),
        sigma_reinflate=_as_float(data, "sigma_reinflate", 0.5, minimum=0.0, maximum=1.0),
        ui_theme=_as_ui_theme(data),
        state_dir_override=state_dir_override,
        deactivate_missing_bots=_as_bool(data, "deactivate_missing_bots", True),
        bot_sync_mode=_as_bot_sync_mode(data),
        trueskill=trueskill,
    )


def detect_fcode(root: Path) -> tuple[str, str] | None:
    """Read ``fcode.toml`` in *root* and return its ``(bots_dir, maps_dir)``.

    Returns ``None`` when *root* is not an fcode project, which lets
    ``oarena init`` fall back to its own defaults.
    """
    path = Path(root).expanduser() / FCODE_CONFIG_NAME
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8", errors="replace"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    bots_dir = data.get("bots_dir", "bots")
    maps_dir = data.get("maps_dir", "maps")
    if not isinstance(bots_dir, str) or not isinstance(maps_dir, str):
        return None
    return bots_dir or "bots", maps_dir or "maps"


def default_toml(bots_dir: str = "bots", maps_dir: str = "maps") -> str:
    """Render a fresh, fully commented ``oarena.toml``."""
    bots_line = f'bots_dir = "{bots_dir}"'.ljust(24)
    maps_line = f'maps_dir = "{maps_dir}"'.ljust(24)
    extra_maps_line = 'extra_maps_dir = "more_maps"'.ljust(34)
    return f"""\
# oarena — local bot league for the Florent Code League (fcode).
# State lives in ./{STATE_DIR}/ ; delete that directory to start over.

{bots_line}# every sub-directory holding main.py is a bot
{maps_line}# official *.map26 maps
{extra_maps_line}# generated/local *.map26 maps
# state_dir = "/absolute/shared/.oarena"  # optional shared league state
# deactivate_missing_bots = false        # partial bot catalogs must opt out
# bot_sync_mode = "verify-only"           # verify hashes; never rewrite shared bot rows

workers        = 0      # parallel games; 0 = one per CPU core
tle_ms         = 50     # profiling-friendly local per-turn limit; platform uses 10 (0 = off)
game_timeout_s = 300    # hard wall-clock kill for a single game

# Which maps a match plays when you don't pass -m. Empty = every map in both directories.
maps        = []
mirror      = true      # play every (map, seed) twice with sides swapped
seed_policy = "random"  # random | fixed
seed        = 1         # base seed when seed_policy = "fixed"

coinflip_is_draw = true   # the engine's coinflip tiebreak carries no skill signal
python_dont_write_bytecode = false  # pass PYTHONDONTWRITEBYTECODE=1 to game workers

replay_budget_mb = 512  # oldest replays are pruned past this; "unlimited" disables pruning
sigma_reinflate  = 0.5  # on source change, sigma is lifted back to at least 0.5 * sigma0
ui_theme         = "dark" # dashboard theme; saved by the UI and shared by every server port

[trueskill]
mu        = {TrueSkillConfig.mu!r}
sigma     = {TrueSkillConfig.sigma!r}
tau       = {TrueSkillConfig.tau!r}
draw_prob = {TrueSkillConfig.draw_prob!r}
# beta    = {TrueSkillConfig.beta!r}   # defaults to sigma / 2
"""


def ensure_dirs(cfg: Config) -> None:
    """Create every directory oarena writes into. Idempotent."""
    for d in (
        cfg.state_dir,
        cfg.replay_dir,
        cfg.log_dir,
        cfg.tmp_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)


_REPLAY_BUDGET_LINE = re.compile(r"(?m)^\s*replay_budget_mb\s*=.*$")
_UI_THEME_LINE = re.compile(r"(?m)^\s*ui_theme\s*=.*$")


def _write_config(path: Path, updated: str) -> None:
    """Replace a config atomically, with a file-only sandbox fallback.

    Hardened services can grant write access to ``oarena.toml`` while keeping
    its parent (and therefore the source tree) read-only.  Such a sandbox
    cannot create the sibling temporary file needed for ``Path.replace``.  In
    that specific case, update the already-existing, explicitly writable file
    in place; all other atomic-write failures remain errors.
    """
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(updated, encoding="utf-8")
        temporary.replace(path)
        return
    except OSError as atomic_exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        if atomic_exc.errno not in {errno.EACCES, errno.EROFS}:
            raise ConfigError(f"cannot write {path}: {atomic_exc}") from atomic_exc

    try:
        with path.open("r+", encoding="utf-8") as handle:
            handle.seek(0)
            handle.write(updated)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as direct_exc:
        raise ConfigError(f"cannot write {path}: {direct_exc}") from direct_exc


def set_replay_budget(path: Path, budget_mb: int | None) -> None:
    """Persist one replay-budget setting without rewriting the user's TOML.

    Keeping comments and unrelated hand edits intact matters more than having a
    general TOML writer for this one small dashboard setting.
    """
    path = Path(path)
    value = '"unlimited"' if budget_mb is None else str(int(budget_mb))
    line = f"replay_budget_mb = {value}  # oldest replays are pruned past this; \"unlimited\" disables pruning"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if _REPLAY_BUDGET_LINE.search(text):
        updated = _REPLAY_BUDGET_LINE.sub(line, text, count=1)
    elif "[trueskill]" in text:
        updated = text.replace("[trueskill]", f"{line}\n\n[trueskill]", 1)
    else:
        updated = text.rstrip() + f"\n\n{line}\n"
    _write_config(path, updated)


def set_ui_theme(path: Path, theme: str) -> None:
    """Persist the dashboard theme in project config, retaining other TOML."""
    theme = theme.strip().lower()
    if theme not in _UI_THEMES:
        raise ConfigError(f"'ui_theme' must be one of {' | '.join(_UI_THEMES)}, got {theme!r}")
    path = Path(path)
    line = f'ui_theme = "{theme}"  # dashboard theme; saved by the UI and shared by every server port'
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if _UI_THEME_LINE.search(text):
        updated = _UI_THEME_LINE.sub(line, text, count=1)
    elif "[trueskill]" in text:
        updated = text.replace("[trueskill]", f"{line}\n\n[trueskill]", 1)
    else:
        updated = text.rstrip() + f"\n\n{line}\n"
    _write_config(path, updated)


# --------------------------------------------------------------------------- #
# locating fcode
# --------------------------------------------------------------------------- #

_FCODE_MISSING = (
    "the fcode engine is not importable from this interpreter.\n"
    "  Install it with:  pip install fcode\n"
    "  (oarena uses whichever fcode the ambient interpreter provides.)"
)


def _import_fcode() -> Any:
    """Import the pure-Python ``fcode`` package (never ``fcode.fcode_engine``)."""
    try:
        return importlib.import_module("fcode")
    except Exception as exc:  # ImportError, but a broken install can raise anything
        raise RuntimeError(f"{_FCODE_MISSING}\n  ({type(exc).__name__}: {exc})") from exc


def check_fcode() -> str:
    """Return the installed fcode version, raising ``RuntimeError`` if absent."""
    module = _import_fcode()
    version = getattr(module, "__version__", None)
    return str(version) if version else "unknown"


def fcode_metadata(module: Any | None = None) -> dict[str, Any]:
    """Return the public, pure-Python game metadata needed by replay clients.

    Values are read from the ambient :mod:`fcode` package on every call so the
    API remains a single source of truth across engine upgrades.  The game
    worker passes the already-imported module explicitly, guaranteeing the
    snapshot belongs to the exact package whose native engine it is about to
    invoke.  This never imports the native ``fcode.fcode_engine`` extension.
    """
    if module is None:
        module = _import_fcode()
    enum_names = ("EntityType", "Environment", "ResourceType", "Team", "Direction")

    try:
        game_constants = {}
        for name in dir(module.GameConstants):
            if not name.isupper():
                continue
            value = getattr(module.GameConstants, name)
            if value is None or type(value) in (bool, int, float, str):
                game_constants[name] = value
        enums: dict[str, list[dict[str, Any]]] = {}
        for enum_name in enum_names:
            members = []
            for member in getattr(module, enum_name):
                if member.value is not None and type(member.value) not in (bool, int, float, str):
                    raise TypeError(f"{enum_name}.{member.name}.value is not a JSON scalar")
                members.append({"name": member.name, "value": member.value})
            enums[enum_name] = members

        direction_deltas: dict[str, list[Any]] = {}
        for direction in module.Direction:
            delta = list(direction.delta())
            if len(delta) != 2 or any(type(value) not in (int, float) for value in delta):
                raise TypeError(f"Direction.{direction.name}.delta() is not a numeric pair")
            direction_deltas[direction.name] = delta
    except Exception as exc:
        raise RuntimeError(
            f"cannot read metadata from the installed fcode package "
            f"({type(exc).__name__}: {exc})"
        ) from exc

    version = getattr(module, "__version__", None)
    return {
        "metadata_version": 1,
        "version": str(version) if version else "unknown",
        "game_constants": game_constants,
        "enums": enums,
        "direction_deltas": direction_deltas,
    }


def fcode_engine_root() -> Path:
    """The directory handed to ``run_game`` as ``engine_root``."""
    module = _import_fcode()
    file = getattr(module, "__file__", None)
    if not file:
        raise RuntimeError(f"{_FCODE_MISSING}\n  (fcode has no __file__; is it a namespace package?)")
    return Path(file).resolve().parent


def visualiser_dist() -> Path | None:
    """The bundled Vite build, or ``None`` when this fcode ships without one."""
    try:
        root = fcode_engine_root()
    except RuntimeError:
        return None
    dist = root / "data" / "visualiser"
    return dist if (dist / "index.html").is_file() else None
