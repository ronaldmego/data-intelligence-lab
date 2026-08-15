"""Feature building — where leakage is either prevented or introduced.

Every fact this module reads passes through :func:`_before`, which drops
anything dated after the observation cutoff. That is the whole no-leakage
guarantee, in one place, so it can be read in ten seconds and tested directly
rather than argued about across a notebook.

Features are built **as of a cutoff**, never "as of now". The same code path
produces the training matrix at the earlier cutoff and the scoring matrix at the
later one, which is what makes the out-of-time comparison honest: if a feature
secretly needed the future, it would break at both cutoffs, not just one.
"""

from __future__ import annotations

from collections import defaultdict

FEATURE_NAMES: tuple[str, ...] = (
    # lifecycle
    "tenure_months",
    "is_early_life",
    # usage trajectory
    "balance_last3",
    "usage_trend",
    "active_days_last3",
    # payment behaviour
    "payment_problem_rate",
    "failed_invoices_last6",
    "avg_days_late_last6",
    "arpu_last3",
    # support experience
    "tickets_last6",
    "unresolved_escalations",
    "has_unresolved_escalation",
    # digital engagement
    "app_logins_last3",
    "self_service_last3",
    # product fit
    "monthly_fee",
    "is_prepaid",
    "product_tier",
    "limit_headroom",
    # commercial history
    "retention_offer_taken",
)


def _f(value: object, default: float = 0.0) -> float:
    """Coerce to float, tolerating both native values and CSV strings."""
    if value is None or value == "":
        return default
    return float(value)  # type: ignore[arg-type]


def _before(rows: list[dict], cutoff: str, field: str = "period_month") -> list[dict]:
    """Drop every fact dated after the cutoff.

    ISO dates sort lexicographically, so a string comparison is exact here and
    avoids parsing 300k rows into date objects for nothing.
    """
    return [r for r in rows if r[field] <= cutoff]


def _group(rows: list[dict], key: str = "customer_id") -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def _month_calendar(tables: dict[str, list[dict]]) -> list[str]:
    """Month index -> ISO month start, derived from the data itself.

    The campaigns table dates itself by ``month_index``, not by a date. Rather
    than re-deriving the generator's calendar anchor (and coupling this case to
    it), read the calendar off the observed months.
    """
    return sorted({r["period_month"] for r in tables["activity_monthly"]})


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _last_n(rows: list[dict], n: int) -> list[dict]:
    """The most recent ``n`` monthly rows, oldest first."""
    return sorted(rows, key=lambda r: r["period_month"])[-n:]


