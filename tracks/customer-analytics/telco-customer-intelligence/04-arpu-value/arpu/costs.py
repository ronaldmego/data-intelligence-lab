"""Collected revenue is not contribution — and the difference is an assumption.

Case 03 moved the contact policy into the data model because a policy living in
the analyst's script is not a policy, it is a preference. A cost-to-serve model
has the same problem and one worse property: it is *invisible*. A contact rule
that is wrong gets argued about by the people it blocks; a marginal cost per
gigabyte that is wrong just quietly re-orders a customer list, and the list looks
exactly the same.

So the unit costs live in ``cost_model.csv`` beside the case, not in this file —
diffable, reviewable by whoever owns them, and changeable without touching code.
They stay in the case rather than in the data model for one reason: they are not
facts about the world, they are this business's finance assumptions, and only
this case consumes them. The moment a second case does, they move.

The conclusions are then reported **as a function of the number nobody owns**,
which is the only honest way to publish a result that depends on it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .data import Plan

COST_MODEL = Path(__file__).resolve().parent.parent / "cost_model.csv"


@dataclass(frozen=True)
class UnitCost:
    """One line of the cost model, as it is written down."""

    cost_id: str
    driver: str
    value: float
    unit: str
    rationale: str


@dataclass(frozen=True)
class CostModel:
    """The declared unit economics, keyed by driver."""

    lines: list[UnitCost]

    def _value(self, driver: str) -> float:
        for line in self.lines:
            if line.driver == driver:
                return line.value
        raise KeyError(f"cost model has no line for driver {driver!r}")

    @property
    def per_line(self) -> float:
        return self._value("per_subscriber_month")

    @property
    def per_gb(self) -> float:
        return self._value("per_gb_carried")

    @property
    def per_ticket(self) -> float:
        return self._value("per_support_ticket")

    @property
    def per_escalation(self) -> float:
        return self._value("per_escalated_ticket")

    def with_per_gb(self, value: float) -> CostModel:
        """The same model at a different marginal data cost — for the sweep."""
        return CostModel(lines=[
            UnitCost(line.cost_id, line.driver, value, line.unit, line.rationale)
            if line.driver == "per_gb_carried" else line
            for line in self.lines
        ])

    def cost_to_serve(self, gb: float, tickets: float, escalations: float) -> float:
        """Monthly cost of serving one customer, at their observed usage and support load."""
        return (
            self.per_line
            + self.per_gb * gb
            + self.per_ticket * tickets
            + self.per_escalation * escalations
        )


def load_cost_model(path: Path | str = COST_MODEL) -> CostModel:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return CostModel(lines=[
            UnitCost(
                cost_id=row["cost_id"],
                driver=row["driver"],
                value=float(row["value"]),
                unit=row["unit"],
                rationale=row["rationale"],
            )
            for row in csv.DictReader(fh)
        ])


# --- what a customer is worth per month -------------------------------------


@dataclass(frozen=True)
class ServiceProfile:
    """The observable drivers of one customer's monthly cost."""

    customer_id: str
    plan_id: str
    billed: float
    collected: float
    data_gb: float
    tickets_per_month: float
    escalations_per_month: float


def contributions(profiles: list[ServiceProfile], model: CostModel) -> list[float]:
    return [
        p.collected - model.cost_to_serve(p.data_gb, p.tickets_per_month, p.escalations_per_month)
        for p in profiles
    ]


@dataclass(frozen=True)
class PlanContribution:
    """A tariff's average economics, at one marginal data cost."""

    plan_id: str
    monthly_fee: float
    customers: int
    collected: float
    data_gb: float
    support_cost: float
    contribution: float

    def at_per_gb(self, per_gb: float, per_line: float) -> float:
        """Mean contribution if the marginal gigabyte cost were ``per_gb``.

        Contribution is linear in that number, so this is exact rather than a
        re-run — which is what lets the crossing points below be solved instead
        of searched for.
        """
        return self.collected - per_line - self.support_cost - per_gb * self.data_gb


def plan_contributions(profiles: list[ServiceProfile], plans: dict[str, Plan],
                       model: CostModel) -> list[PlanContribution]:
    rows: list[PlanContribution] = []
    for plan_id in sorted(plans, key=lambda p: plans[p].monthly_fee):
        members = [p for p in profiles if p.plan_id == plan_id]
        if not members:
            continue
        support = mean(
            model.per_ticket * p.tickets_per_month + model.per_escalation * p.escalations_per_month
            for p in members
        )
        collected = mean(p.collected for p in members)
        gb = mean(p.data_gb for p in members)
        rows.append(PlanContribution(
            plan_id=plan_id,
            monthly_fee=plans[plan_id].monthly_fee,
            customers=len(members),
            collected=collected,
            data_gb=gb,
            support_cost=support,
            contribution=collected - model.cost_to_serve(gb, 0.0, 0.0) - support,
        ))
    return rows


