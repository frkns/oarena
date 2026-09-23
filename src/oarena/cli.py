"""The oarena command line — the primary interface to a local fcode league.

Every command that touches project state follows the same three steps: load the
nearest ``oarena.toml`` (lazily, *inside* the command, so ``init`` and ``--help``
work anywhere), open the store, and let :class:`~oarena.league.League` sync the
bots on disk into it.  :func:`_session` packages that up.

Rendering lives here rather than in ``reporting`` because it is terminal-specific:
the ladder's shared-scale sigma bands, the live arena view, the coloured
head-to-head crosstable.  Anything a machine might want to read is produced by
``reporting`` and printed verbatim under ``--json``.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from . import __version__, bots as botsmod, config as configmod, maps as mapsmod, reporting
from .bots import BotError
from .config import Config, ConfigError
from .events import EventBus
from .league import League
from .maps import MapError
from .pool import Pool
from .ratings import CI, CI_LABEL, CI_PERCENT, Rater
from .reporting import LadderRow
from .runner import GameSpec
from .store import (
    Game,
    Record,
    Store,
    StoreBatchError,
    StoreBusyError,
    StoreConfigError,
    StoreImportError,
    StoreSchemaError,
)

console = Console(highlight=False, soft_wrap=False)
err_console = Console(stderr=True, highlight=False)

# Shared with the web UI's palette (see the contract's §16).
C_WIN = "#35d07f"
C_LOSS = "#ff5d5d"
C_DRAW = "#8b93a3"
C_ACCENT = "orange1"
C_MUTE = "grey42"
C_FAINT = "grey35"

BAR_WIDTH = 26
"""Character width of the ladder's sigma band."""

ARENA_LADDER_LIMIT = 10
"""Rows in each leaderboard snapshot printed by a running arena."""

ARENA_LADDER_INTERVAL_S = 60.0
"""Minimum wall-clock interval between persistent arena leaderboard snapshots."""

ARENA_LIVE_INTERVAL_S = 0.5
"""How often the lightweight live arena statistics are refreshed."""

_UNINDENTED = re.compile(r"^\S")


# --------------------------------------------------------------------------- #
# session
# --------------------------------------------------------------------------- #


@dataclass
class Session:
    """Everything a stateful command needs, wired together once."""

    cfg: Config
    store: Store
    bus: EventBus
    rater: Rater
    league: League

    def close(self) -> None:
        """Abort any active run, reap its workers, then close the database.

        A command can be interrupted outside its main progress loop (including
        during startup).  Closing SQLite while the league thread is still
        recording killed workers races that thread and leaves the executor for
        Python's atexit hook to join, so every CLI session has this final safety
        net.
        """
        reaped = False
        try:
            self.league.force_stop()
        except Exception:  # noqa: BLE001 - shutdown must not mask the real error
            pass
        while not reaped:
            try:
                reaped = self.league.wait(timeout=0.25)
            except KeyboardInterrupt:
                # A second Ctrl-C reasserts cancellation instead of escaping
                # into Python's ThreadPoolExecutor atexit join.
                try:
                    self.league.force_stop()
                except Exception:  # noqa: BLE001 - keep reaping the first abort
                    pass
            except Exception:  # noqa: BLE001 - leave SQLite open rather than race a writer
                break
        if not reaped:
            return
        try:
            self.store.close()
        except Exception:  # noqa: BLE001 - closing must never mask a real error
            pass


@contextmanager
def _session(
    *,
    workers: int | None = None,
    seed: int | None = None,
    sync: bool = True,
    quiet: bool = False,
) -> Iterator[Session]:
    """Open the project in the current directory and sync the bots on disk.

    ``workers`` and ``seed`` are per-invocation overrides of the config file;
    they are applied to the frozen :class:`Config` before anything reads it, so
    the league, the pool and the job planner all see the same values.
    """
    cfg = configmod.load()
    if workers is not None:
        cfg = replace(cfg, workers=max(0, int(workers)))
    if seed is not None:
        cfg = replace(cfg, seed_policy="fixed", seed=int(seed))
    configmod.ensure_dirs(cfg)

    if not cfg.owns_state_dir:
        owner_path = cfg.state_dir.parent / configmod.CONFIG_NAME
        if owner_path.is_file():
            owner = configmod.from_file(owner_path)
            if owner.trueskill != cfg.trueskill:
                raise ConfigError(
                    f"shared state {cfg.state_dir} belongs to a project with different "
                    "TrueSkill settings"
                )

    store = Store(cfg.db_path)
    rater = Rater(cfg.trueskill)
    try:
        store.ensure_rating_config(cfg.trueskill)
    except BaseException:
        store.close()
        raise
    bus = EventBus()
    sess = Session(cfg=cfg, store=store, bus=bus, rater=rater, league=League(cfg, store, bus, rater))
    try:
        if sync:
            _print_sync(sess.league.sync(), quiet=quiet)
        yield sess
    finally:
        sess.close()


def _print_sync(report: Any, *, quiet: bool) -> None:
    """Announce what discovery changed. Silent when nothing did."""
    if quiet:
        return
    for name in getattr(report, "added", ()):
        console.print(Text("  + ", style="green") + Text(name) + Text("  registered", style=C_MUTE))
    for name in getattr(report, "changed", ()):
        console.print(
            Text("  ~ ", style=C_ACCENT)
            + Text(name)
            + Text("  source changed, uncertainty re-inflated", style=C_MUTE)
        )
    for name in getattr(report, "unbroken", ()):
        console.print(Text("  ✓ ", style="green") + Text(name) + Text("  no longer broken", style=C_MUTE))
    for name in getattr(report, "missing", ()):
        console.print(
            Text("  - ", style="yellow") + Text(name) + Text("  directory gone, deactivated", style=C_MUTE)
        )


def _require_owned_state(cfg: Config, action: str) -> None:
    """Refuse destructive maintenance through a config that borrows state."""

    if not cfg.owns_state_dir:
        raise ConfigError(
            f"{action} is disabled because this config uses external shared state "
            f"{cfg.state_dir}; run it from the owning project instead"
        )


def _emit_json(payload: Any) -> None:
    """Print machine-readable JSON and nothing else."""
    click.echo(json.dumps(payload, indent=2, default=str))


def _fatal(message: object) -> None:
    text = " ".join(str(message).split())
    err_console.print(Text("error: ", style="bold red") + Text(text, style="red"))


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #


