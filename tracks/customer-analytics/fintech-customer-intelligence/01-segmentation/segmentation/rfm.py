"""RFM, computed the way it is actually taught — and then measured.

RFM comes from mail-order retail, where a customer decides when to buy again.
Recency is how long ago they *chose* to come back, frequency is how often they
choose to, and monetary is what they spend when they do. All three are readings
of a decision the customer makes.

A subscription has no such decision. The invoice goes out because the company
sends it, on a schedule the company set. So this module computes the three
letters exactly as prescribed, on the transaction table, and then asks a
question the tutorials skip: **how much does each one vary, and does any of it
separate the outcome?**

The failure is not that the numbers come out wrong. It is that they come out
*fine* — a tidy quintile table, five named segments, a slide — while carrying
almost no information. Nothing errors. That is why this is measured rather than
argued.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True)
class Letter:
    """One RFM dimension, with the diagnostics that decide whether it is usable."""

    symbol: str            # R, F, M
    name: str
    definition: str        # how it was computed, in words
    short: str             # the same thing, short enough for a chart label
    values: dict[str, float]
    distinct: int
    sd: float
    modal_share: float     # share of the base sitting on the single commonest value
    churn_low: float       # churn rate of the bottom quintile, by this measure
    churn_high: float      # churn rate of the top quintile
    quintiles_separate: bool  # do the two quintiles hold different values at all?

    @property
    def spread(self) -> float:
        """Difference in churn between the extreme quintiles."""
        return abs(self.churn_high - self.churn_low)

    @property
    def readable_spread(self) -> float:
        """The spread, or zero when the quintiles are an artefact of ties.

        When every customer shares a value, sorting still produces five groups
        and they still have different churn rates — entirely from the order rows
        happened to arrive in. Reporting that number as a spread is how a
        constant becomes a finding.
        """
        return self.spread if self.quintiles_separate else 0.0

    @property
    def degenerate(self) -> bool:
        """Is this dimension a constant dressed as a measurement?"""
        return self.distinct <= 1 or self.modal_share >= 0.95


def _quintile_diagnostics(values: dict[str, float], labels: dict[str, int]) -> tuple[float, float, bool]:
    """Churn in the bottom and top fifths, and whether the fifths differ at all.

    "Differ" is judged on the *predictor*, not the outcome: if the extreme
    quintiles hold the same average value, then whatever gap appears in their
    churn rates came from the order the rows arrived in. Comparing the two means
    rather than the values at the boundary matters — a measure where four fifths
    of the base share one value still separates if the tail is real, and it
    still does not if the tail is empty.
    """
    have = [c for c in values if c in labels]
    if not have:
        return 0.0, 0.0, False
    order = sorted(have, key=lambda c: values[c])
    k = max(1, len(order) // 5)
    bottom, top = order[:k], order[-k:]
    separate = mean(values[c] for c in top) > mean(values[c] for c in bottom)
    return mean(labels[c] for c in bottom), mean(labels[c] for c in top), separate


def _letter(symbol: str, name: str, definition: str, short: str,
            values: dict[str, float], labels: dict[str, int]) -> Letter:
    series = list(values.values())
    counts = Counter(series)
    low, high, separate = _quintile_diagnostics(values, labels)
    return Letter(
        symbol=symbol,
        name=name,
        definition=definition,
        short=short,
        values=values,
        distinct=len(counts),
        sd=pstdev(series) if len(series) > 1 else 0.0,
        modal_share=max(counts.values()) / len(series) if series else 0.0,
        churn_low=low,
        churn_high=high,
        quintiles_separate=separate,
    )


def classic_rfm(
    tables: dict[str, list[dict]],
    cutoff: str,
    customer_ids: list[str],
    labels: dict[str, int],
    months: list[str],
) -> list[Letter]:
    """The three letters, computed on the billing table as prescribed.

    ``billing`` is the transaction table of a fintech: one row per customer per
    month, with an amount. It is the obvious place to point an RFM script, and
    it is what a retail-trained analyst will point one at.
    """
    wanted = set(customer_ids)
    month_index = {m: i for i, m in enumerate(months)}
    cutoff_index = month_index[cutoff]

    last_invoice: dict[str, str] = {}
    invoice_count: Counter[str] = Counter()
    spend: defaultdict[str, float] = defaultdict(float)
    for row in tables["billing"]:
        cid = row["customer_id"]
        if cid not in wanted or row["period_month"] > cutoff:
            continue
        last_invoice[cid] = max(last_invoice.get(cid, ""), row["period_month"])
        invoice_count[cid] += 1
        spend[cid] += float(row["amount_billed"])

    recency = {c: float(cutoff_index - month_index[last_invoice[c]])
               for c in customer_ids if c in last_invoice}
    frequency = {c: float(invoice_count[c]) for c in customer_ids}
    monetary = {c: spend[c] / max(1, invoice_count[c]) for c in customer_ids}

    return [
        _letter("R", "recency", "months since the customer's most recent invoice",
                "months since their last invoice", recency, labels),
        _letter("F", "frequency", "number of invoices issued to the customer",
                "invoices issued to them", frequency, labels),
        _letter("M", "monetary", "average amount billed per invoice",
                "average amount billed", monetary, labels),
    ]


def engagement_recency(
    tables: dict[str, list[dict]],
    cutoff: str,
    customer_ids: list[str],
    labels: dict[str, int],
    months: list[str],
) -> Letter:
    """Recency rebuilt on something the *customer* does.

    The repair is not a different formula, it is a different event. An app login
    is a customer choosing to show up; an invoice is the company sending one.
    Recency only ever measured the first — retail just happened to be a business
    where the two coincided.
    """
    wanted = set(customer_ids)
    month_index = {m: i for i, m in enumerate(months)}
    cutoff_index = month_index[cutoff]

    last_seen: dict[str, str] = {}
    for row in tables["digital_monthly"]:
        cid = row["customer_id"]
        if cid not in wanted or row["period_month"] > cutoff:
            continue
        if float(row["app_logins"]) > 0:
            last_seen[cid] = max(last_seen.get(cid, ""), row["period_month"])

    # A customer who has never logged in is not "recent, unknown" — they are the
    # far end of the scale. Placing them one month beyond the oldest observation
    # keeps the ordering honest without inventing a specific date.
    never = float(cutoff_index + 1)
    values = {
        c: float(cutoff_index - month_index[last_seen[c]]) if c in last_seen else never
        for c in customer_ids
    }
    return _letter("R*", "engagement recency", "months since the customer last opened the app",
                   "months since they opened the app", values, labels)


def correlation(a: dict[str, float], b: dict[str, float]) -> float:
    """Pearson correlation over the customers present in both."""
    pairs = [(a[c], b[c]) for c in a if c in b]
    if len(pairs) < 2:
        return 0.0
    mean_a, mean_b = mean(p[0] for p in pairs), mean(p[1] for p in pairs)
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in pairs)
    spread = (sum((x - mean_a) ** 2 for x, _ in pairs) * sum((y - mean_b) ** 2 for _, y in pairs)) ** 0.5
    return covariance / spread if spread else 0.0


def tenure_of(tables: dict[str, list[dict]], customer_ids: list[str]) -> dict[str, float]:
    """Months since signup, straight off the customers table."""
    wanted = set(customer_ids)
    return {r["customer_id"]: float(r["tenure_months"])
            for r in tables["customers"] if r["customer_id"] in wanted}
