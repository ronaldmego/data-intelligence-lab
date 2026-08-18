"""Where a unit of ARPU actually comes from.

A revenue decomposition is supposed to answer *which lever moves this number*.
The honest way to run it is to ask how much of the variation between customers
survives once you know their tariff — because whatever does not survive is not a
customer behaviour, it is the price list.

Two things get measured here and they point the same way:

* **the variance split**: how much of the spread in monthly invoices is between
  products rather than within them;
* **the usage link**: whether customers who use more generate more revenue —
  asked once over the whole base, and then again *inside each product*, which is
  the only version of the question that is about customers.

The second is where a revenue analysis usually goes wrong, and it does not go
wrong by erroring. It reports a positive, significant correlation.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from .data import Product, Tables, _f


def correlation(xs: list[float], ys: list[float]) -> float:
    """Pearson r. Returns 0.0 for a constant series rather than raising: a
    dimension with no variance has no correlation to report, and case 01 already
    paid for treating that case as an ordinary number."""
    if len(xs) < 3:
        return 0.0
    mx, my = mean(xs), mean(ys)
    sx, sy = pstdev(xs), pstdev(ys)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (len(xs) * sx * sy)


def correlation_se(n: int) -> float:
    """Standard error of a correlation near zero — roughly ``1/sqrt(n - 3)``.

    Reported alongside every within-product correlation because at twenty thousand
    rows a correlation of 0.02 is comfortably "significant" and worth nothing,
    and a table of bare r values invites exactly that reading.
    """
    return 1.0 / max(1.0, (n - 3)) ** 0.5


# --- the level --------------------------------------------------------------


@dataclass(frozen=True)
class RevenueSplit:
    """Billed revenue, cut into the part the tariff fixes and the part it does not."""

    invoices: int
    billed: float
    plan_fee_component: float
    overage_component: float

    @property
    def overage_share(self) -> float:
        return self.overage_component / self.billed if self.billed else 0.0

    @property
    def mean_invoice(self) -> float:
        return self.billed / self.invoices if self.invoices else 0.0


@dataclass(frozen=True)
class VarianceSplit:
    """How much of the spread in monthly invoices is explained by the tariff alone."""

    total_variance: float
    between_plan_variance: float
    n: int

    @property
    def between_share(self) -> float:
        return self.between_plan_variance / self.total_variance if self.total_variance else 0.0

    @property
    def within_share(self) -> float:
        return 1.0 - self.between_share


def split_revenue(tables: Tables, products: dict[str, Product], product_of: dict[str, str],
                  cutoff: str) -> tuple[RevenueSplit, VarianceSplit]:
    """Decompose every invoice up to ``cutoff`` into fee plus the rest."""
    amounts: list[float] = []
    fees: list[float] = []
    by_product: dict[str, list[float]] = {}
    for row in tables["billing"]:
        if row["period_month"] > cutoff:
            continue
        product = products[product_of[row["customer_id"]]]
        amount = _f(row["amount_billed"])
        amounts.append(amount)
        fees.append(product.monthly_fee)
        by_product.setdefault(product.product_id, []).append(amount)

    n = len(amounts)
    grand = mean(amounts)
    total_variance = sum((a - grand) ** 2 for a in amounts)
    between = sum(len(v) * (mean(v) - grand) ** 2 for v in by_product.values())

    return (
        RevenueSplit(
            invoices=n,
            billed=sum(amounts),
            plan_fee_component=sum(fees),
            overage_component=sum(amounts) - sum(fees),
        ),
        VarianceSplit(total_variance=total_variance, between_plan_variance=between, n=n),
    )


# --- the usage link ---------------------------------------------------------


@dataclass(frozen=True)
class UsageLink:
    """One reading of *"do heavy users pay more?"* — over a stated set of rows."""

    scope: str            # "all products" or a product_id
    n: int
    r: float

    @property
    def standard_error(self) -> float:
        return correlation_se(self.n)

    @property
    def readable(self) -> bool:
        """Is the correlation bigger than twice its own sampling noise?"""
        return abs(self.r) > 2.0 * self.standard_error


@dataclass(frozen=True)
class UsageEvidence:
    """The aggregate reading, and the same reading inside each product."""

    overall: UsageLink
    by_product: list[UsageLink]

    @property
    def largest_within(self) -> UsageLink:
        return max(self.by_product, key=lambda link: abs(link.r))

    @property
    def ratio(self) -> float:
        """How many times bigger the aggregate correlation is than the biggest
        within-product one. The number that says the aggregate is composition."""
        largest = abs(self.largest_within.r)
        return abs(self.overall.r) / largest if largest else float("inf")

    @property
    def within_readable(self) -> list[UsageLink]:
        return [link for link in self.by_product if link.readable]


def usage_link(tables: Tables, products: dict[str, Product], product_of: dict[str, str],
               cutoff: str) -> UsageEvidence:
    """Correlate the non-fee part of each invoice with that month's data usage.

    Aggregated first — which is how the question is asked in a meeting — and then
    within each tariff, which is the only version that could be about a customer
    rather than about which product they bought.
    """
    usage = {
        (row["customer_id"], row["period_month"]): _f(row["balance_k"])
        for row in tables["activity_monthly"]
        if row["period_month"] <= cutoff
    }

    overage: list[float] = []
    balances: list[float] = []
    product_ids: list[str] = []
    for row in tables["billing"]:
        if row["period_month"] > cutoff:
            continue
        key = (row["customer_id"], row["period_month"])
        if key not in usage:
            continue
        product = products[product_of[row["customer_id"]]]
        overage.append(_f(row["amount_billed"]) - product.monthly_fee)
        balances.append(usage[key])
        product_ids.append(product.product_id)

    by_product: list[UsageLink] = []
    for product_id in sorted(products, key=lambda p: products[p].monthly_fee):
        idx = [i for i, p in enumerate(product_ids) if p == product_id]
        if len(idx) < 3:
            continue
        by_product.append(UsageLink(
            scope=product_id,
            n=len(idx),
            r=correlation([overage[i] for i in idx], [balances[i] for i in idx]),
        ))

    return UsageEvidence(
        overall=UsageLink(scope="all products", n=len(overage), r=correlation(overage, balances)),
        by_product=by_product,
    )


# --- ARPU as an estimator ---------------------------------------------------


@dataclass(frozen=True)
class PlanNoise:
    """How far a product's measured ARPU wanders from the price the customer signed."""

    product_id: str
    monthly_fee: float
    customers: int
    measured_mean: float
    measured_sd: float

    @property
    def relative_sd(self) -> float:
        return self.measured_sd / self.measured_mean if self.measured_mean else 0.0