def _when(ts: str) -> str:
    """ISO-8601 UTC → a short local-time stamp (time today, date + time before)."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return ts[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%H:%M:%S")
    return local.strftime("%m-%d %H:%M")


def _dur(ms: int) -> str:
    seconds = max(0, int(ms)) / 1000.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _blend(lo: tuple[int, int, int], hi: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(lo, hi))  # type: ignore[return-value]


def _winrate_style(winrate: float) -> str:
    """Diverging loss-red → neutral → win-green scale, matching the web UI."""
    loss, draw, win = (0xFF, 0x5D, 0x5D), (0x8B, 0x93, 0xA3), (0x35, 0xD0, 0x7F)
    if winrate < 0.5:
        return _hex(_blend(loss, draw, winrate / 0.5))
    return _hex(_blend(draw, win, (winrate - 0.5) / 0.5))


def _tally(rec: Record, side: str, winner: str | None) -> None:
    if winner is None:
        return
    if winner == "draw":
        rec.draws += 1
    elif winner == side:
        rec.wins += 1
    else:
        rec.losses += 1
    rec.games += 1


def _first_error_line(text: str) -> str:
    """The most informative single line of a captured stderr log.

    A traceback's *first* line is always the useless ``Traceback (most recent
    call last):`` banner, so this returns the first unindented line after it —
    i.e. the exception itself — and falls back to the first non-empty line.
    """
    marker = "Traceback (most recent call last):"
    head, sep, rest = text.partition(marker)
    if sep:
        for line in rest.splitlines():
            if line.strip() and _UNINDENTED.match(line):
                return line.strip()
    for line in (head if sep else text).splitlines():
        if line.strip():
            return line.strip()
    return ""


def _log_text(cfg: Config, game: Game) -> str:
    if not game.log:
        return ""
    try:
        return (cfg.log_dir / game.log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _matchup(game: Game) -> Text:
    """``a vs b`` with the winner in bold green and a ▲ marker."""
    text = Text()
    a_won, b_won = game.winner == "a", game.winner == "b"
    text.append(game.a, style="bold " + C_WIN if a_won else ("dim" if b_won else ""))
    text.append(" ▲" if a_won else "  ", style=C_WIN)
    text.append(" vs ", style=C_FAINT)
    text.append(game.b, style="bold " + C_WIN if b_won else ("dim" if a_won else ""))
    text.append(" ▲" if b_won else "", style=C_WIN)
    return text


def _result_cell(game: Game) -> Text:
    if game.status != "ok":
        detail = game.error.splitlines()[0] if game.error else ""
        return Text(game.status, style="bold red") + Text(f"  {detail}"[:60], style="red")
    if game.a_errors or game.b_errors:
        return Text(game.win_condition.replace("_", " ") or "bot error", style="bold red")
    if game.winner == "draw":
        return Text(f"draw · {game.win_condition}", style=C_DRAW)
    return Text(game.win_condition or "decided", style=C_MUTE)


# --------------------------------------------------------------------------- #
# the ladder table
# --------------------------------------------------------------------------- #


def _scale(rows: Sequence[LadderRow]) -> tuple[float, float]:
    """The 95%-interval window shared by every band, with a little breathing room.

    Bots that have never played still carry the full starting sigma, and letting
    one of them set the scale would squash every settled band into a stub. The
    window is therefore taken from the bots that have actually played; the rest
    overflow it and :func:`_sigma_bar` marks them as running off the edge.
    """
    settled = [r for r in rows if r.games > 0] or list(rows)
    lo = min(r.mu - CI * r.sigma for r in settled)
    hi = max(r.mu + CI * r.sigma for r in settled)
    if hi - lo < 1e-6:
        lo, hi = lo - 1.0, hi + 1.0
    pad = (hi - lo) * 0.02
    return lo - pad, hi + pad


def _sigma_bar(row: LadderRow, lo: float, hi: float, width: int = BAR_WIDTH) -> Text:
    """One bot's 95% interval drawn on the ladder-wide scale.

    Two bands that do not overlap are a real ordering; two that do are not yet
    separated no matter what the ranks say. A band wider than the window is
    clipped and its ends become ``◄``/``►``.
    """
    span = hi - lo or 1.0
    last = width - 1

    def cell(value: float) -> int:
        return int(round((value - lo) / span * last))

    left, right, mid = cell(row.mu - CI * row.sigma), cell(row.mu + CI * row.sigma), cell(row.mu)
    if row.broken:
        style = C_LOSS
    elif not row.active:
        style = C_MUTE
    elif row.rank == 1:
        style = "gold1"
    else:
        style = C_ACCENT

    bar = Text()
    for i in range(width):
        if i == 0 and left < 0:
            bar.append("◄", style=style)
        elif i == last and right > last:
            bar.append("►", style=style)
        elif i == mid:
            bar.append("●", style=f"{style} bold")
        elif left <= i <= right:
            bar.append("━", style=style)
        else:
            bar.append("·", style=C_FAINT)
    return bar


def _bot_cell(row: LadderRow) -> Text:
    text = Text()
    if row.broken:
        text.append(row.name, style=f"dim {C_LOSS}")
        text.append("  broken", style=f"bold {C_LOSS}")
    elif not row.active:
        text.append(row.name, style="dim")
        text.append("  off", style=C_MUTE)
    else:
        text.append(row.name, style="bold" if row.rank == 1 else "")
    return text


MIN_BAND = 12
"""Below this many characters a σ-band says nothing, so the column is dropped."""


def _natural_width(table: Table) -> int:
    """The width the table wants, unclamped by the current console size."""
    return console.measure(table, options=console.options.update_width(10_000)).maximum


def _compose_ladder(
    rows: Sequence[LadderRow],
    lo: float,
    hi: float,
    *,
    band: int,
    err: bool,
    sigma: bool,
    record: bool,
    title: str | None,
    caption: bool,
) -> Table:
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style=f"bold {C_MUTE}",
        title=title,
        title_style=f"bold {C_ACCENT}",
        title_justify="left",
        pad_edge=False,
        expand=False,
    )
    table.add_column("#", justify="right", style=C_MUTE, no_wrap=True)
    table.add_column("BOT", justify="left", no_wrap=True)
    table.add_column("MU", justify="right", no_wrap=True, min_width=5)
    table.add_column("LCB95", justify="right", style=C_MUTE, no_wrap=True, min_width=5)
    if sigma:
        table.add_column("σ", justify="right", style=C_MUTE, no_wrap=True)
    table.add_column("RATED", justify="right", no_wrap=True)
    if record:
        table.add_column("W-L-D", justify="right", no_wrap=True)
        table.add_column("WIN%", justify="right", no_wrap=True)
    if err:
        table.add_column("ERR", justify="right", no_wrap=True)
    if band:
        table.add_column("RANGE", justify="left", no_wrap=True)

    for row in rows:
        dim = "dim " if (row.broken or not row.active) else ""
        rate_style = _winrate_style(row.winrate) if row.winrate is not None else C_MUTE
        cells: list[Any] = [
            str(row.rank),
            _bot_cell(row),
            Text(f"{row.mu:.2f}", style=dim + ("bold " + C_ACCENT if row.rank == 1 else "")),
            Text(f"{row.lcb95:.2f}", style=dim or C_MUTE),
        ]
        if sigma:
            cells.append(Text(f"{row.sigma:.2f}", style=dim or C_MUTE))
        cells.append(Text(str(row.games), style=dim))
        if record:
            cells.append(Text(f"{row.wins}-{row.losses}-{row.draws}", style=dim))
            cells.append(Text(_pct(row.winrate), style=dim + rate_style))
        if err:
            cells.append(
                Text(str(row.err_total), style=f"{dim}{C_LOSS}")
                if row.err_total
                else Text("·", style=C_FAINT)
            )
        if band:
            cells.append(_sigma_bar(row, lo, hi, band))
        table.add_row(*cells)

    if caption and band:
        table.caption = (
            f"Ranked by μ (mean skill estimate), descending. LCB95 = {CI_LABEL}, the "
            f"conservative lower edge.\nRANGE draws each bot's {CI_PERCENT}% interval on one "
            f"shared scale [{lo:.1f} … {hi:.1f}]; ● = μ, and the band's left edge is LCB95.\n"
            "Bands that overlap are not yet separated, whatever the ranks say.\n"
            "RATED/W-L-D/WIN% count rated decisions; ERR counts attributed bot errors."
        )
        table.caption_style = C_FAINT
        table.caption_justify = "left"
    return table


def _ladder_table(
    rows: Sequence[LadderRow],
    *,
    title: str | None = None,
    caption: bool = True,
    width: int | None = None,
) -> Table:
    """``#  BOT  MU  LCB95  σ  RATED  W-L-D  WIN%  ERR  RANGE`` with shared-scale bands.

    The numbers are the point of the table and everything else is commentary, so
    as the terminal narrows the σ-band shrinks, then goes, followed by ERR, σ,
    and the record columns. Left to itself rich would instead ellipsise the
    primary rating values into ``22.…``.
    """
    lo, hi = _scale(rows) if rows else (0.0, 1.0)
    avail = console.width if width is None else width
    band, err, sigma, record = BAR_WIDTH, True, True, True
    while True:
        table = _compose_ladder(
            rows,
            lo,
            hi,
            band=band,
            err=err,
            sigma=sigma,
            record=record,
            title=title,
            caption=caption,
        )
        over = _natural_width(table) - avail
        if over <= 0:
            return table
        if band:
            band = 0 if band - over < MIN_BAND else band - over
        elif err:
            err = False
        elif sigma:
            sigma = False
        elif record:
            record = False
        else:
            return table  # nothing left to shed; let rich do what it can


def _empty_ladder(cfg: Config) -> Panel:
    return Panel(
        Text.assemble(
            ("no bots yet.\n\n", "bold"),
            ("drop a directory containing ", C_MUTE),
            ("main.py", C_ACCENT),
            (" into\n", C_MUTE),
            (str(cfg.bots_dir), ""),
            ("\n\nthen run ", C_MUTE),
            ("oarena ladder", C_ACCENT),
            (" again.", C_MUTE),
        ),
        border_style=C_MUTE,
        title="empty ladder",
        title_align="left",
    )


# --------------------------------------------------------------------------- #
# root group
# --------------------------------------------------------------------------- #

ALIASES = {"show": "ladder", "ls": "ladder"}


class OrderedGroup(click.Group):
    """A group whose ``--help`` lists commands in declaration order."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands)


