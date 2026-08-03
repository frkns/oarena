"""`oarena.matchmaking`: pairing policies, fairness and the `make` factory."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from oarena import matchmaking
from oarena.bots import BotSource
from oarena.matchmaking import KINDS, Ladder, NoMatch, RoundRobin, TopK, Versus
from oarena.ratings import Rater, Rating
from oarena.store import Bot, Game, Store


def bot(name: str, mu: float = 25.0, sigma: float = 25.0 / 3.0) -> Bot:
    return Bot(name=name, mu=mu, sigma=sigma)


def spread(names: list[str]) -> list[Bot]:
    """Bots on a clearly ordered ladder, strongest first."""
    return [bot(name, mu=40.0 - 5.0 * i, sigma=2.0) for i, name in enumerate(names)]


@pytest.fixture
def rng() -> random.Random:
    return random.Random(20260727)


@pytest.fixture
def pool() -> list[Bot]:
    return spread(["a", "b", "c", "d", "e"])


@pytest.fixture
def seeded_store(store: Store, tmp_path: Path) -> Store:
    for name in ("a", "b", "c", "d", "e"):
        directory = tmp_path / name
        store.upsert_bot(
            BotSource(name=name, dir=directory, entry=directory / "main.py",
                      src_hash="h"),
            Rating(25.0, 8.0),
        )
    return store


def every_maker(rater: Rater, store: Store, rng: random.Random) -> list[object]:
    return [
        Ladder(rater, rng),
        TopK(rater, 0, rng),
        TopK(rater, 3, rng),
        Versus(rater, store, "c", rng),
        RoundRobin(rater, store, rng),
    ]


# --------------------------------------------------------------------------- #
# common contract
# --------------------------------------------------------------------------- #


def test_every_matchmaker_returns_two_distinct_known_bots(
    rater: Rater, seeded_store: Store, rng: random.Random, pool: list[Bot]
) -> None:
    names = {b.name for b in pool}
    for maker in every_maker(rater, seeded_store, rng):
        for _ in range(200):
            a, b = maker.pick(list(pool))  # type: ignore[attr-defined]
            assert a != b
            assert {a, b} <= names


def test_every_matchmaker_refuses_a_pool_of_one(
    rater: Rater, seeded_store: Store, rng: random.Random
) -> None:
    for maker in every_maker(rater, seeded_store, rng):
        with pytest.raises(NoMatch):
            maker.pick([bot("lonely")])  # type: ignore[attr-defined]


def test_every_matchmaker_refuses_an_empty_pool(
    rater: Rater, seeded_store: Store, rng: random.Random
) -> None:
    for maker in every_maker(rater, seeded_store, rng):
        with pytest.raises(NoMatch):
            maker.pick([])  # type: ignore[attr-defined]


def test_every_matchmaker_has_a_name(
    rater: Rater, seeded_store: Store, rng: random.Random
) -> None:
    names = {maker.name for maker in every_maker(rater, seeded_store, rng)}  # type: ignore[attr-defined]
    assert names == {"ladder", "top", "vs", "rr"}


# --------------------------------------------------------------------------- #
# Ladder
# --------------------------------------------------------------------------- #


def test_ladder_never_starves_a_bot(rater: Rater, rng: random.Random) -> None:
    pool = spread(["a", "b", "c", "d", "e", "f", "g", "h"])
    maker = Ladder(rater, rng)

    seen: Counter[str] = Counter()
    for _ in range(2000):
        a, b = maker.pick(list(pool))
        seen[a] += 1
        seen[b] += 1

    assert set(seen) == {b.name for b in pool}
    assert min(seen.values()) > 20, seen


def test_ladder_prefers_the_top_of_the_board(rater: Rater, rng: random.Random) -> None:
    pool = spread(["a", "b", "c", "d", "e", "f", "g", "h"])
    maker = Ladder(rater, rng)

    seen: Counter[str] = Counter()
    for _ in range(3000):
        a, b = maker.pick(list(pool))
        seen[a] += 1
        seen[b] += 1

    assert seen["a"] > seen["h"]


def test_ladder_boosts_an_uncertain_newcomer(rater: Rater, rng: random.Random) -> None:
    settled = [bot(name, mu=40.0 - 4.0 * i, sigma=0.5) for i, name in enumerate("abcdef")]
    newcomer = bot("z", mu=25.0, sigma=rater.sigma0)
    maker = Ladder(rater, rng)

    seen: Counter[str] = Counter()
    for _ in range(2000):
        a, b = maker.pick([*settled, newcomer])
        seen[a] += 1
        seen[b] += 1

    assert seen["z"] > seen["f"]


def test_ladder_sorts_its_pool_defensively(rater: Rater, rng: random.Random) -> None:
    shuffled = list(reversed(spread(["a", "b", "c"])))
    a, b = Ladder(rater, rng).pick(shuffled)
    assert {a, b} <= {"a", "b", "c"}


# --------------------------------------------------------------------------- #
# TopK
# --------------------------------------------------------------------------- #


def test_topk_restricts_to_the_pool(rater: Rater, rng: random.Random) -> None:
    pool = spread(["a", "b", "c", "d", "e"])
    maker = TopK(rater, 3, rng)

    seen: set[str] = set()
    for _ in range(500):
        seen.update(maker.pick(list(pool)))

    assert seen == {"a", "b", "c"}


def test_topk_rank_cutoff_uses_mu_when_lcb95_disagrees(
    rater: Rater, rng: random.Random,
) -> None:
    pool = [
        bot("wide", mu=30.0, sigma=10.0),
        bot("tight", mu=29.0, sigma=1.0),
        bot("third", mu=28.0, sigma=1.0),
    ]

    # The legacy conservative score would exclude "wide"; ranking by μ keeps
    # the two bots with the largest means in the top-two matchmaking pool.
    assert set(TopK(rater, 2, rng).pick(pool)) == {"wide", "tight"}


def test_topk_of_zero_uses_the_whole_board(rater: Rater, rng: random.Random) -> None:
    pool = spread(["a", "b", "c", "d"])
    seen: set[str] = set()
    for _ in range(500):
        seen.update(TopK(rater, 0, rng).pick(list(pool)))
    assert seen == {"a", "b", "c", "d"}


def test_topk_needs_two_bots_in_its_pool(rater: Rater, rng: random.Random) -> None:
    with pytest.raises(NoMatch):
        TopK(rater, 1, rng).pick(spread(["a", "b", "c"]))


def test_topk_favours_close_uncertain_pairings(rater: Rater, rng: random.Random) -> None:
    pool = [
        bot("a", mu=30.0, sigma=6.0),
        bot("b", mu=29.0, sigma=6.0),
        bot("c", mu=5.0, sigma=0.4),
    ]
    maker = TopK(rater, 0, rng)

    pairs = Counter(tuple(sorted(maker.pick(list(pool)))) for _ in range(2000))
    assert pairs[("a", "b")] > pairs[("a", "c")]


# --------------------------------------------------------------------------- #
# Versus
# --------------------------------------------------------------------------- #


def test_versus_always_puts_the_target_first(
    rater: Rater, seeded_store: Store, rng: random.Random, pool: list[Bot]
) -> None:
    maker = Versus(rater, seeded_store, "c", rng)
    for _ in range(200):
        a, b = maker.pick(list(pool))
        assert a == "c" and b != "c"


def test_versus_reaches_every_opponent(
    rater: Rater, seeded_store: Store, rng: random.Random, pool: list[Bot]
) -> None:
    maker = Versus(rater, seeded_store, "c", rng)
    seen = {maker.pick(list(pool))[1] for _ in range(500)}
    assert seen == {"a", "b", "d", "e"}


def test_versus_needs_a_playable_target(
    rater: Rater, seeded_store: Store, rng: random.Random, pool: list[Bot]
) -> None:
    maker = Versus(rater, seeded_store, "missing", rng)
    with pytest.raises(NoMatch, match="not playable"):
        maker.pick(list(pool))


def test_versus_spreads_away_from_already_played_opponents(
    rater: Rater, seeded_store: Store, rng: random.Random, pool: list[Bot]
) -> None:
    for _ in range(40):
        seeded_store.add_game(Game(a="c", b="a", map="sprint", winner="a"))
    maker = Versus(rater, seeded_store, "c", rng)

    seen = Counter(maker.pick(list(pool))[1] for _ in range(1000))

    assert seen["a"] < seen["b"]


# --------------------------------------------------------------------------- #
# RoundRobin
# --------------------------------------------------------------------------- #


def test_round_robin_equalises_pair_counts(
    rater: Rater, seeded_store: Store, rng: random.Random
) -> None:
    pool = spread(["a", "b", "c", "d"])
    maker = RoundRobin(rater, seeded_store, rng)

    for _ in range(24):  # 6 pairs, so 4 full cycles
        a, b = maker.pick(list(pool))
        seeded_store.add_game(Game(a=a, b=b, map="sprint", winner="a"))

    counts = Counter()
    cells = seeded_store.matrix([b.name for b in pool])
    for i, x in enumerate(pool):
        for y in pool[i + 1:]:
            counts[(x.name, y.name)] = cells[x.name][y.name].games

    assert len(counts) == 6
    assert max(counts.values()) - min(counts.values()) <= 1, counts


def test_round_robin_picks_an_unplayed_pair_first(
    rater: Rater, seeded_store: Store, rng: random.Random
) -> None:
    pool = spread(["a", "b", "c"])
    for _ in range(5):
        seeded_store.add_game(Game(a="a", b="b", map="sprint", winner="a"))
        seeded_store.add_game(Game(a="a", b="c", map="sprint", winner="a"))

    maker = RoundRobin(rater, seeded_store, rng)
    assert tuple(sorted(maker.pick(list(pool)))) == ("b", "c")


# --------------------------------------------------------------------------- #
# make()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("ladder", Ladder), ("soft", Ladder), ("default", Ladder), ("LADDER", Ladder),
        ("top", TopK), ("topk", TopK), ("top-k", TopK),
        ("rr", RoundRobin), ("round_robin", RoundRobin),
    ],
)
def test_make_maps_kinds_and_aliases(
    rater: Rater, seeded_store: Store, kind: str, expected: type
) -> None:
    assert isinstance(matchmaking.make(kind, seeded_store, rater), expected)


def test_make_builds_versus_with_a_target(rater: Rater, seeded_store: Store) -> None:
    maker = matchmaking.make("vs", seeded_store, rater, target="c")
    assert isinstance(maker, Versus)
    assert maker.target == "c"


def test_make_passes_top_through(rater: Rater, seeded_store: Store) -> None:
    maker = matchmaking.make("top", seeded_store, rater, top=4)
    assert isinstance(maker, TopK) and maker.k == 4


def test_make_rejects_an_unknown_kind(rater: Rater, seeded_store: Store) -> None:
    with pytest.raises(ValueError, match="unknown matchmaker"):
        matchmaking.make("telepathy", seeded_store, rater)


def test_make_requires_a_target_for_vs(rater: Rater, seeded_store: Store) -> None:
    with pytest.raises(ValueError, match="target"):
        matchmaking.make("vs", seeded_store, rater)


def test_make_accepts_every_documented_kind(rater: Rater, seeded_store: Store) -> None:
    for kind in KINDS:
        maker = matchmaking.make(kind, seeded_store, rater, target="c", top=2)
        assert maker.name == kind


def test_make_uses_the_supplied_rng(rater: Rater, seeded_store: Store) -> None:
    pool = spread(["a", "b", "c", "d", "e"])
    first = matchmaking.make("ladder", seeded_store, rater, rng=random.Random(5))
    second = matchmaking.make("ladder", seeded_store, rater, rng=random.Random(5))

    assert [first.pick(list(pool)) for _ in range(20)] == [
        second.pick(list(pool)) for _ in range(20)
    ]
