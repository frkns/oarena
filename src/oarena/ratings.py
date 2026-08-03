"""TrueSkill ratings for the oarena ladder.

A :class:`Rating` is a plain (mu, sigma) pair — the persisted form, free of any
``trueskill`` object. :class:`Rater` owns the ``trueskill.TrueSkill`` environment
built from the project's ``[trueskill]`` config block and is the only place where
the library is touched.

The ladder is sorted by ``mu``, the posterior mean skill estimate.  The
conservative lower confidence bound ``mu - 1.96*sigma`` remains available as
``lcb95`` (and under the legacy ``score`` name) so callers can see how much
uncertainty remains without silently making it the ranking criterion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import trueskill

if TYPE_CHECKING:  # pragma: no cover - typing only
    from oarena.config import TrueSkillConfig

__all__ = ["CI", "CI_LABEL", "CI_PERCENT", "Rating", "Rater"]

CI = 1.959963984540054
"""Standard-normal quantile for a two-sided 95% interval.

Everything that draws a band or computes LCB95 uses this one constant. psyleague
and the CodinGame crowd use 3σ (a ~99.7% interval), which is an arbitrary round
number; 95% is the interval people actually reason about, and LCB95 is exactly
the band's lower edge.
"""

CI_PERCENT = 95
CI_LABEL = "μ − 1.96σ"
"""How LCB95 is spelled in table captions."""


@dataclass(frozen=True)
class Rating:
    """A bot's skill estimate: a normal distribution over "true" skill."""

    mu: float
    sigma: float

    @property
    def lcb95(self) -> float:
        """Bottom of the 95% interval."""
        return self.mu - CI * self.sigma

    @property
    def score(self) -> float:
        """Legacy name for :attr:`lcb95` (kept for API compatibility)."""
        return self.lcb95

    @property
    def lo(self) -> float:
        """Low edge of the 95% interval — identical to :attr:`lcb95`."""
        return self.lcb95

    @property
    def hi(self) -> float:
        """High edge of the 95% interval."""
        return self.mu + CI * self.sigma

    def __str__(self) -> str:
        return f"{self.score:.2f} (mu={self.mu:.2f} sigma={self.sigma:.2f})"


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


class Rater:
    """Applies game results to ratings using a configured TrueSkill environment."""

    def __init__(self, cfg: TrueSkillConfig) -> None:
        self._cfg = cfg
        self._mu0 = float(cfg.mu)
        self._sigma0 = float(cfg.sigma)
        self._beta = float(cfg.beta)
        self._env = trueskill.TrueSkill(
            mu=self._mu0,
            sigma=self._sigma0,
            beta=self._beta,
            tau=float(cfg.tau),
            draw_probability=float(cfg.draw_prob),
        )

    @property
    def env(self) -> trueskill.TrueSkill:
        """The underlying TrueSkill environment (read-only use)."""
        return self._env

    @property
    def mu0(self) -> float:
        return self._mu0

    @property
    def sigma0(self) -> float:
        """The starting sigma — the ceiling used by :meth:`reinflate`."""
        return self._sigma0

    @property
    def beta(self) -> float:
        return self._beta

    def initial(self) -> Rating:
        """The rating a freshly discovered bot starts with."""
        return Rating(self._mu0, self._sigma0)

    def _to_ts(self, r: Rating) -> trueskill.Rating:
        return self._env.create_rating(mu=r.mu, sigma=r.sigma)

    def update(self, a: Rating, b: Rating, winner: str) -> tuple[Rating, Rating]:
        """Return the post-game ratings of ``a`` and ``b``.

        ``winner`` is ``"a"``, ``"b"`` or ``"draw"`` (``None`` is accepted as a
        draw, matching the nullable ``games.winner`` column).
        """
        key = (winner or "draw").lower()
        if key == "a":
            ranks = [0, 1]
        elif key == "b":
            ranks = [1, 0]
        elif key == "draw":
            ranks = [0, 0]
        else:
            raise ValueError(f"winner must be 'a', 'b' or 'draw', not {winner!r}")

        (na,), (nb,) = self._env.rate([(self._to_ts(a),), (self._to_ts(b),)], ranks=ranks)
        return Rating(float(na.mu), float(na.sigma)), Rating(float(nb.mu), float(nb.sigma))

    def quality(self, a: Rating, b: Rating) -> float:
        """Match quality in 0..1 — 1.0 means a perfectly balanced pairing.

        The module-level function rather than ``env.quality_1vs1``: the method is
        deprecated, and matchmaking calls this once per candidate pair per pick.
        """
        return float(trueskill.quality_1vs1(self._to_ts(a), self._to_ts(b), env=self._env))

    def win_prob(self, a: Rating, b: Rating) -> float:
        """P(a beats b), integrating both bots' uncertainty and the performance noise."""
        denom = math.sqrt(2.0 * self._beta**2 + a.sigma**2 + b.sigma**2)
        if denom <= 0.0:
            return 0.5
        return _phi((a.mu - b.mu) / denom)

    def reinflate(self, r: Rating, factor: float) -> Rating:
        """Lift sigma back towards sigma0 after a bot's source changed.

        The mean is kept — the old bot is still evidence about the new one — but
        confidence is deliberately weakened so the ladder re-tests it.
        """
        return Rating(r.mu, min(self._sigma0, max(r.sigma, self._sigma0 * factor)))