class OarenaGroup(OrderedGroup):
    """The root group: aliases, unambiguous prefixes and shared error mapping."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # Keep documented aliases exact: ``ls`` is a name in its own right,
        # while abbreviated command names are resolved only when they identify
        # a single real root command (``s`` -> ``serve``).  Click otherwise
        # treats a prefix as an unknown command, which is needlessly fussy for
        # a personal CLI with a compact command set.
        canonical = ALIASES.get(cmd_name, cmd_name)
        command = super().get_command(ctx, canonical)
        if command is not None:
            return command
        matches = [name for name in self.list_commands(ctx) if name.startswith(canonical)]
        if len(matches) == 1:
            return super().get_command(ctx, matches[0])
        if len(matches) > 1:
            choices = ", ".join(matches)
            raise click.UsageError(f"ambiguous command {cmd_name!r}; could mean: {choices}", ctx)
        return None

    def main(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return super().main(*args, **kwargs)
        except (
            ConfigError,
            BotError,
            MapError,
            StoreBatchError,
            StoreBusyError,
            StoreConfigError,
            StoreImportError,
            StoreSchemaError,
        ) as exc:
            _fatal(exc)
            raise SystemExit(2) from None
        except KeyboardInterrupt:
            err_console.print(Text("interrupted", style="yellow"))
            raise SystemExit(130) from None


@click.group(
    cls=OarenaGroup,
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
)
@click.version_option(__version__, "-V", "--version", prog_name="oarena")
def main() -> None:
    """oarena — a local bot league for the Florent Code League (fcode).

    Bots are directories containing main.py; every game runs the real fcode
    engine in its own subprocess and feeds a TrueSkill ladder.
    """


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #


@main.command()
@click.option("--force", is_flag=True, help="overwrite an existing oarena.toml")
def init(force: bool) -> None:
    """Create oarena.toml here (inheriting bots_dir/maps_dir from fcode.toml)."""
    root = Path.cwd()
    path = root / configmod.CONFIG_NAME
    detected = configmod.detect_fcode(root)

    if path.exists() and not force:
        console.print(
            Text(f"{configmod.CONFIG_NAME} already exists", style="yellow")
            + Text("  (use --force to overwrite)", style=C_MUTE)
        )
    else:
        path.write_text(configmod.default_toml(*(detected or ("bots", "maps"))), encoding="utf-8")
        console.print(Text("wrote ", style="green") + Text(str(path)))
        if detected:
            console.print(Text(f"  inherited bots_dir/maps_dir from fcode.toml: {detected[0]}, {detected[1]}", style=C_MUTE))

    cfg = configmod.from_file(path)
    configmod.ensure_dirs(cfg)
    gitignore = cfg.state_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")

    store = Store(cfg.db_path)
    try:
        League(cfg, store, EventBus(), Rater(cfg.trueskill)).sync()
        found = store.bots()
    finally:
        store.close()

    discovered_maps = mapsmod.discover(cfg.maps_dir, cfg.extra_maps_dir)
    table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    table.add_column(style=C_MUTE)
    table.add_column()
    table.add_row("bots", f"{len(found)} in {cfg.bots_dir}")
    official_count = sum(game_map.source == "official" for game_map in discovered_maps)
    extra_count = sum(game_map.source == "extra" for game_map in discovered_maps)
    table.add_row("maps", f"{official_count} official in {cfg.maps_dir}")
    table.add_row("extra maps", f"{extra_count} generated/local in {cfg.extra_maps_dir}")
    table.add_row("state", str(cfg.state_dir))
    console.print(table)
    console.print(
        Text("next: ", style=C_MUTE)
        + Text("oarena doctor", style=C_ACCENT)
        + Text("  then  ", style=C_MUTE)
        + Text("oarena arena", style=C_ACCENT)
    )


# --------------------------------------------------------------------------- #
# ladder
# --------------------------------------------------------------------------- #


@main.command(name="ladder")
@click.option("--all", "show_all", is_flag=True, help="include inactive bots")
@click.option("--top", type=click.IntRange(1), metavar="K", help="show only the top K bots")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def ladder_cmd(show_all: bool, top: int | None, as_json: bool) -> None:
    """Show the leaderboard (aliases: show, ls)."""
    with _session(quiet=as_json, sync=False) as sess:
        rows = reporting.ladder(
            sess.store,
            include_inactive=show_all,
            limit=top,
        )
        if as_json:
            _emit_json(reporting.ladder_json(rows))
            return
        if not rows:
            console.print(_empty_ladder(sess.cfg))
            return
        console.print(_ladder_table(rows))
        total = sess.store.game_count()
        if not total:
            console.print(
                Text("no games yet — run ", style=C_MUTE) + Text("oarena arena", style=C_ACCENT)
            )


@main.command(name="refresh")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def sync_cmd(as_json: bool) -> None:
    """Explicitly reconcile bots/ with the league before read-only commands."""

    with _session(quiet=as_json, sync=False) as sess:
        report = sess.league.sync()
        if as_json:
            _emit_json(report.to_json())
        else:
            _print_sync(report, quiet=False)
            if report.empty:
                console.print(Text("bot catalog already up to date", style=C_MUTE))


# --------------------------------------------------------------------------- #
# stochastic flow benchmark
# --------------------------------------------------------------------------- #


@main.command(name="flow-benchmark")
@click.argument("candidate", required=False, default="v7")
@click.option("--opponent", default="do_nothing", show_default=True)
@click.option("--maps-dir", type=click.Path(path_type=Path, file_okay=False))
@click.option(
    "--seed",
    type=click.IntRange(0, 0xFFFF_FFFF_FFFF_FFFF),
    default=1_587_658_667,
    show_default=True,
)
@click.option("-w", "--workers", type=click.IntRange(1), default=2, show_default=True)
@click.option("--timeout-s", type=click.FloatRange(min=0.001), default=600.0, show_default=True)
@click.option("--mutation-percent", default="0.1", metavar="M", show_default=True)
@click.option("--emission-percent", default="1", metavar="E", show_default=True)
@click.option("--skylight-percent", default="20", show_default=True)
@click.option(
    "--skylight-damage",
    type=click.IntRange(1, 0x7FFF_FFFF),
    default=18,
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path, file_okay=False))
def flow_benchmark_cmd(
    candidate: str,
    opponent: str,
    maps_dir: Path | None,
    seed: int,
    workers: int,
    timeout_s: float,
    mutation_percent: str,
    emission_percent: str,
    skylight_percent: str,
    skylight_damage: int,
    output: Path | None,
) -> None:
    """Run the unrated stochastic routing benchmark on every official map.

    CANDIDATE is a bot name or directory. Games use a fixed 200 ms callback
    ceiling, both seats, standard replay files, and a resumable dedicated run
    directory; they never affect the TrueSkill ladder.
    """

    cfg = configmod.load()
    if str(cfg.root) not in sys.path:
        sys.path.insert(0, str(cfg.root))
    benchmark_file = cfg.root / "problems" / "flow_benchmark" / "benchmark.py"
    if not benchmark_file.is_file():
        raise click.ClickException(
            f"this project has no flow benchmark implementation at {benchmark_file}"
        )
    try:
        from problems.flow_benchmark.benchmark import parse_args, run_benchmark

        def bot_path(value: str) -> Path:
            direct = Path(value)
            if direct.is_absolute():
                return direct
            if direct.exists():
                return direct.resolve()
            if "/" in value:
                return cfg.root / direct
            return cfg.bots_dir / value

        arguments = [
            "--candidate", str(bot_path(candidate)),
            "--opponent", str(bot_path(opponent)),
            "--maps-dir", str(maps_dir or cfg.maps_dir),
            "--seed", str(seed),
            "--workers", str(workers),
            "--timeout-s", str(timeout_s),
            "--mutation-percent", mutation_percent,
            "--emission-percent", emission_percent,
            "--skylight-percent", skylight_percent,
            "--skylight-damage", str(skylight_damage),
        ]
        if output is not None:
            arguments.extend(("--output", str(output)))
        run_benchmark(parse_args(arguments))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - present the benchmark's fail-closed reason
        raise click.ClickException(str(exc)) from exc


# --------------------------------------------------------------------------- #
# match
# --------------------------------------------------------------------------- #


def _wld(games: Iterable[Game], name: str) -> tuple[int, int, int]:
    wins = losses = draws = 0
    for game in games:
        if game.winner is None:
            continue
        side = "a" if game.a == name else "b"
        if game.winner == "draw":
            draws += 1
        elif game.winner == side:
            wins += 1
        else:
            losses += 1
    return wins, losses, draws


def _wld_markup(wins: int, losses: int, draws: int) -> str:
    return f"[{C_WIN}]{wins}W[/] [{C_LOSS}]{losses}L[/] [{C_DRAW}]{draws}D[/]"


def _drain(store: Store, cursor: int, *, tag: str | None = None) -> tuple[list[Game], int]:
    """Every game stored since ``cursor``, oldest first, plus the new cursor."""
    page_size = 500
    fresh: list[Game] = []
    while batch := store.list_games_after(cursor, limit=page_size, tag=tag):
        fresh.extend(batch)
        cursor = batch[-1].id
        if len(batch) < page_size:
            break
    return fresh, cursor


def _await_start(league: League, timeout: float = 1.0) -> None:
    """Let the run thread flip ``running`` before we start watching for the end.

    Without this a very fast start/finish race would look like "the run never
    began" and the caller would stop watching while games were still landing.
    """
    deadline = time.monotonic() + timeout
    while not league.running and time.monotonic() < deadline:
        time.sleep(0.02)


def _abort_cli_run(league: League) -> None:
    """SIGKILL CLI game workers now; :class:`Session` reaps local cleanup."""
    console.print(Text("stopping — aborting in-flight games now…", style="yellow"))
    league.force_stop()


def _map_breakdown(games: Sequence[Game], name: str) -> Table:
    per: dict[str, Record] = {}
    for game in games:
        rec = per.setdefault(game.map, Record())
        _tally(rec, "a" if game.a == name else "b", game.winner)

    table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
    table.add_column("MAP", no_wrap=True)
    table.add_column("W-L-D", justify="right")
    table.add_column("WIN%", justify="right")
    table.add_column("", justify="left", no_wrap=True)
    for map_name in sorted(per):
        rec = per[map_name]
        winrate = rec.winrate
        bar = ""
        if winrate is not None:
            filled = int(round(winrate * 10))
            bar = "█" * filled + "░" * (10 - filled)
        table.add_row(
            map_name,
            f"{rec.wins}-{rec.losses}-{rec.draws}",
            Text(_pct(winrate), style=_winrate_style(winrate) if winrate is not None else C_MUTE),
            Text(bar, style=_winrate_style(winrate) if winrate is not None else C_FAINT),
        )
    return table


def _crash_table(cfg: Config, games: Sequence[Game]) -> Table | None:
    """Group this run's failures by bot: ``(bot, count, first stderr line)``.

    Engine-level failures (timeout, killed worker) belong to the game rather than
    to either bot, so they are grouped under ``(engine)``.
    """
    buckets: dict[tuple[str, str], list[int]] = {}
    firsts: dict[tuple[str, str], str] = {}

    def record(bot: str, kind: str, detail: str, gid: int) -> None:
        key = (bot, kind)
        buckets.setdefault(key, []).append(gid)
        if key not in firsts and detail:
            firsts[key] = detail

    for game in games:
        status = game.status
        if status == "loadfail_a":
            record(game.a, "load failure", game.error, game.id)
        elif status == "loadfail_b":
            record(game.b, "load failure", game.error, game.id)
        elif status == "loadfail_both":
            for bot in dict.fromkeys((game.a, game.b)):
                record(bot, "load failure", game.error, game.id)
        elif status != "ok":
            record("(engine)", status, game.error, game.id)
        if status not in {"loadfail_a", "loadfail_b", "loadfail_both"} and (
            game.a_errors or game.b_errors
        ):
            line = _first_error_line(_log_text(cfg, game))
            if game.a_errors:
                record(game.a, "runtime error", line, game.id)
            if game.b_errors:
                record(game.b, "runtime error", line, game.id)

    if not buckets:
        return None

    table = Table(
        box=box.SIMPLE_HEAD,
        header_style=f"bold {C_LOSS}",
        title="crashes",
        title_style=f"bold {C_LOSS}",
        title_justify="left",
        pad_edge=False,
    )
    table.add_column("BOT", no_wrap=True)
    table.add_column("KIND", no_wrap=True)
    table.add_column("N", justify="right")
    table.add_column("FIRST STDERR LINE")
    table.add_column("GAME", justify="right", style=C_MUTE)
    for (bot, kind), gids in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        table.add_row(
            Text(bot, style="bold"),
            Text(kind, style=C_LOSS),
            str(len(gids)),
            Text(firsts.get((bot, kind), "—")[:88], style=C_MUTE),
            f"#{gids[0]}",
        )
    return table


@main.command()
@click.argument("a")
@click.argument("b")
@click.option("-m", "--map", "map_specs", multiple=True, help="map to play (repeatable)")
@click.option("-n", "--repeat", default=1, type=click.IntRange(1), show_default=True, help="rounds per map")
@click.option("--mirror/--no-mirror", default=None, help="also play every pairing with sides swapped")
@click.option("--unrated", is_flag=True, help="play without touching the ladder")
@click.option("--seed", type=int, default=None, help="force a fixed base seed")
@click.option("-w", "--workers", type=click.IntRange(1), default=None, help="parallel games")
@click.option(
    "--tag",
    default=None,
    help="reserve an immutable batch tag for auditable games (cannot be reused)",
)
@click.option("--watch", "watch_after", is_flag=True, help="open the last replay afterwards")
@click.option("-q", "--quiet", is_flag=True, help="only print the final summary")
def match(
    a: str,
    b: str,
    map_specs: tuple[str, ...],
    repeat: int,
    mirror: bool | None,
    unrated: bool,
    seed: int | None,
    workers: int | None,
    tag: str | None,
    watch_after: bool,
    quiet: bool,
) -> None:
    """Play a fixed set of games between two bots."""
    with _session(workers=workers, seed=seed, quiet=quiet, sync=False) as sess:
        cfg, store, league = sess.cfg, sess.store, sess.league
        a_name = league.resolve(a).name
        b_name = league.resolve(b).name
        jobs = league.plan_match(
            a_name,
            b_name,
            maps=list(map_specs) or None,
            repeat=repeat,
            mirror=mirror,
            rated=not unrated,
            tag=tag or "match",
        )
        map_names = sorted({job.map for job in jobs})
        mirrored = cfg.mirror if mirror is None else mirror
        rated = not unrated and a_name != b_name

        if not quiet:
            console.print(
                Text(f"{a_name} vs {b_name}", style="bold")
                + Text(
                    f"   {len(jobs)} games · {len(map_names)} maps × {repeat} round(s)"
                    f" × {'2 sides' if mirrored else '1 side'} · {cfg.n_workers} workers"
                    f" · {'rated' if rated else 'unrated'}",
                    style=C_MUTE,
                )
            )
            if a_name == b_name:
                console.print(Text("  self-match: unrated by definition", style=C_MUTE))

        cursor = max((g.id for g in store.list_games(limit=1)), default=0)
        played: list[Game] = []
        try:
            league.start_match(
                jobs, label=f"{a_name} vs {b_name}", workers=workers, batch_tag=tag
            )
            _await_start(league)
            if quiet:
                while not (league.wait(timeout=0.25) or not league.running):
                    pass
                played, cursor = _drain(store, cursor, tag=tag)
            else:
                played, cursor = _match_progress(
                    sess, jobs, a_name, b_name, cursor, tag=tag
                )
        except KeyboardInterrupt:
            _abort_cli_run(league)
            raise SystemExit(130) from None

        fresh, cursor = _drain(store, cursor, tag=tag)
        played.extend(fresh)
        _match_summary(sess, played, a_name, quiet=quiet)

        if watch_after and played:
            _open_replay(cfg, played[-1].id)


def _match_progress(
    sess: Session,
    jobs: Sequence[Any],
    a_name: str,
    b_name: str,
    cursor: int,
    *,
    tag: str | None = None,
) -> tuple[list[Game], int]:
    """Run the progress bar until the league's run thread finishes."""
    played: list[Game] = []
    progress = Progress(
        SpinnerColumn(style=C_ACCENT),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=32, complete_style=C_ACCENT, finished_style=C_WIN),
        MofNCompleteColumn(),
        TextColumn("{task.fields[wld]}"),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        task = progress.add_task(
            f"{escape(a_name)} vs {escape(b_name)}", total=len(jobs), wld=_wld_markup(0, 0, 0)
        )
        while True:
            finished = sess.league.wait(timeout=0.2) or not sess.league.running
            fresh, cursor = _drain(sess.store, cursor, tag=tag)
            if fresh:
                played.extend(fresh)
                progress.update(
                    task, completed=len(played), wld=_wld_markup(*_wld(played, a_name))
                )
            if finished:
                break
        progress.update(task, completed=max(len(played), progress.tasks[0].completed))
    return played, cursor