# --- the number nobody owns -------------------------------------------------


def _crossing(a: PlanContribution, b: PlanContribution) -> float | None:
    """The marginal data cost at which two plans are equally profitable.

    The fixed per-line cost is the same for both and cancels, so it does not
    appear: where two tariffs cross depends only on what they collect, what
    their customers cost in support, and how much data they carry.
    """
    denominator = a.data_gb - b.data_gb
    if abs(denominator) < 1e-9:
        return None
    numerator = (a.collected - a.support_cost) - (b.collected - b.support_cost)
    crossing = numerator / denominator
    return crossing if crossing > 0 else None


@dataclass(frozen=True)
class SweepPoint:
    """One marginal data cost, and what the analysis would conclude at it."""

    per_gb: float
    mean_contribution: float
    negative_customers: int
    top_third_overlap: float     # against the same third ranked by ARPU
    best_plan: str
    worst_plan: str


@dataclass(frozen=True)
class CostSensitivity:
    """Where the conclusion changes, expressed in the units of the assumption."""

    declared_per_gb: float
    points: list[SweepPoint]
    overtaken_per_gb: float | None    # top-fee plan stops being the most profitable
    overtaken_by: str | None
    inversion_per_gb: float | None    # top-fee plan falls below the cheapest
    ruin_per_gb: float | None         # top-fee plan stops covering its own cost
    top_plan: str
    cheapest_plan: str

    def at(self, per_gb: float) -> SweepPoint:
        return min(self.points, key=lambda p: abs(p.per_gb - per_gb))


def sensitivity(profiles: list[ServiceProfile], plans: dict[str, Plan], model: CostModel,
                grid: list[float] | None = None) -> CostSensitivity:
    """Re-price the base across a range of marginal data costs.

    The declared value answers *what is a customer worth today*; the sweep
    answers the question that actually matters when the number is an assumption:
    *how wrong would it have to be for this to be the wrong answer?*
    """
    grid = grid if grid is not None else [round(0.02 * i, 2) for i in range(26)]
    arpu_order = sorted(range(len(profiles)), key=lambda i: -profiles[i].collected)
    third = max(1, len(profiles) // 3)
    top_by_arpu = set(arpu_order[:third])

    points: list[SweepPoint] = []
    for per_gb in grid:
        variant = model.with_per_gb(per_gb)
        values = contributions(profiles, variant)
        order = sorted(range(len(profiles)), key=lambda i: -values[i])
        by_plan = plan_contributions(profiles, plans, variant)
        points.append(SweepPoint(
            per_gb=per_gb,
            mean_contribution=mean(values),
            negative_customers=sum(1 for v in values if v < 0),
            top_third_overlap=len(top_by_arpu & set(order[:third])) / third,
            best_plan=max(by_plan, key=lambda p: p.contribution).plan_id,
            worst_plan=min(by_plan, key=lambda p: p.contribution).plan_id,
        ))

    rows = plan_contributions(profiles, plans, model)
    top = max(rows, key=lambda p: p.monthly_fee)
    cheapest = min(rows, key=lambda p: p.monthly_fee)
    ruin = None
    if top.data_gb > 0:
        candidate = (top.collected - model.per_line - top.support_cost) / top.data_gb
        ruin = candidate if candidate > 0 else None

    # The first rival to overtake the flagship, solved rather than found on the
    # sweep grid — a threshold reported to the cent should not be an artefact of
    # how finely the sweep happened to be sampled.
    crossings = [
        (crossing, other.plan_id)
        for other in rows if other.plan_id != top.plan_id
        for crossing in [_crossing(top, other)] if crossing is not None
    ]
    overtaken, overtaken_by = min(crossings, default=(None, None))

    return CostSensitivity(
        declared_per_gb=model.per_gb,
        points=points,
        overtaken_per_gb=overtaken,
        overtaken_by=overtaken_by,
        inversion_per_gb=_crossing(top, cheapest),
        ruin_per_gb=ruin,
        top_plan=top.plan_id,
        cheapest_plan=cheapest.plan_id,
    )
