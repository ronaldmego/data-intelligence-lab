"""The case, end to end — one link of the value chain at a time.

    product fee → billed ARPU → collected ARPU → contribution → customer value

Every earlier case in the track collapsed that whole chain into a single number:
``arpu_last3``, multiplied by a flat margin and a flat twelve months. None of
them were wrong to — a constant cannot re-order a ranking, and ranking was what
they were doing. This case is about the value itself, so each link gets priced,
and each is changed **on its own** so the effect is attributable.

Order:

1. **Refit case 02's churn model**, because the risk score is an input here.
2. **Define the base** — which invoices, over which customers.
3. **Decompose the level** — where a unit of revenue comes from, and whether
   trailing ARPU carries anything the price list does not.
4. **Decompose the movement** — the monthly bridge, with the interval that says
   whether it moved at all.
5. **Billed to collected**, and whether the shortfall is distributed.
6. **Collected to contribution**, reported as a function of the one assumption
   the answer hangs on.
7. **Contribution to value** — the horizon, and the four target lists it
   produces from the same scores.
8. **What all of it does to case 01's value axis.**

The answer key is never opened. Not out of discipline — it has nothing to say
here. ``churn_potential_outcomes`` records what a customer would have done
without the campaign, inside the same 90-day window; the question this case
cannot settle is what a *saved* customer does in the years after the data ends.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

_TRACK = Path(__file__).resolve().parents[2]
for _dependency in ("02-churn-prediction", "03-next-best-offer"):
    _path = str(_TRACK / _dependency)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from churn import run_case as run_churn_case  # noqa: E402
from churn.pipeline import CaseResult as ChurnResult  # noqa: E402

try:  # the save rate case 05 measured, published by case 03
    from nbo.value import MEASURED_SAVE_RATE
except ImportError:  # pragma: no cover - only when the sibling case is absent
    MEASURED_SAVE_RATE = 0.124

from .bridge import Bridge, build_bridge  # noqa: E402
from .collection import Collection, measure_collection  # noqa: E402
from .costs import (  # noqa: E402
    CostModel,
    CostSensitivity,
    ProductContribution,
    ServiceProfile,
    contributions,
    load_cost_model,
    plan_contributions,
    sensitivity,
)
from .data import (  # noqa: E402
    Product,
    Population,
    RevenueBase,
    Tables,
    _f,
    billing_months,
    load_products,
    load_tables,
    product_of,
    revenue_base,
    scoreable_population,
    trailing_mean,
)
from .decision import Accounting, Bakeoff, Constants, run_bakeoff  # noqa: E402
from .horizon import (  # noqa: E402
    Cancellation,
    HorizonComparison,
    cancellation,
    compare_horizons,
    flat_horizon,
    hazard_horizon,
)
from .revenue import (  # noqa: E402
    EstimatorQuality,
    RevenueSplit,
    UsageEvidence,
    VarianceSplit,
    estimator_quality,
    split_revenue,
    usage_link,
)
from .stability import AxisStability, measure_axis  # noqa: E402

REVENUE_WINDOW_MONTHS = 3      # the window case 02's `arpu_last3` uses
COLLECTION_WINDOW_MONTHS = 12  # a failure rate estimated on three invoices is noise
DEFAULT_CAP_MONTHS = 36.0
CAP_SWEEP = (12.0, 24.0, 36.0, 60.0)
# Other *constant* horizons, as the control for the per-customer one. The last
# is a stand-in for "no horizon at all": at that point the offer cost is
# negligible next to the value at risk and the ranking is p x revenue.
FLAT_SWEEP = (6.0, 24.0, 60.0, 1_000_000.0)


@dataclass(frozen=True)
class FlatPoint:
    """A different *constant* horizon, and how far its list is from case 02's.

    The control for the whole horizon section. If swapping twelve months for six
    or for a thousand moved the list as much as making it vary per customer,
    the finding would be about the number rather than about the flatness.
    """

    months: float
    overlap_with_flat: float


@dataclass(frozen=True)
class CapPoint:
    """One ceiling on expected life, and how far its list is from case 02's."""

    cap: float
    mean_months: float
    overlap_with_flat: float
    overlap_with_revenue_only: float
    churners_caught: int