def _match_summary(sess: Session, played: Sequence[Game], a_name: str, *, quiet: bool) -> None:
    if not played:
        console.print(Text("no games were played", style="yellow"))
        return
    wins, losses, draws = _wld(played, a_name)
    console.print()
    console.print(
        Text(f"{a_name}: ", style="bold")
        + Text(f"{wins}W", style=C_WIN)
        + Text(" · ")
        + Text(f"{losses}L", style=C_LOSS)
        + Text(" · ")
        + Text(f"{draws}D", style=C_DRAW)
        + Text(f"   over {len(played)} games", style=C_MUTE)
    )
    if not quiet:
        console.print(_map_breakdown(played, a_name))
    crashes = _crash_table(sess.cfg, played)
    if crashes is not None:
        console.print(crashes)
        console.print(Text("  inspect one with:  oarena log <id>", style=C_MUTE))


# --------------------------------------------------------------------------- #
# arena
# --------------------------------------------------------------------------- #


@dataclass
class _ArenaStats:
    """Persisted outcomes observed during one arena invocation."""

    games: int = 0
    rated: int = 0
    ok: int = 0
    decisive: int = 0
    draws: int = 0
    failed: int = 0
    bot_errors: int = 0
    ok_turns: int = 0
    ok_duration_ms: int = 0

    def add(self, games: Iterable[Game]) -> None:
        for game in games:
            self.games += 1
            self.rated += int(bool(game.rated))
            errors = max(0, game.a_errors) + max(0, game.b_errors)
            self.bot_errors += errors
            if game.status != "ok" or errors:
                self.failed += 1
                continue
            self.ok += 1
            self.ok_turns += max(0, game.turns)
            self.ok_duration_ms += max(0, game.duration_ms)
            if game.winner == "draw":
                self.draws += 1
            elif game.winner in ("a", "b"):
                self.decisive += 1

    @property
    def unresolved(self) -> int:
        return max(0, self.games - self.decisive - self.draws - self.failed)

    @property
    def average_turns(self) -> float:
        return self.ok_turns / self.ok if self.ok else 0.0

    @property
    def average_duration_ms(self) -> int:
        return round(self.ok_duration_ms / self.ok) if self.ok else 0


def _live_lines(status: dict[str, Any], limit: int = 6) -> list[Text]:
    """One line per in-flight game. ``since`` and ``now`` are both monotonic."""
    now = float(status.get("now") or time.monotonic())
    lines: list[Text] = []
    live = status.get("live") or []
    for entry in live[:limit]:
        since = entry.get("since")
        age = ""
        if isinstance(since, (int, float)):
            age = f"  {max(0.0, now - float(since)):.1f}s"
        lines.append(
            Text("  ▸ ", style=C_ACCENT)
            + Text(f"{entry.get('a', '?')} vs {entry.get('b', '?')}")
            + Text(f"  on {entry.get('map', '?')}", style=C_MUTE)
            + Text(age, style=C_FAINT)
        )
    if len(live) > limit:
        lines.append(Text(f"  … +{len(live) - limit} more in flight", style=C_FAINT))
    return lines


def _arena_results_line(stats: _ArenaStats) -> Text:
    line = Text("results", style="bold")
    if not stats.games:
        line.append("  ·  waiting for the first completed game", style=C_MUTE)
        return line

    line.append(f"  ·  {stats.decisive} decisive", style=C_MUTE)
    line.append(f"  ·  {stats.draws} draw{'s' if stats.draws != 1 else ''}", style=C_DRAW)
    if stats.unresolved:
        line.append(f"  ·  {stats.unresolved} unresolved", style="yellow")
    line.append(
        f"  ·  {stats.failed} failed",
        style=C_LOSS if stats.failed else C_MUTE,
    )
    line.append(f"  ·  {stats.rated} rated", style=C_MUTE)
    line.append(
        f"  ·  {stats.bot_errors} bot error{'s' if stats.bot_errors != 1 else ''}",
        style=C_LOSS if stats.bot_errors else C_MUTE,
    )
    return line


def _arena_average_line(stats: _ArenaStats) -> Text | None:
    if not stats.ok:
        return None
    return Text("average", style="bold") + Text(
        f"  ·  {stats.average_turns:.0f} turns"
        f"  ·  {_dur(stats.average_duration_ms)}/game",
        style=C_MUTE,
    )


def _arena_footer(
    status: dict[str, Any],
    stats: _ArenaStats,
    elapsed: float,
) -> RenderableType:
    mode = status.get("mode") or "arena"
    bits = Text()
    bits.append(f"{mode}", style=f"bold {C_ACCENT}")
    if status.get("stopping"):
        bits.append("  stopping", style="yellow")
    bits.append(f"  ·  {status.get('workers', 0)} workers", style=C_MUTE)
    bits.append(f"  ·  {stats.games} games", style=C_MUTE)
    total = status.get("total")
    if total:
        bits.append(f"/{total}", style=C_MUTE)
    bits.append(f"  ·  {float(status.get('rate') or 0.0):.1f}/min", style=C_MUTE)
    bits.append(f"  ·  {status.get('in_flight', 0)} in flight", style=C_MUTE)
    bits.append(f"  ·  {int(elapsed) // 60}m{int(elapsed) % 60:02d}", style=C_MUTE)
    lines = _live_lines(status)
    idle = status.get("idle_reason")
    if idle and not status.get("in_flight"):
        # The arena deliberately waits rather than exiting — a bot can appear at
        # any moment — but a bare ladder with nothing happening reads as a hang.
        lines = [Text(f"  waiting — {idle}", style="yellow"), *lines]
    summary: list[RenderableType] = [_arena_results_line(stats)]
    average = _arena_average_line(stats)
    if average is not None:
        summary.append(average)
    return Group(bits, *summary, *lines)


def _arena_snapshot_due(
    *,
    now: float,
    last_at: float,
    games: int,
    last_games: int,
    interval: float = ARENA_LADDER_INTERVAL_S,
) -> bool:
    """Whether enough time and new evidence exist for another ladder snapshot."""
    return games > last_games and now - last_at >= interval


def _arena_ladder_snapshot(
    store: Store,
    *,
    games: int,
    elapsed: float,
    final: bool = False,
) -> RenderableType:
    if final:
        title = f"top {ARENA_LADDER_LIMIT} · final · {games} games"
    elif games == 0:
        title = f"top {ARENA_LADDER_LIMIT} · opening"
    else:
        title = (
            f"top {ARENA_LADDER_LIMIT} · {_dur(int(elapsed * 1000))}"
            f" · {games} games"
        )
    return _ladder_view(store, limit=ARENA_LADDER_LIMIT, title=title)


def _run_arena(
    kind: str,
    *,
    top: int,
    target: str | None,
    rated: bool,
    workers: int | None,
    games: int,
    tag: str | None,
) -> None:
    """Shared implementation of ``arena`` and ``vs``."""
    with _session(workers=workers, sync=False) as sess:
        cfg, store, league = sess.cfg, sess.store, sess.league
        if target is not None:
            target = league.resolve(target).name

        cursor = max((game.id for game in store.list_games(limit=1)), default=0)
        stats = _ArenaStats()
        started = time.monotonic()
        try:
            league.start_arena(
                kind,
                top=top,
                target=target,
                rated=rated,
                limit=games,
                workers=workers,
                batch_tag=tag,
            )
            opening_ladder = _arena_ladder_snapshot(
                store,
                games=stats.games,
                elapsed=0.0,
            )
            _await_start(league)

            label = kind if target is None else f"vs {target}"
            console.print(
                Text(f"arena · {label}", style=f"bold {C_ACCENT}")
                + Text(
                    f"   {cfg.n_workers} workers · {'rated' if rated else 'unrated'}"
                    + (f" · stopping after {games} games" if games else "")
                    + "   (Ctrl-C to stop)",
                    style=C_MUTE,
                )
            )
            console.print(opening_ladder)
            last_ladder_at = time.monotonic()
            last_ladder_games = stats.games
            with Live(console=console, refresh_per_second=2, transient=True) as live:
                while league.running:
                    fresh, cursor = _drain(store, cursor, tag=tag)
                    stats.add(fresh)
                    now = time.monotonic()
                    status = league.status
                    live.update(_arena_footer(status, stats, now - started))
                    if _arena_snapshot_due(
                        now=now,
                        last_at=last_ladder_at,
                        games=stats.games,
                        last_games=last_ladder_games,
                    ):
                        live.console.print(
                            _arena_ladder_snapshot(
                                store,
                                games=stats.games,
                                elapsed=now - started,
                            )
                        )
                        last_ladder_at = now
                        last_ladder_games = stats.games
                    time.sleep(ARENA_LIVE_INTERVAL_S)
        except KeyboardInterrupt:
            _abort_cli_run(league)
            raise SystemExit(130) from None

        fresh, cursor = _drain(store, cursor, tag=tag)
        stats.add(fresh)
        elapsed = max(time.monotonic() - started, 1e-6)
        console.print(
            _arena_ladder_snapshot(
                store,
                games=stats.games,
                elapsed=elapsed,
                final=True,
            )
        )
        console.print(_arena_footer(league.status, stats, elapsed))


