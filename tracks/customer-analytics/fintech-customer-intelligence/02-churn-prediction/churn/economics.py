"""From a probability to a decision — the part that decides whether any of it mattered.

A churn model does not retain anybody. A *retention action* does, and there is
only budget for a fraction of the base. So the deliverable is not a score, it is
an answer to: **who do we call, and is calling them worth it?**

That reframing changes the ranking. Sorting by churn probability puts the
customer most likely to leave at the top regardless of whether they are worth
keeping; sorting by expected value puts the customer whose departure costs the
most *in expectation* at the top. Those are different lists, and the second one
is the one that makes money. Quantifying that gap is the point of this module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Economics:
    """The commercial assumptions, stated out loud so they can be argued with.

    None of these are measured from the data — they are the retention team's
    numbers, and every figure downstream inherits them. Putting them in one
    frozen object keeps the report honest: change a number here and every
    conclusion moves, which is exactly the sensitivity a reader should see.
    """

    contact_cost: float = 1.50       # cost of one outbound retention contact
    offer_cost: float = 12.00        # cost of the retention offer, paid only when accepted
    save_rate: float = 0.25          # share of would-be churners a contact actually retains
    margin: float = 0.35             # contribution margin on revenue
    horizon_months: int = 12         # how far forward saved revenue is counted

    def value_at_risk(self, monthly_revenue: float) -> float:
        """Margin lost over the horizon if this customer leaves."""
        return monthly_revenue * self.margin * self.horizon_months

    def expected_value(self, churn_probability: float, monthly_revenue: float) -> float:
        """Expected profit from contacting this one customer.

        Saved margin, times the chance the save works, times the chance there
        was anything to save — minus the contact, minus the offer we only pay
        for when it is accepted.
        """
        saved = churn_probability * self.save_rate
        return saved * (self.value_at_risk(monthly_revenue) - self.offer_cost) - self.contact_cost

    def break_even_probability(self, monthly_revenue: float) -> float:
        """The churn probability below which contacting this customer loses money."""
        upside = self.save_rate * (self.value_at_risk(monthly_revenue) - self.offer_cost)
        return self.contact_cost / upside if upside > 0 else float("inf")


@dataclass(frozen=True)
class Targeting:
    """One targeting policy, evaluated at every capacity level."""

    name: str
    order: list[int]              # customer indices, best first
    profit_curve: list[tuple[int, float]]  # (customers contacted, realised profit)

    def profit_at(self, n_contacted: int) -> float:
        best = 0.0
        for n, profit in self.profit_curve:
            if n <= n_contacted:
                best = profit
        return best

    @property
    def optimal(self) -> tuple[int, float]:
        """The capacity that maximises profit, and that profit."""
        return max(self.profit_curve, key=lambda t: t[1], default=(0, 0.0))


def _realised_profit(economics: Economics, churned: int, monthly_revenue: float) -> float:
    """Profit actually booked from contacting one customer, given what happened.

    The counterfactual is unknowable — we cannot observe whether *this* customer
    would have stayed anyway — so the save rate is applied as an expectation
    over customers who did churn. That is an assumption, not a measurement, and
    it is the reason case 05 (incrementality) exists: a held-out control is the
    only thing that turns this number into evidence.
    """
    if churned:
        return economics.save_rate * (economics.value_at_risk(monthly_revenue) - economics.offer_cost) \
            - economics.contact_cost
    return -economics.contact_cost


def build_targeting(
    name: str,
    priority: list[float],
    probabilities: list[float],
    monthly_revenue: list[float],
    y: list[int],
    economics: Economics,
    steps: int = 20,
) -> Targeting:
    """Rank customers by ``priority`` and trace realised profit as capacity grows."""
    order = sorted(range(len(priority)), key=lambda i: priority[i], reverse=True)

    curve: list[tuple[int, float]] = [(0, 0.0)]
    running = 0.0
    checkpoints = {max(1, (s + 1) * len(order) // steps) for s in range(steps)}
    for rank, i in enumerate(order, start=1):
        running += _realised_profit(economics, y[i], monthly_revenue[i])
        if rank in checkpoints:
            curve.append((rank, running))
    return Targeting(name=name, order=order, profit_curve=curve)


@dataclass(frozen=True)
class TargetingComparison:
    by_risk: Targeting
    by_value: Targeting
    contact_all: float
    capacity: int
    overlap_at_capacity: float

    @property
    def uplift_at_capacity(self) -> float:
        return self.by_value.profit_at(self.capacity) - self.by_risk.profit_at(self.capacity)


def compare_policies(
    probabilities: list[float],
    monthly_revenue: list[float],
    y: list[int],
    economics: Economics,
    capacity_share: float = 0.10,
) -> TargetingComparison:
    """Risk-ranked vs value-ranked targeting at a fixed contact capacity."""
    expected = [economics.expected_value(p, r) for p, r in zip(probabilities, monthly_revenue, strict=True)]

    by_risk = build_targeting("by predicted risk", probabilities, probabilities, monthly_revenue, y, economics)
    by_value = build_targeting("by expected value", expected, probabilities, monthly_revenue, y, economics)

    capacity = max(1, int(len(y) * capacity_share))
    top_risk = set(by_risk.order[:capacity])
    top_value = set(by_value.order[:capacity])

    contact_all = sum(
        _realised_profit(economics, y[i], monthly_revenue[i]) for i in range(len(y))
    )

    return TargetingComparison(
        by_risk=by_risk,
        by_value=by_value,
        contact_all=contact_all,
        capacity=capacity,
        overlap_at_capacity=len(top_risk & top_value) / capacity,
    )