@dataclass(frozen=True)
class FullModelComparison:
    """Case 02's value model against this case's, both changes at once.

    Reported *after* the one-at-a-time results and clearly marked, because a
    number produced by changing three things is a summary, not an attribution.
    """

    overlap: float
    capacity: int
    case02_mean_contribution: float
    case04_mean_contribution: float
    case02_mean_revenue: float
    case04_mean_revenue: float


@dataclass
class CaseResult:
    churn: ChurnResult
    population: Population
    products: dict[str, Product]
    profiles: list[ServiceProfile]
    cost_model: CostModel

    base: RevenueBase | None = None
    split: RevenueSplit | None = None
    variance: VarianceSplit | None = None
    usage: UsageEvidence | None = None
    estimator: EstimatorQuality | None = None
    bridge: Bridge | None = None
    collection: Collection | None = None
    plan_economics: list[ProductContribution] = field(default_factory=list)
    contribution: list[float] = field(default_factory=list)
    sensitivity: CostSensitivity | None = None
    horizons: HorizonComparison | None = None
    cancellation: Cancellation | None = None
    bakeoff: Bakeoff | None = None
    cap_sweep: list[CapPoint] = field(default_factory=list)
    flat_sweep: list[FlatPoint] = field(default_factory=list)
    full_model: FullModelComparison | None = None
    axis: AxisStability | None = None
    save_rate: float = MEASURED_SAVE_RATE
    cap_months: float = DEFAULT_CAP_MONTHS

    @property
    def cutoff(self) -> str:
        return self.population.cutoff

    @property
    def mean_contribution(self) -> float:
        return mean(self.contribution) if self.contribution else 0.0

    @property
    def value_chain(self) -> list[tuple[str, float]]:
        """The chain as a ladder of per-customer monthly figures."""
        assert self.split is not None and self.collection is not None
        fee = mean(self.products[p].monthly_fee for p in [pr.product_id for pr in self.profiles])
        billed = mean(p.billed for p in self.profiles)
        collected = mean(p.collected for p in self.profiles)
        return [
            ("product fee", fee),
            ("billed ARPU", billed),
            ("collected ARPU", collected),
            ("contribution", self.mean_contribution),
        ]


def _support_load(tables: Tables, customer_ids: list[str], months: list[str],
                  window: int) -> tuple[dict[str, float], dict[str, float]]:
    """Tickets and escalations per month over the last ``window`` months."""
    recent = set(months[-window:])
    wanted = set(customer_ids)
    tickets: dict[str, float] = defaultdict(float)
    escalations: dict[str, float] = defaultdict(float)
    for row in tables["support_interactions"]:
        if row["customer_id"] not in wanted or row["period_month"] not in recent:
            continue
        tickets[row["customer_id"]] += 1.0
        if int(_f(row["escalated"])) == 1:
            escalations[row["customer_id"]] += 1.0
    return (
        {cid: tickets[cid] / window for cid in customer_ids},
        {cid: escalations[cid] / window for cid in customer_ids},
    )


