"""Four target lists from one set of scores, and the thing that separates them.

Every list below uses the same customers, the same churn probabilities, the same
revenue figure and the same commercial constants. The **only** thing that varies
is how many months of margin a save is credited with — the assumption case 02
had to make and could not test, because a constant cannot re-order anything.

One variable at a time is the point. It would be easy to change the horizon,
the revenue definition and the cost model together and report a list that shares
half its names with case 02's; that result would be true and would explain
nothing. The revenue definition is priced separately, in ``costs.py``.

Each list is then scored under **each** accounting, which produces the table this
case exists for: every list wins under its own. The data cannot break the tie,
and neither can the answer key — this world ends at the observation cutoff, so
what a saved customer does afterwards is not merely unobserved, it does not
exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from .horizon import Horizon


@dataclass(frozen=True)
class Constants:
    """The commercial constants, taken from case 02 so the two can be compared.

    Held here rather than imported wholesale because this case replaces exactly
    one of them — the horizon — and inheriting an object whose ``value_at_risk``
    hard-codes the thing under test would be circular.
    """

    contact_cost: float
    offer_cost: float
    save_rate: float
    margin: float


@dataclass(frozen=True)
class Accounting:
    """One way of pricing a saved customer: a horizon plus the constants."""

    horizon: Horizon
    constants: Constants

    @property
    def name(self) -> str:
        return self.horizon.name

    def value_at_risk(self, i: int, revenue: float) -> float:
        return revenue * self.constants.margin * self.horizon.months[i]

    def expected_value(self, i: int, probability: float, revenue: float) -> float:
        saved = probability * self.constants.save_rate
        return saved * (self.value_at_risk(i, revenue) - self.constants.offer_cost) \
            - self.constants.contact_cost

    def realised(self, i: int, churned: int, revenue: float) -> float:
        """Profit booked from contacting one customer, given what happened.

        Same shape as case 02's: the counterfactual for an individual is
        unobservable, so the save rate is applied as an expectation over the
        customers who did churn.
        """
        if churned:
            return self.constants.save_rate * (self.value_at_risk(i, revenue) - self.constants.offer_cost) \
                - self.constants.contact_cost
        return -self.constants.contact_cost


@dataclass(frozen=True)
class TargetList:
    """One ranking, cut at capacity."""

    name: str
    note: str
    selected: list[int]

    def __len__(self) -> int:
        return len(self.selected)

    def overlap(self, other: TargetList) -> float:
        if not self.selected:
            return 0.0
        return len(set(self.selected) & set(other.selected)) / len(self.selected)


@dataclass(frozen=True)
class ListProfile:
    """What a list actually contains — reported because the profit table alone
    makes four different lists look like four numbers."""

    name: str
    churners_caught: int
    mean_revenue: float
    mean_probability: float


@dataclass(frozen=True)
class Bakeoff:
    """Every list, scored under every accounting."""

    lists: list[TargetList]
    accountings: list[Accounting]
    profit: dict[tuple[str, str], float]      # (list name, accounting name) -> realised profit
    profiles: list[ListProfile]
    capacity: int

    def best_under(self, accounting: Accounting) -> TargetList:
        return max(self.lists, key=lambda lst: self.profit[(lst.name, accounting.name)])

    @property
    def every_list_wins_under_its_own(self) -> bool:
        """Is the bake-off circular — does each accounting crown the list built
        for it? When true, the comparison is not evidence about the world; it is
        the assumption, restated as a number."""
        for accounting in self.accountings:
            built_for_this = [lst for lst in self.lists if lst.name.endswith(accounting.name)]
            if not built_for_this:
                continue
            if self.best_under(accounting).name not in {lst.name for lst in built_for_this}:
                return False
        return True

    def profile(self, name: str) -> ListProfile:
        return next(p for p in self.profiles if p.name == name)


def build_lists(probabilities: list[float], revenue: list[float],
                accountings: list[Accounting], capacity: int) -> list[TargetList]:
    """One list per accounting, plus the two lists that ignore an axis entirely."""
    n = len(probabilities)
    lists = [
        TargetList(
            name="by predicted risk",
            note="the list a churn model produces on its own",
            selected=sorted(range(n), key=lambda i: -probabilities[i])[:capacity],
        ),
    ]
    for accounting in accountings:
        lists.append(TargetList(
            name=f"by expected value, {accounting.name}",
            note=accounting.horizon.note,
            selected=sorted(
                range(n),
                key=lambda i, a=accounting: -a.expected_value(i, probabilities[i], revenue[i]),
            )[:capacity],
        ))
    lists.append(TargetList(
        name="by revenue alone",
        note="no churn model at all — rank by what the customer pays",
        selected=sorted(range(n), key=lambda i: -revenue[i])[:capacity],
    ))
    return lists


def run_bakeoff(probabilities: list[float], revenue: list[float], y: list[int],
                accountings: list[Accounting], capacity_share: float = 0.10) -> Bakeoff:
    n = len(probabilities)
    capacity = max(1, int(n * capacity_share))
    lists = build_lists(probabilities, revenue, accountings, capacity)

    profit: dict[tuple[str, str], float] = {}
    for lst in lists:
        for accounting in accountings:
            profit[(lst.name, accounting.name)] = sum(
                accounting.realised(i, y[i], revenue[i]) for i in lst.selected
            )

    profiles = [
        ListProfile(
            name=lst.name,
            churners_caught=sum(y[i] for i in lst.selected),
            mean_revenue=mean(revenue[i] for i in lst.selected),
            mean_probability=mean(probabilities[i] for i in lst.selected),
        )
        for lst in lists
    ]

    return Bakeoff(lists=lists, accountings=accountings, profit=profit,
                   profiles=profiles, capacity=capacity)
