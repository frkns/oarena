"""`oarena.ratings`: direction, convergence, re-inflation and win probability."""

from __future__ import annotations

import pytest

from oarena.config import TrueSkillConfig
from oarena.ratings import CI, Rater, Rating


# --------------------------------------------------------------------------- #
# Rating
# --------------------------------------------------------------------------- #


def test_lcb95_and_legacy_score_are_the_bottom_of_the_interval() -> None:
    r = Rating(25.0, 8.0)
    assert r.lcb95 == pytest.approx(25.0 - CI * 8.0)
    assert r.score == pytest.approx(r.lcb95)
    assert r.lo == pytest.approx(r.lcb95)
    assert r.hi == pytest.approx(25.0 + CI * 8.0)
    assert CI == pytest.approx(1.96, abs=1e-3)


def test_rating_is_frozen() -> None:
    with pytest.raises(Exception):
        Rating(25.0, 8.0).mu = 1.0  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Rater basics
# --------------------------------------------------------------------------- #


def test_initial_matches_the_config(rater: Rater) -> None:
    initial = rater.initial()
    assert initial.mu == pytest.approx(25.0)
    assert initial.sigma == pytest.approx(25.0 / 3.0)
    assert rater.sigma0 == pytest.approx(initial.sigma)


def test_custom_config_is_honoured() -> None:
    custom = Rater(TrueSkillConfig(mu=1200.0, sigma=200.0, beta=100.0, tau=2.0))
    assert custom.initial() == Rating(1200.0, 200.0)
    assert custom.sigma0 == pytest.approx(200.0)


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def test_a_win_moves_a_up_and_b_down(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    na, nb = rater.update(a, b, "a")

    assert na.mu > a.mu
    assert nb.mu < b.mu
    assert na.sigma < a.sigma
    assert nb.sigma < b.sigma
    assert na.mu - a.mu == pytest.approx(b.mu - nb.mu)


def test_b_win_is_the_mirror_image(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    a_wins = rater.update(a, b, "a")
    b_wins = rater.update(a, b, "b")

    assert b_wins[0] == a_wins[1]
    assert b_wins[1] == a_wins[0]


def test_a_draw_between_equals_only_shrinks_sigma(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    na, nb = rater.update(a, b, "draw")

    assert na.mu == pytest.approx(a.mu)
    assert nb.mu == pytest.approx(b.mu)
    assert na.sigma < a.sigma
    assert nb.sigma < b.sigma


def test_a_draw_pulls_unequal_ratings_together(rater: Rater) -> None:
    strong, weak = Rating(35.0, 4.0), Rating(15.0, 4.0)
    ns, nw = rater.update(strong, weak, "draw")

    assert ns.mu < strong.mu
    assert nw.mu > weak.mu


def test_none_is_treated_as_a_draw(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    assert rater.update(a, b, None) == rater.update(a, b, "draw")  # type: ignore[arg-type]


def test_unknown_winner_is_rejected(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    with pytest.raises(ValueError):
        rater.update(a, b, "maybe")


def test_sigma_shrinks_monotonically_over_many_games(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    sigmas = [a.sigma]
    for i in range(30):
        a, b = rater.update(a, b, "a" if i % 2 else "b")
        sigmas.append(a.sigma)

    assert all(later <= earlier for earlier, later in zip(sigmas, sigmas[1:]))
    assert sigmas[-1] < sigmas[0] / 2


def test_a_consistent_winner_separates_from_the_loser(rater: Rater) -> None:
    a, b = rater.initial(), rater.initial()
    for _ in range(20):
        a, b = rater.update(a, b, "a")
    assert a.score > b.hi or a.mu > b.mu + 10.0


# --------------------------------------------------------------------------- #
# reinflate
# --------------------------------------------------------------------------- #


def test_reinflate_lifts_a_settled_sigma_to_the_floor(rater: Rater) -> None:
    settled = Rating(30.0, 1.0)
    lifted = rater.reinflate(settled, 0.5)

    assert lifted.mu == pytest.approx(settled.mu)
    assert lifted.sigma == pytest.approx(rater.sigma0 * 0.5)


def test_reinflate_never_exceeds_sigma0(rater: Rater) -> None:
    wide = Rating(30.0, rater.sigma0 * 4)
    assert rater.reinflate(wide, 0.5).sigma == pytest.approx(rater.sigma0)


def test_reinflate_leaves_an_already_wide_sigma_alone(rater: Rater) -> None:
    middling = Rating(30.0, rater.sigma0 * 0.8)
    assert rater.reinflate(middling, 0.5).sigma == pytest.approx(middling.sigma)


def test_reinflate_with_factor_one_resets_to_sigma0(rater: Rater) -> None:
    assert rater.reinflate(Rating(30.0, 0.5), 1.0).sigma == pytest.approx(rater.sigma0)


def test_reinflate_with_factor_zero_is_a_no_op(rater: Rater) -> None:
    assert rater.reinflate(Rating(30.0, 0.5), 0.0).sigma == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# probabilities
# --------------------------------------------------------------------------- #


def test_win_prob_of_equals_is_a_half(rater: Rater) -> None:
    assert rater.win_prob(rater.initial(), rater.initial()) == pytest.approx(0.5)


def test_win_prob_is_symmetric_and_bounded(rater: Rater) -> None:
    a, b = Rating(32.0, 3.0), Rating(21.0, 6.0)
    forward = rater.win_prob(a, b)
    backward = rater.win_prob(b, a)

    assert 0.0 < forward < 1.0
    assert 0.0 < backward < 1.0
    assert forward + backward == pytest.approx(1.0)
    assert forward > 0.5


def test_win_prob_grows_with_the_mean_gap(rater: Rater) -> None:
    weak = Rating(20.0, 3.0)
    probs = [rater.win_prob(Rating(mu, 3.0), weak) for mu in (20.0, 25.0, 30.0, 40.0)]
    assert probs == sorted(probs)


def test_quality_is_highest_for_equals(rater: Rater) -> None:
    even = rater.quality(rater.initial(), rater.initial())
    lopsided = rater.quality(Rating(45.0, 1.0), Rating(5.0, 1.0))

    assert 0.0 < even <= 1.0
    assert 0.0 <= lopsided < even