def _service_profiles(tables: Tables, population: Population, assignment: dict[str, str],
                      cutoff: str, months: list[str]) -> list[ServiceProfile]:
    """One row per customer: what they pay, what they cost to serve.

    The revenue **level** comes from the last three months, so it matches case
    02's ``arpu_last3`` exactly and the two cases cannot drift. The collection
    **rate** comes from a year, because a payment-failure rate estimated on three
    invoices is a coin flip with three sides; applying the slower rate to the
    faster level keeps the level current without pretending the rate is.
    """
    billing = defaultdict(list)
    for row in tables["billing"]:
        if row["customer_id"] in population.labels:
            billing[row["customer_id"]].append(row)
    usage = defaultdict(list)
    for row in tables["activity_monthly"]:
        if row["customer_id"] in population.labels:
            usage[row["customer_id"]].append(row)

    tickets, escalations = _support_load(tables, population.customer_ids, months, 6)
    collection_window = set(months[-COLLECTION_WINDOW_MONTHS:])

    profiles: list[ServiceProfile] = []
    for cid in population.customer_ids:
        rows = billing[cid]
        billed = trailing_mean(rows, "amount_billed", cutoff, REVENUE_WINDOW_MONTHS)
        year = [r for r in rows if r["period_month"] in collection_window]
        billed_year = sum(_f(r["amount_billed"]) for r in year)
        paid_year = sum(_f(r["amount_paid"]) for r in year)
        rate = paid_year / billed_year if billed_year else 1.0
        profiles.append(ServiceProfile(
            customer_id=cid,
            product_id=assignment[cid],
            billed=billed,
            collected=billed * rate,
            balance_k=trailing_mean(usage[cid], "balance_k", cutoff, REVENUE_WINDOW_MONTHS),
            tickets_per_month=tickets[cid],
            escalations_per_month=escalations[cid],
        ))
    return profiles