def _ladder_view(
    store: Store,
    *,
    limit: int | None = None,
    title: str | None = None,
) -> RenderableType:
    rows = reporting.ladder(store, include_inactive=False, limit=limit)
    if not rows:
        return Text("waiting for bots…", style=C_MUTE)
    return _ladder_table(rows, title=title, caption=False)


@main.command()
@click.option("--top", type=click.IntRange(0), default=0, help="only match the top K bots")
@click.option("--vs", "target", default=None, help="focus every game on this bot")
@click.option("--rr", is_flag=True, help="round-robin: always play the least-played pair")
@click.option("-w", "--workers", type=click.IntRange(1), default=None, help="parallel games")
@click.option("--unrated", is_flag=True, help="play without touching the ladder")
@click.option("-n", "--games", type=click.IntRange(0), default=0, help="stop after N games")
@click.option(
    "--tag",
    default=None,
    help="reserve an immutable batch tag for auditable games (cannot be reused)",
)
def arena(
    top: int,
    target: str | None,
    rr: bool,
    workers: int | None,
    unrated: bool,
    games: int,
    tag: str | None,
) -> None:
    """Run games continuously with live stats and periodic top-10 snapshots."""
    chosen = [name for name, on in (("top", top), ("vs", target), ("rr", rr)) if on]
    if len(chosen) > 1:
        raise click.UsageError("--top, --vs and --rr are mutually exclusive")
    kind = chosen[0] if chosen else "ladder"
    _run_arena(
        kind,
        top=top,
        target=target,
        rated=not unrated,
        workers=workers,
        games=games,
        tag=tag,
    )


@main.command(name="vs")
@click.argument("bot")
@click.option("-w", "--workers", type=click.IntRange(1), default=None, help="parallel games")
@click.option("--unrated", is_flag=True, help="play without touching the ladder")
@click.option("-n", "--games", type=click.IntRange(0), default=0, help="stop after N games")
@click.option(
    "--tag",
    default=None,
    help="reserve an immutable batch tag for auditable games (cannot be reused)",
)
def vs_cmd(
    bot: str, workers: int | None, unrated: bool, games: int, tag: str | None
) -> None:
    """Run an arena focused on one bot (alias for `arena --vs BOT`)."""
    _run_arena(
        "vs",
        top=0,
        target=bot,
        rated=not unrated,
        workers=workers,
        games=games,
        tag=tag,
    )


# --------------------------------------------------------------------------- #
# bots
# --------------------------------------------------------------------------- #


@main.command(name="bots")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def bots_cmd(as_json: bool) -> None:
    """List every known bot with its paths, hash and state."""
    with _session(quiet=as_json, sync=False) as sess:
        rows = sess.store.bots()
        if as_json:
            _emit_json([reporting.bot_json(b) for b in rows])
            return
        if not rows:
            console.print(_empty_ladder(sess.cfg))
            return

        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
        table.add_column("BOT", no_wrap=True)
        table.add_column("STATE", no_wrap=True)
        table.add_column("HASH", style=C_MUTE, no_wrap=True)
        table.add_column("DIR")
        table.add_column("NOTE", style=C_MUTE)
        for entry in rows:
            if entry.broken:
                state = Text("broken", style=f"bold {C_LOSS}")
            elif not entry.active:
                state = Text("off", style=C_MUTE)
            else:
                state = Text("live", style=C_WIN)
            name = Text()
            name.append(entry.name, style="dim" if not entry.active else "")
            table.add_row(
                name,
                state,
                entry.src_hash[:10] or "—",
                _relative(sess.cfg.root, entry.dir),
                (entry.broken_reason or entry.note)[:60],
            )
        console.print(table)


def _relative(root: Path, path: str | Path) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


@main.group(cls=OrderedGroup)
def bot() -> None:
    """Inspect and manage a single bot."""


@bot.command(name="info")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def bot_info(name: str, as_json: bool) -> None:
    """Show one bot's record, per-map and per-opponent splits, and crashes."""
    with _session(quiet=as_json, sync=False) as sess:
        store, cfg = sess.store, sess.cfg
        row = store.get_bot(name)
        if row is None:
            raise BotError(f"unknown bot {name!r}; run `oarena refresh` to discover sources")
        if as_json:
            _emit_json(reporting.bot_detail(store, name))
            return
        record = store.record(name)
        err_games, err_total = store.error_count(name)

        header = Text()
        header.append(row.name, style=f"bold {C_ACCENT}")
        header.append(f"   μ {row.mu:.2f}", style="bold")
        header.append(f"   LCB95 {row.rating.lcb95:.2f}  σ {row.sigma:.2f}", style=C_MUTE)
        if row.broken:
            header.append("   BROKEN", style=f"bold {C_LOSS}")
        if not row.active:
            header.append("   inactive", style=C_MUTE)
        console.print(header)

        meta = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        meta.add_column(style=C_MUTE, no_wrap=True)
        meta.add_column()
        meta.add_row("dir", str(row.dir))
        meta.add_row("hash", row.src_hash[:16] or "—")
        meta.add_row("record", f"{record.wins}-{record.losses}-{record.draws}  ({_pct(record.winrate)} of {record.games})")
        meta.add_row(
            "errors",
            f"{err_total} attributed errors in {err_games} games" if err_total else "none",
        )
        if row.broken_reason:
            meta.add_row("broken", Text(row.broken_reason, style=C_LOSS))
        if row.note:
            meta.add_row("note", row.note)
        console.print(meta)

        h2h = store.head_to_head(name)
        if h2h:
            table = Table(
                box=box.SIMPLE_HEAD,
                header_style=f"bold {C_MUTE}",
                title="opponents",
                title_style="bold",
                title_justify="left",
                pad_edge=False,
            )
            table.add_column("OPPONENT", no_wrap=True)
            table.add_column("W-L-D", justify="right")
            table.add_column("WIN%", justify="right")
            for opponent, rec in sorted(h2h.items(), key=lambda kv: -(kv[1].winrate or 0.0)):
                table.add_row(
                    opponent,
                    f"{rec.wins}-{rec.losses}-{rec.draws}",
                    Text(_pct(rec.winrate), style=_winrate_style(rec.winrate or 0.5)),
                )
            console.print(table)

        per_map = store.map_record(name)
        if per_map:
            table = Table(
                box=box.SIMPLE_HEAD,
                header_style=f"bold {C_MUTE}",
                title="maps",
                title_style="bold",
                title_justify="left",
                pad_edge=False,
            )
            table.add_column("MAP", no_wrap=True)
            table.add_column("W-L-D", justify="right")
            table.add_column("WIN%", justify="right")
            for map_name, rec in sorted(per_map.items()):
                table.add_row(
                    map_name,
                    f"{rec.wins}-{rec.losses}-{rec.draws}",
                    Text(_pct(rec.winrate), style=_winrate_style(rec.winrate or 0.5)),
                )
            console.print(table)

        crashes = store.recent_crashes(name, limit=5)
        if crashes:
            table = Table(
                box=box.SIMPLE_HEAD,
                header_style=f"bold {C_LOSS}",
                title="recent crashes",
                title_style=f"bold {C_LOSS}",
                title_justify="left",
                pad_edge=False,
            )
            table.add_column("GAME", justify="right", style=C_MUTE)
            table.add_column("WHEN", no_wrap=True, style=C_MUTE)
            table.add_column("VS", no_wrap=True)
            table.add_column("WHAT")
            for game in crashes:
                other = game.b if game.a == name else game.a
                detail = game.error or _first_error_line(_log_text(cfg, game))
                table.add_row(f"#{game.id}", _when(game.ts), other, Text(detail[:80], style=C_MUTE))
            console.print(table)

        versions = store.versions(name, limit=5)
        if len(versions) > 1:
            console.print(Text("versions", style="bold"))
            for _vid, src_hash, ts in versions:
                console.print(Text(f"  {_when(ts)}  {src_hash[:12]}", style=C_MUTE))


@bot.command(name="hash")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def bot_hash(name: str, as_json: bool) -> None:
    """Hash NAME's Python sources and record a changed version, if any.

    Source hashes are normally checked by every oarena command. This is the
    explicit, quick command for checking one bot after an edit; a changed hash
    is recorded as a version marker and its rating uncertainty is re-inflated.
    """
    with _session(quiet=as_json, sync=False) as sess:
        try:
            source = botsmod.resolve(sess.cfg.bots_dir, name)
        except BotError:
            # Give sync a chance to register a newly-created bot before using
            # the standard, helpful unknown-name error.
            sess.league.sync()
            source = botsmod.resolve(sess.cfg.bots_dir, name)

        before = sess.store.get_bot(source.name)
        report = sess.league.sync()
        row = sess.store.get_bot(source.name)
        if row is None:  # pragma: no cover - sync registered the source above
            raise BotError(f"unknown bot {source.name!r}")

        changed = source.name in report.changed
        payload = {
            "name": source.name,
            "hash": row.src_hash,
            "changed": changed,
            "registered": source.name in report.added,
            "versions": len(sess.store.versions(source.name)),
        }
        if as_json:
            _emit_json(payload)
            return

        console.print(Text(source.name, style=f"bold {C_ACCENT}"))
        console.print(Text(f"sha256  {row.src_hash}"))
        if payload["registered"]:
            state = "registered as a new bot"
        elif changed:
            state = "changed — version recorded; rating uncertainty re-inflated"
        elif before is not None:
            state = "unchanged — matches the tracked source version"
        else:  # pragma: no cover - covered by the registered branch today
            state = "tracked"
        console.print(Text(state, style=C_MUTE))
        console.print(Text(f"versions  {payload['versions']}", style=C_MUTE))


@bot.command(name="enable")
@click.argument("name")
def bot_enable(name: str) -> None:
    """Let a bot play again."""
    _set_active(name, True)


