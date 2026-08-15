"""How long is a customer worth anything for?

Case 02 answered *twelve months, everybody* — one constant, applied to a base
whose churn probabilities span two orders of magnitude. It is the single most
consequential number in the track and it was never argued for, because in that
case it could not change the answer: multiplying every customer by the same
constant cannot re-order a list.

The moment the question is *value* rather than *rank*, it can. And the
alternative is not another constant: a 90-day churn probability already implies a
lifetime. Convert it to a monthly hazard and the expected remaining life of a
memoryless customer is ``1/h``.

That has a consequence which is easy to miss and hard to unsee. A save is worth
the life it preserves, and the higher the hazard, the less life there is to
preserve — so ``p`` in the numerator and ``1/h`` in the denominator very nearly
cancel. ``p / h`` tends to the length of the label window, three months, for
small ``p``. Under a hazard-consistent horizon the expected value of a retention
contact barely depends on churn risk at all.

Whether that is *right* depends on something no dataset here records: whether a
save changes the customer's hazard or merely postpones one draw of it. This
module computes both readings and refuses to pick.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

LABEL_WINDOW_MONTHS = 3.0  # the churn label looks 90 days ahead


def monthly_hazard(p90: float) -> float:
    """The constant monthly hazard implied by a 90-day churn probability.

    ``(1 - h) ** 3 = 1 - p``. Clamped away from both ends: a probability of
    exactly 1 implies an infinite hazard and exactly 0 an infinite life, and
    neither belongs in a customer list.
    """
    p = min(max(p90, 1e-6), 1.0 - 1e-6)
    return 1.0 - (1.0 - p) ** (1.0 / LABEL_WINDOW_MONTHS)


def expected_remaining_months(p90: float, cap: float) -> float:
    """Expected remaining life under a constant hazard, ceilinged at ``cap``.

    The ceiling is a policy, not an estimate. Without one the lowest-risk
    customers are credited with thirty years of margin, which is not a forecast
    anybody would defend out loud — and quietly defending it is how a lifetime
    value model comes to be dominated by its least certain tail.
    """
    return min(1.0 / monthly_hazard(p90), cap)


@dataclass(frozen=True)
class Horizon:
    """One answer to *how many months of margin does saving this customer buy?*"""

    name: str
    note: str
    months: list[float]

    @property
    def mean_months(self) -> float:
        return mean(self.months)

    def quantile(self, q: float) -> float:
        ordered = sorted(self.months)
        return ordered[min(len(ordered) - 1, int(len(ordered) * q))]

    @property
    def spread(self) -> tuple[float, float]:
        return min(self.months), max(self.months)


def flat_horizon(n: int, months: float) -> Horizon:
    """Case 02's assumption, stated as what it is."""
    return Horizon(
        name=f"flat {months:.0f} months",
        note="every customer credited with the same life, whatever their risk",
        months=[months] * n,
    )


def hazard_horizon(probabilities: list[float], cap: float) -> Horizon:
    """Expected life implied by each customer's own churn probability."""
    return Horizon(
        name=f"hazard-implied, capped at {cap:.0f}",
        note="a customer's own 90-day probability, read as a constant monthly hazard",
        months=[expected_remaining_months(p, cap) for p in probabilities],
    )


@dataclass(frozen=True)
class Cancellation:
    """Evidence for the near-cancellation, measured rather than asserted."""

    ratios: list[float]          # p / h, per customer
    window: float = LABEL_WINDOW_MONTHS

    @property
    def mean_ratio(self) -> float:
        return mean(self.ratios)

    @property
    def spread(self) -> tuple[float, float]:
        return min(self.ratios), max(self.ratios)

    @property
    def deviation_from_window(self) -> float:
        """How far the mean ratio sits from the label window, in months."""
        return self.mean_ratio - self.window


def cancellation(probabilities: list[float]) -> Cancellation:
    return Cancellation(ratios=[p / monthly_hazard(p) for p in probabilities])


@dataclass(frozen=True)
class HorizonComparison:
    """The two horizons side by side, on the same customers."""

    flat: Horizon
    hazard: Horizon
    below_flat: int              # customers whose implied life is shorter than the flat one
    n: int

    @property
    def below_flat_share(self) -> float:
        return self.below_flat / self.n if self.n else 0.0

    @property
    def flat_months(self) -> float:
        return self.flat.months[0] if self.flat.months else 0.0


def compare_horizons(probabilities: list[float], flat_months: float, cap: float) -> HorizonComparison:
    flat = flat_horizon(len(probabilities), flat_months)
    hazard = hazard_horizon(probabilities, cap)
    return HorizonComparison(
        flat=flat,
        hazard=hazard,
        below_flat=sum(1 for m in hazard.months if m < flat_months),
        n=len(probabilities),
    )
