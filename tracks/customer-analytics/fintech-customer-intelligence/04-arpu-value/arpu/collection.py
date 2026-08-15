"""Billed is not collected — and the question is whether that changes anyone's rank.

The gap itself is easy: sum what was invoiced, sum what was paid, subtract. The
part worth an analysis is whether the gap is *distributed*. A uniform shortfall
is a level correction — apply it once, move on. A shortfall concentrated in the
customers a retention programme is about would mean every value figure in the
track over-states exactly the population it is spent on.

This module was written expecting the second. The data model gives failed
invoices to price-sensitive customers, and payment problems raise churn odds, so
the two ought to travel together. Whether they do at a level a *model* can see is
the measurement, not the premise — and the report states the answer either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from .data import Tables, _f
from .revenue import correlation


@dataclass(frozen=True)
class Decile:
    """One tenth of the base, ordered by predicted churn risk."""

    rank: int                # 1 = lowest risk
    customers: int
    mean_risk: float
    collection_rate: float
    collection_se: float
    mean_billed: float


@dataclass(frozen=True)
class Fold:
    """The same correlation, measured on one slice of the same base.

    Five folds of one population is a cheaper and sharper stability check than
    five seeds: the data-generating process is held fixed, so anything the folds
    disagree about is sampling noise and nothing else. If the sign is not even
    stable *inside* one world, quoting it from one is not a finding.
    """

    rank: int
    n: int
    r: float

    @property
    def standard_error(self) -> float:
        return 1.0 / max(1.0, (self.n - 3)) ** 0.5

    @property
    def readable(self) -> bool:
        return abs(self.r) > 2.0 * self.standard_error


@dataclass(frozen=True)
class Collection:
    """The billed-to-collected gap, and its distribution across risk."""

    months: int
    billed: float
    collected: float
    invoices: int
    settled_in_service_month: int
    settled_invoices: int
    deciles: list[Decile]
    risk_correlation: float
    n_customers: int
    folds: list[Fold]

    @property
    def fold_range(self) -> tuple[float, float]:
        return min(f.r for f in self.folds), max(f.r for f in self.folds)

    @property
    def fold_sign_changes(self) -> int:
        """How many times the sign flips between consecutive folds."""
        signs = [f.r >= 0 for f in self.folds]
        return sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)

    @property
    def sign_is_stable(self) -> bool:
        return all(f.r >= 0 for f in self.folds) or all(f.r < 0 for f in self.folds)

    @property
    def readable_folds(self) -> int:
        return sum(1 for f in self.folds if f.readable)

    @property
    def loss_rate(self) -> float:
        return 1.0 - self.collected / self.billed if self.billed else 0.0

    @property
    def same_month_share(self) -> float:
        return self.settled_in_service_month / self.settled_invoices if self.settled_invoices else 0.0

    @property
    def spread(self) -> float:
        """Highest minus lowest decile collection rate."""
        rates = [d.collection_rate for d in self.deciles]
        return max(rates) - min(rates)

    @property
    def spread_se(self) -> float:
        top = max(self.deciles, key=lambda d: d.collection_rate)
        bottom = min(self.deciles, key=lambda d: d.collection_rate)
        return (top.collection_se ** 2 + bottom.collection_se ** 2) ** 0.5

    @property
    def monotone(self) -> bool:
        rates = [d.collection_rate for d in self.deciles]
        return all(a <= b for a, b in zip(rates, rates[1:], strict=False)) or \
            all(a >= b for a, b in zip(rates, rates[1:], strict=False))

    @property
    def risk_correlation_se(self) -> float:
        return 1.0 / max(1.0, (self.n_customers - 3)) ** 0.5

    @property
    def concentrates_in_risk(self) -> bool:
        """Is the shortfall bigger for high-risk customers, readably?"""
        return self.risk_correlation < -2.0 * self.risk_correlation_se


def measure_collection(tables: Tables, customer_ids: list[str], risk: list[float],
                       cutoff: str, months: int = 12, folds: int = 5) -> Collection:
    """Collection over the last ``months`` invoiced months, split by predicted risk.

    ``folds`` slices the population by stride — no RNG, so the split is
    byte-reproducible on any machine, the same device cases 01 and 02 use — and
    re-measures the correlation on each slice.
    """
    all_months = sorted({r["period_month"] for r in tables["billing"] if r["period_month"] <= cutoff})
    window = set(all_months[-months:])

    billed: dict[str, float] = {}
    collected: dict[str, float] = {}
    invoices = same_month = settled = 0
    for row in tables["billing"]:
        if row["period_month"] not in window:
            continue
        cid = row["customer_id"]
        billed[cid] = billed.get(cid, 0.0) + _f(row["amount_billed"])
        collected[cid] = collected.get(cid, 0.0) + _f(row["amount_paid"])
        invoices += 1
        if row["paid_date"]:
            settled += 1
            if row["paid_date"][:7] == row["period_month"][:7]:
                same_month += 1

    rate = [
        (collected.get(cid, 0.0) / billed[cid]) if billed.get(cid) else 1.0
        for cid in customer_ids
    ]

    order = sorted(range(len(customer_ids)), key=lambda i: risk[i])
    n = len(order)
    deciles: list[Decile] = []
    for d in range(10):
        idx = order[d * n // 10:(d + 1) * n // 10]
        if not idx:
            continue
        rates = [rate[i] for i in idx]
        deciles.append(Decile(
            rank=d + 1,
            customers=len(idx),
            mean_risk=mean(risk[i] for i in idx),
            collection_rate=mean(rates),
            collection_se=pstdev(rates) / len(rates) ** 0.5 if len(rates) > 1 else 0.0,
            mean_billed=mean(billed.get(customer_ids[i], 0.0) for i in idx) / months,
        ))

    scoped_billed = sum(billed.get(cid, 0.0) for cid in customer_ids)
    scoped_collected = sum(collected.get(cid, 0.0) for cid in customer_ids)

    slices = [
        [i for i in range(n) if i % folds == f]
        for f in range(folds)
    ]
    fold_rows = [
        Fold(rank=f + 1, n=len(idx),
             r=correlation([risk[i] for i in idx], [rate[i] for i in idx]))
        for f, idx in enumerate(slices) if len(idx) > 3
    ]

    return Collection(
        months=months,
        billed=scoped_billed,
        collected=scoped_collected,
        invoices=invoices,
        settled_in_service_month=same_month,
        settled_invoices=settled,
        deciles=deciles,
        risk_correlation=correlation(risk, rate),
        n_customers=n,
        folds=fold_rows,
    )
