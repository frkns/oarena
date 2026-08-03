"""Arena matchmakers: how an endless run chooses the next pair of bots.

`League` re-reads the playable bots from the store before every pick and hands
them to a matchmaker already sorted by ladder ``mu`` (descending), so ranks are
simply list positions and ratings adapt as the run progresses. A
matchmaker returns two *distinct* bot names; the league then queues the pair on
one map twice with the sides swapped, so turn-order bias cancels out.

Constructors (all take the rater first and an optional `random.Random` last)::

    Ladder(rater, rng=None)
    TopK(rater, k=0, rng=None)
    Versus(rater, store, target, rng=None)
    RoundRobin(rater, store, rng=None)

Prefer :func:`make`, which maps the CLI/HTTP `kind` string onto them.

Sampling is deliberately soft: every matchmaker keeps a positive probability on
every reachable pair, because a hard cutoff starves exactly the bots whose
ratings are least trustworthy. The one exception is the explicit `TopK` pool,
which is an opt-in "polish the top of the board" mode.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:  # runtime-free: this module must not drag in the DB layer
    from .ratings import Rater
    from .store import Bot, Record, Store

__all__ = [
    "NoMatch",
    "Matchmaker",
    "Ladder",
    "TopK",
    "Versus",
    "RoundRobin",
    "make",
    "KINDS",
]

RANK_HALF_LIFE = 4.0
"""Anchor preference halves every this many ranks down the board."""

DIST_HALF_LIFE = 2.0
"""Opponent preference halves every this many ranks away from the anchor."""

WIDE_EPS = 0.02
"""Uniform floor: lopsided matchups stay possible, just rare."""

KINDS: tuple[str, ...] = ("ladder", "top", "vs", "rr")

_T = TypeVar("_T")

_ALIASES = {
    "ladder": "ladder",
    "soft": "ladder",
    "softladder": "ladder",
    "default": "ladder",
    "top": "top",
    "topk": "top",
    "vs": "vs",
    "versus": "vs",
    "target": "vs",
    "rr": "rr",
    "roundrobin": "rr",
}


class NoMatch(RuntimeError):
    """No legal pair right now (fewer than two playable bots, target missing, ...).

    The arena loop treats this as "idle and retry", not as a failure: a bot that
    is still being written may show up a second later.
    """


@runtime_checkable
class Matchmaker(Protocol):
    name: str

    def pick(self, bots: list[Bot]) -> tuple[str, str]:
        """Choose two distinct bot names from the playable, μ-sorted `bots`."""
        ...


# --------------------------------------------------------------------------
# helpers


def _ranked(bots: Sequence[Bot]) -> list[Bot]:
    """Ladder order (``mu`` descending, name as tiebreak).

    The league already sorts, so this is a cheap defensive copy that keeps rank
    arithmetic honest if some other caller forgets.
    """
    return sorted(bots, key=lambda b: (-b.mu, b.name))


def _weighted_choice(rng: random.Random, items: Sequence[_T], weights: Sequence[float]) -> _T:
    """Sample one item, degrading to a uniform draw if the weights degenerate.

    Weights can collapse to zero (every sigma is 0) or go non-finite (a rating
    blew up) in ways that would make `random.choices` raise. Matchmaking must
    never be the thing that stops an arena, so a bad weight vector costs
    precision, not availability.
    """
    clean = [w if math.isfinite(w) and w > 0.0 else 0.0 for w in weights]
    if math.fsum(clean) <= 0.0:
        return rng.choice(items)
    return rng.choices(items, weights=clean, k=1)[0]


class _PairGames:
    """Per-pair *attempt* counts, cached against the store's total game count.

    Counts every recorded game for the pair, including crashes and timeouts —
    not just decided ones. A pairing that always fails has still consumed the
    machine's time, and counting only decided games would leave it at zero and
    keep it as attractive to `RoundRobin`/`Versus` as a never-played pair.

    `pick()` runs once per queued game, so the read is refreshed only when the
    number of stored games actually changed. Counts are symmetric: a pair is a
    matchup, not an ordered slot assignment.
    """

    def __init__(self, store: Store) -> None:
        self._store = store
        self._stamp = -1
        self._counts: dict[tuple[str, str], int] = {}

    def refresh(self, names: Sequence[str]) -> None:
        stamp = self._store.game_count()
        if stamp != self._stamp:
            self._counts = self._store.pair_counts()
            self._stamp = stamp

    def between(self, a: str, b: str) -> int:
        key = (a, b) if a < b else (b, a)
        return self._counts.get(key, 0)


# --------------------------------------------------------------------------
# matchmakers


class Ladder:
    """Top-weighted soft sampling — the default arena matchmaker.

    Anchor weight ``2**(-rank / 4) + sigma / sigma0``: prefer the top of the
    board, but boost uncertain bots (newcomers, just-edited bots) so they are
    placed quickly. Opponent weight ``2**(-|rank - anchor| / 2) + 0.02``: mostly
    rank-neighbour games, with a uniform floor that keeps the whole ladder
    connected. Every bot keeps a positive probability, so nothing starves.
    """

    name: str = "ladder"

    def __init__(self, rater: Rater, rng: random.Random | None = None) -> None:
        self.rater = rater
        self.rng = rng or random.Random()

    def pick(self, bots: list[Bot]) -> tuple[str, str]:
        pool = _ranked(bots)
        if len(pool) < 2:
            raise NoMatch("need at least 2 playable bots")
        sigma0 = self.rater.sigma0 or 1.0
        idx = list(range(len(pool)))
        anchor_w = [2.0 ** (-i / RANK_HALF_LIFE) + pool[i].sigma / sigma0 for i in idx]
        ai = _weighted_choice(self.rng, idx, anchor_w)
        others = [j for j in idx if j != ai]
        opp_w = [2.0 ** (-abs(j - ai) / DIST_HALF_LIFE) + WIDE_EPS for j in others]
        oi = _weighted_choice(self.rng, others, opp_w)
        return pool[ai].name, pool[oi].name

    def __repr__(self) -> str:
        return "Ladder()"


class TopK:
    """Hard top-`k` pool: polish an already settled top of the board.

    Bots outside the μ-ranked pool never play, so this is an explicit opt-in;
    use the regular ladder matchmaker when new or freshly edited bots still need
    placement. Inside the pool, pairs are weighted by
    ``quality(a, b) * (sigma_a + sigma_b)`` — close matchups between uncertain
    bots teach the most per game. `k = 0` means the whole board.
    """

    name: str = "top"

    def __init__(self, rater: Rater, k: int = 0, rng: random.Random | None = None) -> None:
        self.rater = rater
        self.k = max(0, int(k))
        self.rng = rng or random.Random()

    def pick(self, bots: list[Bot]) -> tuple[str, str]:
        pool = _ranked(bots)
        if self.k:
            pool = pool[: self.k]
        if len(pool) < 2:
            raise NoMatch(f"need at least 2 playable bots in the top {self.k or len(pool)}")
        pairs: list[tuple[str, str]] = []
        weights: list[float] = []
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                a, b = pool[i], pool[j]
                pairs.append((a.name, b.name))
                weights.append(self.rater.quality(a.rating, b.rating) * (a.sigma + b.sigma))
        return _weighted_choice(self.rng, pairs, weights)

    def __repr__(self) -> str:
        return f"TopK(k={self.k})"


class Versus:
    """One target bot against everyone else.

    Opponent weight ``(2**(-rank / 4) + 2**(-|rank - rank_target| / 2) + 0.02) /
    (games_played_together + 1)``: prefer strong opponents and the target's own
    neighbourhood, while the divisor spreads games across the field instead of
    grinding the same matchup. The target must itself be playable.
    """

    name: str = "vs"

    def __init__(
        self,
        rater: Rater,
        store: Store,
        target: str,
        rng: random.Random | None = None,
    ) -> None:
        self.rater = rater
        self.store = store
        self.target = target
        self.rng = rng or random.Random()
        self._pairs = _PairGames(store)

    def pick(self, bots: list[Bot]) -> tuple[str, str]:
        pool = _ranked(bots)
        if len(pool) < 2:
            raise NoMatch("need at least 2 playable bots")
        names = [b.name for b in pool]
        try:
            rank_t = names.index(self.target)
        except ValueError:
            raise NoMatch(f"target bot {self.target!r} is not playable") from None
        self._pairs.refresh(names)
        opponents: list[str] = []
        weights: list[float] = []
        for i, bot in enumerate(pool):
            if i == rank_t:
                continue
            pref = (
                2.0 ** (-i / RANK_HALF_LIFE)
                + 2.0 ** (-abs(i - rank_t) / DIST_HALF_LIFE)
                + WIDE_EPS
            )
            opponents.append(bot.name)
            weights.append(pref / (self._pairs.between(self.target, bot.name) + 1))
        return self.target, _weighted_choice(self.rng, opponents, weights)

    def __repr__(self) -> str:
        return f"Versus(target={self.target!r})"


class RoundRobin:
    """Always play the least-played pair, ties broken randomly.

    The fastest way to fill in a complete crosstable: it equalises pair counts
    instead of chasing information gain.
    """

    name: str = "rr"

    def __init__(self, rater: Rater, store: Store, rng: random.Random | None = None) -> None:
        self.rater = rater
        self.store = store
        self.rng = rng or random.Random()
        self._pairs = _PairGames(store)

    def pick(self, bots: list[Bot]) -> tuple[str, str]:
        pool = _ranked(bots)
        if len(pool) < 2:
            raise NoMatch("need at least 2 playable bots")
        names = [b.name for b in pool]
        self._pairs.refresh(names)
        fewest = -1
        candidates: list[tuple[str, str]] = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                played = self._pairs.between(names[i], names[j])
                if not candidates or played < fewest:
                    fewest = played
                    candidates = [(names[i], names[j])]
                elif played == fewest:
                    candidates.append((names[i], names[j]))
        return self.rng.choice(candidates)

    def __repr__(self) -> str:
        return "RoundRobin()"


# --------------------------------------------------------------------------


def make(
    kind: str,
    store: Store,
    rater: Rater,
    *,
    top: int = 0,
    target: str | None = None,
    rng: random.Random | None = None,
) -> Matchmaker:
    """Build a matchmaker from a CLI/HTTP `kind` in {"ladder", "top", "vs", "rr"}.

    Raises `ValueError` for an unknown kind or a `vs` run without a target.
    """
    key = _ALIASES.get((kind or "").strip().lower().replace("-", "").replace("_", ""))
    if key is None:
        raise ValueError(f"unknown matchmaker {kind!r} (expected one of: {', '.join(KINDS)})")
    rng = rng or random.Random()
    if key == "ladder":
        return Ladder(rater, rng)
    if key == "top":
        return TopK(rater, top, rng)
    if key == "vs":
        if not target:
            raise ValueError("the 'vs' matchmaker needs a target bot")
        return Versus(rater, store, target, rng)
    return RoundRobin(rater, store, rng)