@bot.command(name="disable")
@click.argument("name")
def bot_disable(name: str) -> None:
    """Keep a bot's history but stop matching it."""
    _set_active(name, False)


def _set_active(name: str, active: bool) -> None:
    with _session(quiet=True) as sess:
        if sess.store.get_bot(name) is None:
            raise BotError(f"unknown bot {name!r}")
        sess.store.set_active(name, active)
        console.print(
            Text(name, style="bold") + Text(" enabled" if active else " disabled", style=C_MUTE)
        )


@bot.command(name="rm")
@click.argument("name")
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def bot_rm(name: str, yes: bool) -> None:
    """Delete a bot and every game it played."""
    with _session(quiet=True, sync=False) as sess:
        _require_owned_state(sess.cfg, "bot deletion")
        sess.league.sync()
        row = sess.store.get_bot(name)
        if row is None:
            raise BotError(f"unknown bot {name!r}")
        record = sess.store.record(name)
        if not yes:
            click.confirm(
                f"delete {name!r} and its {record.games} games?", abort=True, default=False
            )
        sess.store.delete_bot(name)
        console.print(Text(f"deleted {name}", style="yellow"))

        directory = Path(row.dir)
        if directory.is_dir():
            console.print(
                Text(f"note: {directory} is untouched and will be re-registered on the next sync — ", style=C_MUTE)
                + Text("oarena bot disable", style=C_ACCENT)
                + Text(" keeps it out of the ladder instead.", style=C_MUTE)
            )