def _axis_snapshots(tables: Tables, population: Population, prior: Population,
                    months: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """Trailing ARPU at both observation cutoffs, for the customers in both."""
    shared = set(population.labels) & set(prior.labels)
    billing = defaultdict(list)
    for row in tables["billing"]:
        if row["customer_id"] in shared:
            billing[row["customer_id"]].append(row)
    before = {
        cid: trailing_mean(rows, "amount_billed", prior.cutoff, REVENUE_WINDOW_MONTHS)
        for cid, rows in billing.items()
    }
    after = {
        cid: trailing_mean(rows, "amount_billed", population.cutoff, REVENUE_WINDOW_MONTHS)
        for cid, rows in billing.items()
    }
    return before, after


def run_case(
    tables: Tables | None = None,
    cost_model: CostModel | None = None,
    save_rate: float = MEASURED_SAVE_RATE,
    cap_months: float = DEFAULT_CAP_MONTHS,
    capacity_share: float = 0.10,
) -> CaseResult:
    """Run the whole case and return every number the report needs."""
    tables = tables if tables is not None else load_tables()
    cost_model = cost_model or load_cost_model()

    churn = run_churn_case(tables, capacity_share=capacity_share)
    population = churn.test
    prior = scoreable_population(tables, "churn_labels_prior")
    products = load_products(tables)
    assignment = product_of(tables)
    months = billing_months(tables)
    cutoff = population.cutoff

    profiles = _service_profiles(tables, population, assignment, cutoff, months)
    result = CaseResult(
        churn=churn, population=population, products=products, profiles=profiles,
        cost_model=cost_model, save_rate=save_rate, cap_months=cap_months,
    )

    # --- 2. the base ------------------------------------------------------
    result.base = revenue_base(tables, population)

    # --- 3. the level -----------------------------------------------------
    result.split, result.variance = split_revenue(tables, products, assignment, cutoff)
    result.usage = usage_link(tables, products, assignment, cutoff)
    result.estimator = estimator_quality(
        measured={p.customer_id: p.billed for p in profiles},
        product_of=assignment,
        products=products,
        months_averaged=REVENUE_WINDOW_MONTHS,
        between_plan_share=result.variance.between_share,
    )

    # --- 4. the movement --------------------------------------------------
    result.bridge = build_bridge(tables, cutoff)

    # --- 5. billed to collected -------------------------------------------
    result.collection = measure_collection(
        tables, population.customer_ids, churn.probabilities, cutoff, COLLECTION_WINDOW_MONTHS,
    )

    # --- 6. collected to contribution -------------------------------------
    result.contribution = contributions(profiles, cost_model)
    result.plan_economics = plan_contributions(profiles, products, cost_model)
    result.sensitivity = sensitivity(profiles, products, cost_model)

    # --- 7. contribution to value -----------------------------------------
    constants = Constants(
        contact_cost=churn.economics.contact_cost,
        offer_cost=churn.economics.offer_cost,
        save_rate=save_rate,
        margin=churn.economics.margin,
    )
    flat_months = float(churn.economics.horizon_months)
    result.horizons = compare_horizons(churn.probabilities, flat_months, cap_months)
    result.cancellation = cancellation(churn.probabilities)

    accountings = [
        Accounting(horizon=result.horizons.flat, constants=constants),
        Accounting(horizon=result.horizons.hazard, constants=constants),
    ]
    result.bakeoff = run_bakeoff(
        churn.probabilities, churn.monthly_revenue, churn.y_test, accountings,
        capacity_share=capacity_share,
    )

    flat_list = next(lst for lst in result.bakeoff.lists if lst.name.endswith(result.horizons.flat.name))
    revenue_list = next(lst for lst in result.bakeoff.lists if lst.name == "by revenue alone")
    capacity = result.bakeoff.capacity
    n = len(churn.probabilities)
    for cap in CAP_SWEEP:
        horizon = hazard_horizon(churn.probabilities, cap)
        accounting = Accounting(horizon=horizon, constants=constants)
        order = sorted(
            range(n),
            key=lambda i, a=accounting: -a.expected_value(i, churn.probabilities[i], churn.monthly_revenue[i]),
        )[:capacity]
        result.cap_sweep.append(CapPoint(
            cap=cap,
            mean_months=horizon.mean_months,
            overlap_with_flat=len(set(order) & set(flat_list.selected)) / capacity,
            overlap_with_revenue_only=len(set(order) & set(revenue_list.selected)) / capacity,
            churners_caught=sum(churn.y_test[i] for i in order),
        ))

    # The control: other constants, in place of the per-customer horizon.
    for months in FLAT_SWEEP:
        accounting = Accounting(horizon=flat_horizon(n, months), constants=constants)
        order = sorted(
            range(n),
            key=lambda i, a=accounting: -a.expected_value(i, churn.probabilities[i], churn.monthly_revenue[i]),
        )[:capacity]
        result.flat_sweep.append(FlatPoint(
            months=months,
            overlap_with_flat=len(set(order) & set(flat_list.selected)) / capacity,
        ))

    # Both changes at once — revenue definition *and* horizon — reported last
    # and labelled, because it cannot attribute anything.
    hazard = result.horizons.hazard
    full_order = sorted(
        range(n),
        key=lambda i: -(
            churn.probabilities[i] * save_rate
            * (result.contribution[i] * constants.margin * hazard.months[i] - constants.offer_cost)
            - constants.contact_cost
        ),
    )[:capacity]
    result.full_model = FullModelComparison(
        overlap=len(set(full_order) & set(flat_list.selected)) / capacity,
        capacity=capacity,
        case02_mean_contribution=mean(result.contribution[i] for i in flat_list.selected),
        case04_mean_contribution=mean(result.contribution[i] for i in full_order),
        case02_mean_revenue=mean(churn.monthly_revenue[i] for i in flat_list.selected),
        case04_mean_revenue=mean(churn.monthly_revenue[i] for i in full_order),
    )

    # --- 8. case 01's value axis ------------------------------------------
    before, after = _axis_snapshots(tables, population, prior, months)
    result.axis = measure_axis(
        before=before,
        after=after,
        product_of=assignment,
        fees={pid: product.monthly_fee for pid, product in products.items()},
        months_apart=_months_between(prior.cutoff, population.cutoff),
        months_averaged=REVENUE_WINDOW_MONTHS,
    )

    return result


def _months_between(earlier: str, later: str) -> int:
    y0, m0 = int(earlier[:4]), int(earlier[5:7])
    y1, m1 = int(later[:4]), int(later[5:7])
    return (y1 - y0) * 12 + (m1 - m0)