def build_features(
    tables: dict[str, list[dict]],
    cutoff: str,
    customer_ids: list[str],
) -> list[list[float]]:
    """Build the feature matrix for ``customer_ids`` as of ``cutoff``.

    Returns one row per customer, in the order given, with columns in
    :data:`FEATURE_NAMES` order.
    """
    wanted = set(customer_ids)

    usage = _group([r for r in _before(tables["activity_monthly"], cutoff) if r["customer_id"] in wanted])
    billing = _group([r for r in _before(tables["billing"], cutoff) if r["customer_id"] in wanted])
    digital = _group([r for r in _before(tables["digital_monthly"], cutoff) if r["customer_id"] in wanted])
    support = _group([r for r in _before(tables["support_interactions"], cutoff) if r["customer_id"] in wanted])

    products = {r["product_id"]: r for r in tables["products"]}
    customers = {r["customer_id"]: r for r in tables["customers"] if r["customer_id"] in wanted}

    # A retention offer taken *at or before* the cutoff is legitimate history,
    # not leakage: the campaign ran, the customer accepted, and that happened
    # before the model is asked to predict anything. Campaigns after the cutoff
    # are dropped — including them would be predicting churn with a treatment
    # the customer had not yet received.
    calendar = _month_calendar(tables)
    campaign_month = {
        r["campaign_id"]: calendar[min(int(r["month_index"]), len(calendar) - 1)]
        for r in tables["campaigns"]
    }
    retention_campaigns = {
        r["campaign_id"] for r in tables["campaigns"]
        if r["objective"] == "retention" and campaign_month[r["campaign_id"]] <= cutoff
    }
    took_retention_offer = {
        r["customer_id"] for r in tables["campaign_exposures"]
        if r["campaign_id"] in retention_campaigns and int(r["responded"]) == 1
    }

    matrix: list[list[float]] = []
    for cid in customer_ids:
        cust = customers[cid]
        product = products[cust["current_product_id"]]

        u_all = usage.get(cid, [])
        b_all = billing.get(cid, [])
        d_all = digital.get(cid, [])
        s_all = support.get(cid, [])

        months_observed = max(1, len(b_all))
        tenure = float(len(u_all))

        # --- usage trajectory: level, and the trend that drives churn --------
        u_last3 = _last_n(u_all, 3)
        u_prior3 = _last_n(u_all[: max(0, len(u_all) - 3)], 3) if len(u_all) > 3 else []
        bal_last3 = _mean([_f(r["balance_k"]) for r in u_last3])
        bal_prior3 = _mean([_f(r["balance_k"]) for r in u_prior3])
        # Ratio of recent to previous usage. 1.0 = flat; < 1 = declining. Held
        # at 1.0 when there is no prior period rather than inventing a decline.
        usage_trend = min(3.0, bal_last3 / bal_prior3) if bal_prior3 > 0.01 else 1.0

        # --- payment behaviour ------------------------------------------------
        problems = sum(1.0 if r["status"] == "failed" else 0.5 if r["status"] == "late" else 0.0 for r in b_all)
        b_last6 = _last_n(b_all, 6)

        # --- support ----------------------------------------------------------
        unresolved = sum(1 for r in s_all if int(r["escalated"]) == 1 and int(r["resolved"]) == 0)
        recent_months = {r["period_month"] for r in _last_n(u_all, 6)}
        tickets_last6 = sum(1 for r in s_all if r["period_month"] in recent_months)

        # --- product fit ---------------------------------------------------------
        cap = _f(product["credit_limit_k"], 1.0) or 1.0
        headroom = (cap - bal_last3) / cap

        matrix.append([
            tenure,
            1.0 if tenure <= 6 else 0.0,
            bal_last3,
            usage_trend,
            _mean([_f(r["active_days"]) for r in u_last3]),
            problems / months_observed,
            float(sum(1 for r in b_last6 if r["status"] == "failed")),
            _mean([_f(r["days_late"]) for r in b_last6]),
            _mean([_f(r["amount_billed"]) for r in _last_n(b_all, 3)]),
            float(tickets_last6),
            float(unresolved),
            1.0 if unresolved > 0 else 0.0,
            _mean([_f(r["app_logins"]) for r in _last_n(d_all, 3)]),
            _mean([_f(r["self_service_actions"]) for r in _last_n(d_all, 3)]),
            _f(product["monthly_fee"]),
            1.0 if product["family"] == "prepaid" else 0.0,
            _f(product["tier"]),
            headroom,
            1.0 if cid in took_retention_offer else 0.0,
        ])

    return matrix


def build_leaky_feature(tables: dict[str, list[dict]], label_table: str, customer_ids: list[str]) -> list[float]:
    """A deliberately poisoned feature, for the contrast section of the report.

    ``churn_date`` is a *post-outcome* fact: it exists only because the customer
    churned. Deriving anything from it — "days until churn", "has a churn date",
    or a downstream field computed after the fact — hands the model the answer.
    This function exists to quantify what that looks like, because the failure
    mode is not a crash: it is a metric that looks wonderful.
    """
    churn_date = {r["customer_id"]: r["churn_date"] for r in tables[label_table]}
    return [1.0 if churn_date.get(cid) else 0.0 for cid in customer_ids]
