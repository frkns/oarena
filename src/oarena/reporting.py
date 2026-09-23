"""Row and JSON shapes shared by the CLI and the HTTP layer.

Both front-ends read the same store, and both must show the same numbers: a
ladder printed by ``oarena ladder`` and one fetched from ``/api/ladder`` are the
same rows, built here exactly once. The CLI's rich rendering (tables, sigma
bars, colours) lives in ``cli.py``; this module only produces plain data.

Everything returned is JSON-safe: primitives, lists and dicts, snake_case keys,
timestamps left as the ISO-8601 strings the store already holds.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .ratings import CI, CI_LABEL, CI_PERCENT
from .store import Bot, Game, Record, Store

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .maps import GameMap

__all__ = [
    "LadderRow",
    "bot_detail",
    "bot_json",
    "game_json",
    "game_summary_json",
    "ladder",
    "ladder_json",
    "maps_json",
    "matrix_json",
    "pair_map_matrix_json",
    "record_json",
    "timeline_json",
]


# --------------------------------------------------------------------------- #
# ladder
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LadderRow:
    """One line of the leaderboard: rating, record and health for a single bot.

    ``games``/``wins``/``losses``/``draws`` count *rated, decided* games played
    by the bot's current source hash. A crash, timeout or explicitly unrated
    game has no ladder record. ``err_games``/``err_total`` cover all attempts
    by that same source version. Historical versions remain available in bot
    detail and game history, but editing a bot gives these health counters a
    clean slate.
    """

    rank: int
    name: str
    active: bool
    broken: bool
    broken_reason: str
    score: float
    mu: float
    sigma: float
    games: int
    wins: int
    losses: int
    draws: int
    winrate: float | None
    err_games: int
    err_total: int
    note: str
    last_played: str | None
    source_updated: str
    source_version_id: int | None

    @property
    def lcb95(self) -> float:
        """Bottom of the 95% interval (legacy JSON name: ``score``)."""
        return self.score

    @property
    def lo(self) -> float:
        """Bottom of the 95% interval — identical to ``lcb95``."""
        return self.lcb95

    @property
    def hi(self) -> float:
        """Top of the 95% interval."""
        return self.mu + CI * self.sigma


def ladder(
    store: Store,
    *,
    include_inactive: bool = True,
    limit: int | None = None,
) -> list[LadderRow]:
    """Every bot in ladder order (``mu`` descending, name as tiebreak).

    ``limit`` is applied after ordering but before the per-bot record/error
    queries, keeping small live snapshots cheap. Ranks are assigned after
    filtering, so a ladder without inactive bots is numbered 1..n with no gaps.
    """
    bots = [b for b in store.bots() if include_inactive or b.active]
    bots.sort(key=lambda b: (-b.mu, b.name))
    if limit is not None:
        bots = bots[:max(0, int(limit))]

    latest_versions = store.latest_versions()
    rows: list[LadderRow] = []
    for rank, bot in enumerate(bots, start=1):
        source_hash = bot.src_hash or None
        rec = store.record(bot.name, rated_only=True, source_hash=source_hash)
        err_games, err_total = store.error_count(bot.name, source_hash=source_hash)
        last_played = store.last_played(bot.name, source_hash=source_hash)
        version = latest_versions.get(bot.name)
        rows.append(
            LadderRow(
                rank=rank,
                name=bot.name,
                active=bot.active,
                broken=bot.broken,
                broken_reason=bot.broken_reason,
                score=bot.rating.score,
                mu=bot.mu,
                sigma=bot.sigma,
                games=rec.games,
                wins=rec.wins,
                losses=rec.losses,
                draws=rec.draws,
                winrate=rec.winrate,
                err_games=err_games,
                err_total=err_total,
                note=bot.note,
                last_played=last_played,
                source_updated=version[1] if version is not None else bot.created,
                source_version_id=version[0] if version is not None else None,
            )
        )
    return rows


def ladder_json(rows: Sequence[LadderRow]) -> list[dict[str, Any]]:
    """Serialise ladder rows, adding the ``lo``/``hi`` band the charts draw."""
    return [
        {
            "rank": r.rank,
            "name": r.name,
            "active": r.active,
            "broken": r.broken,
            "broken_reason": r.broken_reason,
            "score": r.score,
            "lcb95": r.lcb95,
            "mu": r.mu,
            "sigma": r.sigma,
            "lo": r.lo,
            "hi": r.hi,
            "games": r.games,
            "wins": r.wins,
            "losses": r.losses,
            "draws": r.draws,
            "winrate": r.winrate,
            "err_games": r.err_games,
            "err_total": r.err_total,
            "note": r.note,
            "last_played": r.last_played,
            "source_updated": r.source_updated,
            "source_version_id": r.source_version_id,
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# games
# --------------------------------------------------------------------------- #


def _delta(mu_before: float | None, sigma_before: float | None,
           mu_after: float | None, sigma_after: float | None) -> float | None:
    """Change in LCB95 across one game, or ``None`` if unrated."""
    if None in (mu_before, sigma_before, mu_after, sigma_after):
        return None
    before = float(mu_before) - CI * float(sigma_before)  # type: ignore[arg-type]
    after = float(mu_after) - CI * float(sigma_after)  # type: ignore[arg-type]
    return after - before


def game_json(g: Game) -> dict[str, Any]:
    """One game row as JSON, plus the few things every view derives from it.

    Extras over the raw columns: ``ok``, ``winner_name`` (the bot that won, not
    the slot), ``a_delta``/``b_delta`` (LCB95 change, ``None`` when the game was
    not rated) and ``has_replay``/``has_log``.
    """
    winner_name: str | None = None
    if g.winner == "a":
        winner_name = g.a
    elif g.winner == "b":
        winner_name = g.b

    return {
        "id": g.id,
        "a": g.a,
        "b": g.b,
        "a_src_hash": g.a_src_hash,
        "b_src_hash": g.b_src_hash,
        "fcode_version": g.fcode_version,
        "has_fcode_metadata": bool(g.fcode_metadata_json),
        "map": g.map,
        "seed": g.seed,
        "rated": bool(g.rated),
        "status": g.status,
        "ok": g.status == "ok",
        "winner": g.winner,
        "winner_name": winner_name,
        "win_condition": g.win_condition,
        "turns": g.turns,
        "duration_ms": g.duration_ms,
        "resign_message": g.resign_message,
        "error": g.error,
        "a_titanium": g.a_titanium,
        "a_mined": g.a_mined,
        "a_units": g.a_units,
        "a_buildings": g.a_buildings,
        "a_errors": g.a_errors,
        "b_titanium": g.b_titanium,
        "b_mined": g.b_mined,
        "b_units": g.b_units,
        "b_buildings": g.b_buildings,
        "b_errors": g.b_errors,
        "a_mu_before": g.a_mu_before,
        "a_sigma_before": g.a_sigma_before,
        "a_mu_after": g.a_mu_after,
        "a_sigma_after": g.a_sigma_after,
        "b_mu_before": g.b_mu_before,
        "b_sigma_before": g.b_sigma_before,
        "b_mu_after": g.b_mu_after,
        "b_sigma_after": g.b_sigma_after,
        "a_delta": _delta(g.a_mu_before, g.a_sigma_before, g.a_mu_after, g.a_sigma_after),
        "b_delta": _delta(g.b_mu_before, g.b_sigma_before, g.b_mu_after, g.b_sigma_after),
        "replay": g.replay,
        "log": g.log,
        "has_replay": bool(g.replay),
        "has_log": bool(g.log),
        "tag": g.tag,
        "batch_ordinal": g.batch_ordinal,
        "ts": g.ts,
    }


def game_summary_json(g: Game) -> dict[str, Any]:
    """The compact game shape used by the Games table.

    Game detail, CLI JSON and event payloads deliberately keep using
    :func:`game_json`.  The history table only needs these values, so omitting
    source hashes, rating snapshots, resource totals and file paths avoids
    serialising and transferring data it never reads.
    """
    return {
        "id": g.id,
        "a": g.a,
        "b": g.b,
        "map": g.map,
        "rated": bool(g.rated),
        "status": g.status,
        "winner": g.winner,
        "win_condition": g.win_condition,
        "turns": g.turns,
        "duration_ms": g.duration_ms,
        "resign_message": g.resign_message,
        "error": g.error,
        "a_errors": g.a_errors,
        "b_errors": g.b_errors,
        "has_replay": bool(g.replay),
        "tag": g.tag,
        "batch_ordinal": g.batch_ordinal,
        "ts": g.ts,
    }


# --------------------------------------------------------------------------- #
# bots
# --------------------------------------------------------------------------- #


def record_json(rec: Record) -> dict[str, Any]:
    """A W/L/D tally with its derived win rate (``None`` when nothing was played)."""
    return {
        "wins": rec.wins,
        "losses": rec.losses,
        "draws": rec.draws,
        "games": rec.games,
        "winrate": rec.winrate,
        "score": rec.score,
    }


def bot_json(bot: Bot) -> dict[str, Any]:
    """A bot row plus its derived rating band."""
    return {
        "name": bot.name,
        "dir": bot.dir,
        "entry": bot.entry,
        "active": bot.active,
        "broken": bot.broken,
        "broken_reason": bot.broken_reason,
        "playable": bot.playable,
        "src_hash": bot.src_hash,
        "mu": bot.mu,
        "sigma": bot.sigma,
        "score": bot.rating.score,
        "lcb95": bot.rating.lcb95,
        "lo": bot.rating.lo,
        "hi": bot.rating.hi,
        "note": bot.note,
        "created": bot.created,
        "updated": bot.updated,
    }


def bot_detail(store: Store, name: str) -> dict[str, Any]:
    """Everything the bot drawer and ``oarena bot info`` show.

    ``{bot, record, h2h, maps, history, versions, crashes}``. ``h2h`` and
    ``maps`` are *lists* of records (each carrying its ``opponent`` / ``map``
    key) already ordered for display — most-played opponent first, maps
    alphabetically — because both consumers render them as ordered tables.

    Raises ``KeyError`` if no such bot is stored.
    """
    bot = store.get_bot(name)
    if bot is None:
        raise KeyError(name)

    err_games, err_total = store.error_count(name)
    h2h = [{"opponent": opp, **record_json(rec)} for opp, rec in store.head_to_head(name).items()]
    h2h.sort(key=lambda row: (-int(row["games"]), str(row["opponent"])))
    per_map = [{"map": m, **record_json(rec)} for m, rec in store.map_record(name).items()]
    per_map.sort(key=lambda row: str(row["map"]))

    detail = bot_json(bot)
    detail["err_games"] = err_games
    detail["err_total"] = err_total

    return {
        "bot": detail,
        "record": record_json(store.record(name)),
        "h2h": h2h,
        "maps": per_map,
        "history": store.rating_history(name),
        "versions": [
            {"id": vid, "hash": src_hash, "ts": ts} for vid, src_hash, ts in store.versions(name)
        ],
        "crashes": [game_json(g) for g in store.recent_crashes(name)],
    }


def timeline_json(store: Store, *, top: int = 5, limit: int | None = None) -> dict[str, Any]:
    """Rating histories for the leading active ``top`` bots, including source versions.

    A single payload keeps the all-bots graph coherent: every series comes from
    the same database snapshot and is ranked by the current posterior mean.
    ``top = 0`` means the complete ladder, intentionally capped by callers.
    """
    rows = ladder(store, include_inactive=False)
    selected = rows if top == 0 else rows[:top]
    return {
        "bots": [
            {
                "name": row.name,
                "rank": row.rank,
                "score": row.score,
                "lcb95": row.lcb95,
                "history": store.rating_history(row.name, limit=limit),
                "versions": [
                    {"id": vid, "hash": src_hash, "ts": ts}
                    for vid, src_hash, ts in store.versions(row.name)
                ],
            }
            for row in selected
        ]
    }


# --------------------------------------------------------------------------- #
# crosstable
# --------------------------------------------------------------------------- #


def matrix_json(store: Store, names: Sequence[str], *, min_games: int = 0) -> dict[str, Any]:
    """Head-to-head crosstable over ``names``, in the order given.

    ``cells[a][b]`` is a's record against b. Every name gets a (possibly empty)
    row, but pairings that were never played are omitted from it, so the payload
    stays small on a sparse board. ``min_games`` drops cells with too few games
    for the caller to trust.
    """
    cells: dict[str, dict[str, Any]] = {name: {} for name in names}
    for a, row in store.matrix(names).items():
        for b, rec in row.items():
            if a == b or rec.games <= 0 or rec.games < min_games:
                continue
            cells[a][b] = record_json(rec)
    return {"names": list(names), "cells": cells}


def pair_map_matrix_json(store: Store, first: str, second: str, maps: Sequence[str]) -> dict[str, Any]:
    """A two-row, map-keyed matrix for one exact head-to-head pairing.

    The shape deliberately mirrors :func:`matrix_json`: a row name indexes a
    dictionary of cells.  The UI can therefore use the same renderer for the
    league crosstable and a Games-page pairing breakdown.
    """
    records = store.pair_map_record(first, second)
    cells: dict[str, dict[str, Any]] = {first: {}, second: {}}
    for name in maps:
        rec = records.get(name)
        if rec is None or not rec.games:
            continue
        cells[first][name] = record_json(rec)
        cells[second][name] = {
            "wins": rec.losses,
            "losses": rec.wins,
            "draws": rec.draws,
            "games": rec.games,
            "winrate": 1.0 - rec.winrate if rec.winrate is not None else None,
            "score": rec.losses + 0.5 * rec.draws,
        }
    return {"names": [first, second], "columns": list(maps), "cells": cells}


# --------------------------------------------------------------------------- #
# maps
# --------------------------------------------------------------------------- #


def maps_json(store: Store, maps: Iterable[GameMap]) -> list[dict[str, Any]]:
    """Maps with their geometry (including base64 tiles) and how often they were played."""
    counts = store.map_play_counts()
    return [{**m.to_json(), "games": counts.get(m.name, 0)} for m in maps]