def _under(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().is_relative_to(parent.resolve())
    except (OSError, ValueError):
        return False


@bot.command(name="note")
@click.argument("name")
@click.argument("text", nargs=-1)
def bot_note(name: str, text: tuple[str, ...]) -> None:
    """Attach a note to a bot (no text clears it)."""
    with _session(quiet=True) as sess:
        if sess.store.get_bot(name) is None:
            raise BotError(f"unknown bot {name!r}")
        note = " ".join(text).strip()
        sess.store.set_note(name, note)
        console.print(Text(name, style="bold") + Text(f"  note: {note or '(cleared)'}", style=C_MUTE))


# --------------------------------------------------------------------------- #
# maps
# --------------------------------------------------------------------------- #


@main.command(name="maps")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def maps_cmd(as_json: bool) -> None:
    """List the maps oarena can play, with how often each has been used."""
    with _session(quiet=as_json, sync=False) as sess:
        found = mapsmod.discover(sess.cfg.maps_dir, sess.cfg.extra_maps_dir)
        counts = sess.store.map_play_counts()
        if as_json:
            _emit_json(reporting.maps_json(sess.store, found))
            return
        if not found:
            console.print(
                Panel(
                    Text(
                        f"no *.map26 files in {sess.cfg.maps_dir} or "
                        f"{sess.cfg.extra_maps_dir}",
                        style="yellow",
                    ),
                    border_style=C_MUTE,
                )
            )
            return

        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
        table.add_column("MAP", no_wrap=True)
        table.add_column("SOURCE", no_wrap=True)
        table.add_column("SIZE", justify="right")
        table.add_column("AREA", justify="right")
        table.add_column("WALLS", justify="right")
        table.add_column("ORE", justify="right")
        table.add_column("SPAWNS", justify="right")
        table.add_column("GAMES", justify="right")
        for game_map in found:
            ok = game_map.width > 0
            table.add_row(
                Text(game_map.name, style="" if ok else C_LOSS),
                game_map.source,
                f"{game_map.width}×{game_map.height}" if ok else Text("unreadable", style=C_LOSS),
                str(game_map.area),
                str(game_map.walls),
                Text(str(game_map.ore), style=C_ACCENT),
                str(len(game_map.spawns)),
                str(counts.get(game_map.name, 0)),
            )
        console.print(table)


# --------------------------------------------------------------------------- #
# games / game / log
# --------------------------------------------------------------------------- #


@main.command(name="batch")
@click.argument("tag")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def batch_cmd(tag: str, as_json: bool) -> None:
    """Show immutable batch metadata and its stored-game count."""

    with _session(quiet=True, sync=False) as sess:
        row = sess.store.batch(tag)
        if row is None:
            raise click.ClickException(f"no batch tagged {tag!r}")
        payload = {**row, "stored_games": sess.store.game_count(tag=tag)}
        if as_json:
            _emit_json(payload)
            return
        table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        table.add_column(style=C_MUTE)
        table.add_column()
        for key in (
            "tag",
            "mode",
            "status",
            "requested_games",
            "played_games",
            "stored_games",
            "started",
            "finished",
        ):
            table.add_row(key.replace("_", " "), str(payload.get(key, "—")))
        console.print(table)


@main.command(name="games")
@click.option("-n", "--limit", default=20, type=click.IntRange(1), show_default=True)
@click.option("--bot", "bot_name", default=None, help="only games this bot played")
@click.option("--map", "map_name", default=None, help="only games on this map")
@click.option("--tag", default=None, help="only games in this immutable batch tag")
@click.option("--failed", is_flag=True, help="only games that did not finish cleanly")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def games_cmd(
    limit: int,
    bot_name: str | None,
    map_name: str | None,
    tag: str | None,
    failed: bool,
    as_json: bool,
) -> None:
    """List recent games, newest first."""
    with _session(quiet=as_json, sync=False) as sess:
        rows = sess.store.list_games(
            limit=limit,
            bot=bot_name,
            map=map_name,
            tag=tag,
            status="failed" if failed else None,
        )
        if as_json:
            _emit_json([reporting.game_json(g) for g in rows])
            return
        if not rows:
            console.print(Text("no games match that filter", style=C_MUTE))
            return

        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
        table.add_column("ID", justify="right", style=C_MUTE)
        table.add_column("WHEN", no_wrap=True, style=C_MUTE)
        table.add_column("MATCHUP", no_wrap=True)
        table.add_column("MAP", no_wrap=True, style=C_MUTE)
        table.add_column("RESULT")
        table.add_column("TURNS", justify="right")
        table.add_column("TIME", justify="right", style=C_MUTE)
        table.add_column("ERR", justify="right")
        for game in rows:
            errors = game.a_errors + game.b_errors
            table.add_row(
                str(game.id),
                _when(game.ts),
                _matchup(game),
                game.map,
                _result_cell(game),
                str(game.turns or "—"),
                _dur(game.duration_ms),
                Text(str(errors), style=C_LOSS) if errors else Text("·", style=C_FAINT),
            )
        console.print(table)
        console.print(Text("detail: oarena game <id>   ·   stderr: oarena log <id>", style=C_FAINT))


@main.command(name="game")
@click.argument("gid", type=int, metavar="ID")
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def game_cmd(gid: int, as_json: bool) -> None:
    """Show one game in full."""
    with _session(quiet=True, sync=False) as sess:
        game = sess.store.get_game(gid)
        if game is None:
            raise click.ClickException(f"no game #{gid}")
        if as_json:
            _emit_json(reporting.game_json(game))
            return

        console.print(
            Text(f"game #{game.id}  ", style=f"bold {C_ACCENT}")
            + _matchup(game)
            + Text(f"   {game.map}  seed {game.seed}  {game.tag or 'game'}", style=C_MUTE)
        )
        console.print(
            Text("  ")
            + _result_cell(game)
            + Text(
                f"   {game.turns} turns · {_dur(game.duration_ms)} · "
                f"{'rated' if game.rated else 'unrated'} · {_when(game.ts)}",
                style=C_MUTE,
            )
        )
        if game.resign_message:
            console.print(Text(f"  resign: {game.resign_message}", style="yellow"))

        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
        table.add_column("", style=C_MUTE, no_wrap=True)
        table.add_column(game.a, justify="right")
        table.add_column(game.b, justify="right")
        table.add_row("titanium", str(game.a_titanium), str(game.b_titanium))
        table.add_row("mined", str(game.a_mined), str(game.b_mined))
        table.add_row("units", str(game.a_units), str(game.b_units))
        table.add_row("buildings", str(game.a_buildings), str(game.b_buildings))
        table.add_row(
            "errors",
            Text(str(game.a_errors), style=C_LOSS if game.a_errors else C_FAINT),
            Text(str(game.b_errors), style=C_LOSS if game.b_errors else C_FAINT),
        )
        if game.a_mu_after is not None and game.b_mu_after is not None:
            table.add_row(
                "LCB95",
                _delta_cell(game.a_mu_before, game.a_sigma_before, game.a_mu_after, game.a_sigma_after),
                _delta_cell(game.b_mu_before, game.b_sigma_before, game.b_mu_after, game.b_sigma_after),
            )
        console.print(table)

        replay = sess.cfg.replay_dir / game.replay if game.replay else None
        console.print(
            Text("  replay: ", style=C_MUTE)
            + Text(str(replay) if replay and replay.exists() else "— (pruned)", style=C_FAINT)
        )
        text = _log_text(sess.cfg, game)
        if text:
            tail = "\n".join(text.strip().splitlines()[-12:])
            console.print(
                Panel(
                    Text(tail, style=C_MUTE),
                    title=f"stderr tail · oarena log {game.id}",
                    title_align="left",
                    border_style=C_FAINT,
                )
            )


def _delta_cell(
    mu_before: float | None, sigma_before: float | None, mu_after: float | None, sigma_after: float | None
) -> Text:
    if mu_before is None or sigma_before is None or mu_after is None or sigma_after is None:
        return Text("—", style=C_FAINT)
    before = mu_before - CI * sigma_before
    after = mu_after - CI * sigma_after
    delta = after - before
    style = C_WIN if delta > 0 else (C_LOSS if delta < 0 else C_DRAW)
    return Text(f"{before:.2f} → {after:.2f} ") + Text(f"({delta:+.2f})", style=style)


@main.command(name="log")
@click.argument("gid", type=int, metavar="ID")
def log_cmd(gid: int) -> None:
    """Print a game's captured stdout/stderr."""
    with _session(quiet=True, sync=False) as sess:
        game = sess.store.get_game(gid)
        if game is None:
            raise click.ClickException(f"no game #{gid}")
        text = _log_text(sess.cfg, game)
        if not text:
            console.print(Text(f"game #{gid} produced no log output", style=C_MUTE))
            return
        click.echo(text.rstrip("\n"))


# --------------------------------------------------------------------------- #
# watch
# --------------------------------------------------------------------------- #


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _open_replay(cfg: Config, gid: int, host: str = "127.0.0.1") -> None:
    """Serve the dashboard on a spare port and deep-link the browser to a game.

    The bundled visualiser fetches its replay over HTTP, so a server has to be
    up for the duration; this one lives as long as the command does.
    """
    from . import server as servermod

    port = _free_port(host)
    thread = threading.Thread(
        target=servermod.serve,
        args=(cfg,),
        kwargs={"host": host, "port": port, "open_browser": False},
        daemon=True,
        name="oarena-watch",
    )
    thread.start()
    url = f"http://{host}:{port}/#/games/{gid}"
    time.sleep(0.5)
    opened = webbrowser.open(url)
    console.print(
        Text("watching game ", style=C_MUTE)
        + Text(f"#{gid}", style="bold")
        + Text(f"  {url}", style=C_ACCENT)
        + Text("" if opened else "  (open it yourself — no browser found)", style="yellow")
    )
    console.print(Text("Ctrl-C to stop the viewer", style=C_FAINT))
    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print(Text("closed", style=C_MUTE))


@main.command()
@click.argument("gid", type=int, metavar="ID", required=False)
def watch(gid: int | None) -> None:
    """Open a replay in the bundled fcode visualiser (default: the newest game)."""
    with _session(quiet=True, sync=False) as sess:
        if gid is None:
            recent = sess.store.list_games(limit=1)
            if not recent:
                raise click.ClickException("no games to watch yet")
            gid = recent[0].id
        game = sess.store.get_game(gid)
        if game is None:
            raise click.ClickException(f"no game #{gid}")
        if not game.replay or not (sess.cfg.replay_dir / game.replay).exists():
            raise click.ClickException(
                f"game #{gid} has no replay on disk (failed games keep none, and old ones are pruned)"
            )
        cfg = sess.cfg
    _open_replay(cfg, gid)


# --------------------------------------------------------------------------- #
# matrix
# --------------------------------------------------------------------------- #


@main.command(name="matrix")
@click.option("--min", "min_games", type=click.IntRange(0), default=0, help="dim cells thinner than N games")
@click.option("--all", "show_all", is_flag=True, help="include inactive bots")
def matrix_cmd(min_games: int, show_all: bool) -> None:
    """Print the head-to-head crosstable in ladder order."""
    with _session(sync=False) as sess:
        rows = reporting.ladder(sess.store, include_inactive=show_all)
        if len(rows) < 2:
            console.print(Text("need at least two bots for a crosstable", style=C_MUTE))
            return
        names = [r.name for r in rows]
        cells = sess.store.matrix(names)

        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
        table.add_column("#", justify="right", style=C_MUTE)
        table.add_column("BOT", no_wrap=True)
        for index in range(1, len(names) + 1):
            table.add_column(str(index), justify="right", min_width=3)
        table.add_column("TOTAL", justify="right")

        for i, row in enumerate(rows):
            cells_out: list[Text] = []
            wins = losses = draws = played = 0
            for j, other in enumerate(names):
                if i == j:
                    cells_out.append(Text("╱", style=C_FAINT))
                    continue
                rec = cells.get(row.name, {}).get(other, Record())
                wins += rec.wins
                losses += rec.losses
                draws += rec.draws
                played += rec.games
                winrate = rec.winrate
                if winrate is None:
                    cells_out.append(Text("·", style=C_FAINT))
                elif rec.games < min_games:
                    cells_out.append(Text(f"{winrate * 100:.0f}", style=C_FAINT))
                else:
                    cells_out.append(Text(f"{winrate * 100:.0f}", style=_winrate_style(winrate)))
            total = Record(wins=wins, losses=losses, draws=draws, games=played)
            table.add_row(
                str(i + 1),
                _bot_cell(row),
                *cells_out,
                Text(
                    f"{_pct(total.winrate)} ({played})",
                    style=_winrate_style(total.winrate) if total.winrate is not None else C_MUTE,
                ),
            )
        console.print(table)
        console.print(
            Text("cell = row bot's win% against the column bot", style=C_FAINT)
            + Text(f"   ·   dim = fewer than {min_games} games" if min_games else "", style=C_FAINT)
        )


# --------------------------------------------------------------------------- #
# serve
# --------------------------------------------------------------------------- #


@main.command()
@click.option("-p", "--port", default=7878, show_default=True, type=int)
@click.option("-H", "--host", default="127.0.0.1", show_default=True)
@click.option("--open/--no-open", "open_browser", default=True, help="open a browser on start")
@click.option("-w", "--workers", type=click.IntRange(1), default=None, help="parallel games")
@click.option(
    "--reload/--no-reload",
    "reload_enabled",
    default=False,
    help="restart safely when oarena, bots, maps, config or fcode changes",
)
@click.option(
    "--strict-port",
    is_flag=True,
    help="fail instead of falling back to a random port when the requested port is busy",
)
def serve(
    port: int,
    host: str,
    open_browser: bool,
    workers: int | None,
    reload_enabled: bool,
    strict_port: bool,
) -> None:
    """Run the web dashboard."""
    cfg = configmod.load()
    configmod.ensure_dirs(cfg)
    try:
        if reload_enabled:
            from . import reloader

            reloader.serve(
                cfg,
                host=host,
                port=port,
                open_browser=open_browser,
                workers=workers,
                strict_port=strict_port,
            )
        else:
            from . import server as servermod

            servermod.serve(
                cfg,
                host=host,
                port=port,
                open_browser=open_browser,
                workers=workers,
                strict_port=strict_port,
            )
    except KeyboardInterrupt:
        console.print(Text("server stopped", style=C_MUTE))


# --------------------------------------------------------------------------- #
# maintenance
# --------------------------------------------------------------------------- #


@main.command(name="import-db")
@click.argument(
    "source_db",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--source-key",
    required=True,
    help="stable identity used to resume and deduplicate this source league",
)
@click.option(
    "--through",
    type=click.IntRange(1),
    default=None,
    help="only import rated source games with id at or below this cutoff",
)
@click.option(
    "--source-state-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="directory containing source replays/ and logs/ (default: database directory)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="validate and report without importing games or artifacts",
)
@click.option("--json", "as_json", is_flag=True, help="emit JSON only")
def import_db(
    source_db: Path,
    source_key: str,
    through: int | None,
    source_state_dir: Path | None,
    dry_run: bool,
    as_json: bool,
) -> None:
    """Import rated games from another oarena database into this league."""

    with _session(quiet=as_json, sync=False) as sess:
        report = sess.store.import_rated_games(
            source_db,
            source_key=source_key,
            rater=sess.rater,
            replay_dir=sess.cfg.replay_dir,
            log_dir=sess.cfg.log_dir,
            source_state_dir=source_state_dir,
            through=through,
            dry_run=dry_run,
        )
        if as_json:
            _emit_json(asdict(report))
            return
        if report.dry_run:
            console.print(
                Text("validated ", style="green")
                + Text(f"{report.selected} rated source game(s)")
                + Text(
                    f" · would import {report.would_import} · already imported {report.skipped}"
                    f" · {len(report.bots)} referenced bot(s)",
                    style=C_MUTE,
                )
            )
            return
        console.print(
            Text(f"imported {report.imported} rated game(s)", style="green")
            + Text(
                f" · skipped {report.skipped} already imported"
                f" · ratings appended from current destination ratings",
                style=C_MUTE,
            )
        )


@main.command()
def recompute() -> None:
    """Replay every rated game from scratch to rebuild the ladder."""
    with _session(sync=False) as sess:
        _require_owned_state(sess.cfg, "recompute")
        total = sess.store.game_count()
        with console.status(f"replaying {total} games…", spinner="dots"):
            sess.store.recompute(sess.rater)
        console.print(Text(f"rebuilt every rating from {total} games", style="green"))
        rows = reporting.ladder(sess.store, include_inactive=False)
        if rows:
            console.print(_ladder_table(rows))


@main.command()
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
@click.option("--all", "wipe_all", is_flag=True, help="also forget the bots themselves")
@click.option("--clean", "clean_state", is_flag=True, help="remove all .oarena state, including the database")
def reset(yes: bool, wipe_all: bool, clean_state: bool) -> None:
    """Delete game history, or use --clean for a completely fresh arena."""
    if clean_state and wipe_all:
        raise click.UsageError("--clean already removes the database and bot rows; do not combine it with --all")
    with _session(quiet=True, sync=False) as sess:
        cfg, store = sess.cfg, sess.store
        _require_owned_state(cfg, "reset")
        total = store.game_count()
        if clean_state:
            files = sum(1 for path in cfg.state_dir.rglob("*") if path.is_file()) if cfg.state_dir.exists() else 0
            what = f"all oarena state: database, ladder, {files} state file(s), replays and logs"
        else:
            what = "every game, replay and log" + (", and every bot" if wipe_all else "")
        if not yes:
            click.confirm(f"delete {what} ({total} games)?", abort=True, default=False)
        if clean_state:
            # Keep the advisory-lock inode in place while deleting every other
            # state entry. Removing a held lock file would let another process
            # create a new inode and bypass the lease.
            with store.writer_lock.hold("clean reset"):
                store.close()
                for entry in cfg.state_dir.iterdir():
                    if entry == store.writer_lock.path:
                        continue
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        try:
                            entry.unlink()
                        except OSError:
                            pass
            console.print(Text("clean reset: removed all .oarena state", style="yellow"))
            return
        with store.writer_lock.hold("reset"):
            store.reset(keep_bots=not wipe_all, rater=sess.rater)
            removed = (
                _empty_dir(cfg.replay_dir)
                + _empty_dir(cfg.log_dir)
                + _empty_dir(cfg.tmp_dir)
            )
        console.print(
            Text(f"reset: {total} games and {removed} files removed", style="yellow")
            + Text("" if wipe_all else "  (bots kept, ratings back to initial)", style=C_MUTE)
        )
        if wipe_all:
            console.print(
                Text("bot directories are untouched; they re-register on the next sync", style=C_MUTE)
            )


def _empty_dir(directory: Path) -> int:
    count = 0
    if not directory.is_dir():
        return 0
    for entry in directory.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
            count += 1
        except OSError:
            pass
    return count


@main.command()
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def gc(yes: bool) -> None:
    """Prune orphaned replays/logs and anything past the replay budget."""
    with _session(quiet=True, sync=False) as sess:
        cfg, store = sess.cfg, sess.store
        _require_owned_state(cfg, "gc")
        kept_replays = dict(store.replay_files())
        kept_logs = dict(store.log_files())

        orphans: list[Path] = []
        for directory, kept in ((cfg.replay_dir, set(kept_replays.values())), (cfg.log_dir, set(kept_logs.values()))):
            if not directory.is_dir():
                continue
            orphans.extend(p for p in directory.iterdir() if p.is_file() and p.name not in kept)
        stale = [(gid, name, cfg.replay_dir / name) for gid, name in kept_replays.items()]
        missing = [(gid, path) for gid, _name, path in stale if not path.exists()]

        over: list[tuple[int, Path]] = []
        budget = cfg.replay_budget_bytes
        live = [(gid, cfg.replay_dir / name) for gid, name in kept_replays.items() if (cfg.replay_dir / name).exists()]
        total = sum(p.stat().st_size for _gid, p in live)
        if budget is not None:
            size = total
            for gid, path in sorted(live):  # oldest game id first
                if size <= budget:
                    break
                size -= path.stat().st_size
                over.append((gid, path))

        freed = sum(p.stat().st_size for p in orphans) + sum(p.stat().st_size for _gid, p in over)
        console.print(
            Text(
                f"{len(orphans)} orphan files · {len(missing)} dangling rows · "
                f"{len(over)} replays over the {cfg.replay_budget_mb if cfg.replay_budget_mb is not None else 'unlimited'} budget · "
                f"{freed / 1e6:.1f} MB to free",
                style=C_MUTE,
            )
        )
        if not (orphans or missing or over):
            console.print(Text("nothing to collect", style="green"))
            return
        if not yes:
            click.confirm("delete them?", abort=True, default=True)

        for path in orphans:
            try:
                path.unlink()
            except OSError:
                pass
        for gid, _path in missing:
            store.clear_replay(gid)
        for gid, path in over:
            try:
                path.unlink()
            except OSError:
                pass
            store.clear_replay(gid)
        _empty_dir(cfg.tmp_dir)
        console.print(Text(f"freed {freed / 1e6:.1f} MB", style="green"))


# --------------------------------------------------------------------------- #
# bench
# --------------------------------------------------------------------------- #


@main.command()
@click.option("-w", "--workers", "worker_spec", default="1,2,4,8", show_default=True, help="comma-separated worker counts")
@click.option("-n", "--games", default=4, type=click.IntRange(1), show_default=True, help="games per worker count")
@click.option("-m", "--map", "map_spec", default=None, help="map to benchmark on (default: the smallest)")
@click.option("--bots", "bot_pair", nargs=2, default=None, help="the two bots to play (default: two playable ones)")
def bench(worker_spec: str, games: int, map_spec: str | None, bot_pair: tuple[str, str] | None) -> None:
    """Measure how well games parallelise on this machine.

    Nothing is rated or stored: the games run through the same supervisor the
    league uses, straight into a throwaway pool.
    """
    with _session(quiet=True) as sess:
        cfg = sess.cfg
        try:
            counts = [int(part) for part in worker_spec.replace(" ", "").split(",") if part]
        except ValueError:
            raise click.UsageError(f"--workers takes a comma-separated list of integers, got {worker_spec!r}") from None
        counts = [c for c in counts if c > 0]
        if not counts:
            raise click.UsageError("--workers needs at least one positive integer")

        sources = botsmod.discover(cfg.bots_dir)
        if not sources:
            raise BotError(f"no bots in {cfg.bots_dir} to benchmark with")
        if bot_pair:
            left = sess.league.resolve(bot_pair[0])
            right = sess.league.resolve(bot_pair[1])
        else:
            # Prefer active bots; disabled bots are deliberately outside normal
            # matchmaking, while broken is only a diagnostic state.
            sess.league.sync()
            active = {b.name for b in sess.store.bots(active_only=True)}
            usable = [s for s in sources if s.name in active] or sources
            left = usable[0]
            right = usable[1] if len(usable) > 1 else usable[0]
        game_map = (
            mapsmod.resolve(cfg.maps_dir, map_spec, cfg.extra_maps_dir)
            if map_spec
            else mapsmod.select(cfg.maps_dir, None, [], cfg.extra_maps_dir)[0]
        )

        console.print(
            Text(f"bench · {left.name} vs {right.name} on {game_map.name}", style=f"bold {C_ACCENT}")
            + Text(f"   {games} games per setting", style=C_MUTE)
        )

        rng = random.Random(cfg.seed)
        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_MUTE}", pad_edge=False)
        table.add_column("WORKERS", justify="right")
        table.add_column("GAMES", justify="right")
        table.add_column("WALL", justify="right")
        table.add_column("PER GAME", justify="right")
        table.add_column("GAMES/MIN", justify="right")
        table.add_column("SPEEDUP", justify="right")
        table.add_column("FAILED", justify="right")

        baseline: float | None = None
        total_failed = 0
        for count in counts:
            specs = [
                GameSpec(
                    a=left,
                    b=right,
                    map=game_map,
                    seed=rng.randrange(1, 2**31),
                    tle_ms=cfg.tle_ms,
                    timeout_s=cfg.game_timeout_s,
                    cwd=cfg.root,
                    tmp_dir=cfg.tmp_dir,
                    python_dont_write_bytecode=cfg.python_dont_write_bytecode,
                )
                for _ in range(games)
            ]
            started = time.monotonic()
            pool = Pool(count)
            interrupted = False
            try:
                with console.status(f"{count} workers × {games} games…", spinner="dots"):
                    futures = [pool.submit(spec) for spec in specs]
                    outcomes = [f.result() for f in futures]
            except KeyboardInterrupt:
                interrupted = True
                console.print(Text("stopping — aborting benchmark games now…", style="yellow"))
                pool.force_stop()
                raise SystemExit(130) from None
            finally:
                if not interrupted:
                    pool.shutdown()
            elapsed = max(time.monotonic() - started, 1e-6)
            failed = sum(0 if o.ok else 1 for o in outcomes)
            for outcome in outcomes:
                for path in (outcome.replay_path, outcome.log_path):
                    if path is not None:
                        try:
                            path.unlink()
                        except OSError:
                            pass
            baseline = baseline if baseline is not None else elapsed
            total_failed += failed
            table.add_row(
                str(count),
                str(games),
                f"{elapsed:.1f}s",
                f"{elapsed / games:.2f}s",
                f"{games / elapsed * 60:.1f}",
                Text(f"{baseline / elapsed:.2f}×", style=C_ACCENT),
                Text(str(failed), style=C_LOSS) if failed else Text("0", style=C_FAINT),
            )
        console.print(table)
        if total_failed:
            # A failing pair finishes in milliseconds, so the timings above would
            # be measuring how fast the engine can crash rather than how fast it
            # can play. Say so instead of printing a confident, wrong speedup.
            console.print(
                Text(f"warning: {total_failed} game(s) failed — these timings are not ", style=C_LOSS)
                + Text("meaningful. Pick a working pair with ", style=C_LOSS)
                + Text("oarena bench --bots A B", style=C_ACCENT)
                + Text(f", or check `oarena log`. ({left.name} vs {right.name})", style=C_LOSS)
            )
        console.print(
            Text(f"cpu cores: {os.cpu_count()}  ·  configured workers: {cfg.n_workers}", style=C_MUTE)
        )


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