@dataclass(frozen=True)
class EstimatorQuality:
    """Trailing ARPU, judged as what it is: an estimate of a known number."""

    months_averaged: int
    per_plan: list[PlanNoise]
    distinct_true_values: int
    between_plan_share: float

    @property
    def worst(self) -> PlanNoise:
        return max(self.per_plan, key=lambda p: p.relative_sd)

    @property
    def mean_relative_sd(self) -> float:
        return mean(p.relative_sd for p in self.per_plan)


def estimator_quality(measured: dict[str, float], product_of: dict[str, str],
                      products: dict[str, Product], months_averaged: int,
                      between_plan_share: float) -> EstimatorQuality:
    """Compare each customer's measured ARPU against their own tariff.

    The comparison is only meaningful because this world charges a flat fee plus
    a term that is unrelated to usage — which :func:`usage_link` establishes
    rather than assumes. Where usage-based charging is real, trailing ARPU
    carries information the price list does not, and this section would say the
    opposite.
    """
    per_plan: list[PlanNoise] = []
    for product_id in sorted(products, key=lambda p: products[p].monthly_fee):
        values = [v for cid, v in measured.items() if product_of.get(cid) == product_id]
        if len(values) < 2:
            continue
        per_plan.append(PlanNoise(
            product_id=product_id,
            monthly_fee=products[product_id].monthly_fee,
            customers=len(values),
            measured_mean=mean(values),
            measured_sd=pstdev(values),
        ))
    return EstimatorQuality(
        months_averaged=months_averaged,
        per_plan=per_plan,
        distinct_true_values=len({products[p].monthly_fee for p in products}),
        between_plan_share=between_plan_share,
    )