@dataclass
class _Check:
    name: str
    ok: bool
    detail: str
    warn: bool = False


def _check_engine_subprocess() -> _Check:
    """Import the native engine in a *throwaway* interpreter.

    A bot that fails to load takes its whole process down with a SIGSEGV, so the
    parent never imports ``fcode.fcode_engine`` — not even to check on it.
    """
    code = "from fcode.fcode_engine import run_game; print(run_game.__name__)"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _Check("engine loads (subprocess)", False, f"{type(exc).__name__}: {exc}")
    if proc.returncode == 0:
        return _Check("engine loads (subprocess)", True, "fcode.fcode_engine.run_game")
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return _Check(
        "engine loads (subprocess)",
        False,
        detail[-1] if detail else f"exit {proc.returncode}",
    )


@main.command()
def doctor() -> None:
    """Check that this project can actually run games."""
    checks: list[_Check] = []

    config_path = configmod.find_config()
    checks.append(
        _Check(
            f"{configmod.CONFIG_NAME} found",
            config_path is not None,
            str(config_path) if config_path else "run `oarena init` in your project root",
        )
    )

    try:
        version = configmod.check_fcode()
        checks.append(_Check("fcode importable", True, f"version {version}"))
    except RuntimeError as exc:
        checks.append(_Check("fcode importable", False, " ".join(str(exc).split())))

    checks.append(_check_engine_subprocess())

    dist = configmod.visualiser_dist()
    checks.append(
        _Check(
            "visualiser bundled",
            dist is not None,
            str(dist) if dist else "no data/visualiser in this fcode — the Watch view will degrade",
            warn=dist is None,
        )
    )

    if config_path is not None:
        cfg = configmod.from_file(config_path)
        found_maps = mapsmod.discover(cfg.maps_dir, cfg.extra_maps_dir)
        checks.append(
            _Check(
                "maps present",
                bool(found_maps),
                (
                    f"{len(found_maps)} maps across {cfg.maps_dir} and {cfg.extra_maps_dir}"
                    if found_maps
                    else f"no *.map26 in {cfg.maps_dir} or {cfg.extra_maps_dir}"
                ),
            )
        )
        sources = botsmod.discover(cfg.bots_dir)
        checks.append(
            _Check(
                "bots present",
                bool(sources),
                f"{len(sources)} bots in {cfg.bots_dir}"
                if sources
                else f"no directory with main.py under {cfg.bots_dir}",
            )
        )
        try:
            configmod.ensure_dirs(cfg)
            store = Store(cfg.db_path)
            try:
                count = store.game_count()
            finally:
                store.close()
            checks.append(_Check("database writable", True, f"{cfg.db_path} ({count} games)"))
        except Exception as exc:  # noqa: BLE001 - any failure here is a real one
            checks.append(_Check("database writable", False, f"{type(exc).__name__}: {exc}"))

    table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    table.add_column(width=2)
    table.add_column("CHECK", no_wrap=True)
    table.add_column("DETAIL", style=C_MUTE)
    failed = 0
    for check in checks:
        if check.ok:
            mark, style = "✓", C_WIN
        elif check.warn:
            mark, style = "!", "yellow"
        else:
            mark, style = "✗", C_LOSS
            failed += 1
        table.add_row(Text(mark, style=style), Text(check.name, style="bold" if not check.ok else ""), check.detail[:96])
    console.print(table)

    if failed:
        console.print(Text(f"{failed} check(s) failed", style=f"bold {C_LOSS}"))
        raise SystemExit(1)
    console.print(Text("all good — try `oarena arena`", style=C_WIN))


if __name__ == "__main__":  # pragma: no cover - `python -m oarena.cli`
    main()
