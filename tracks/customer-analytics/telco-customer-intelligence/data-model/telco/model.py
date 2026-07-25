"""Synthetic telco customer-intelligence data model.

A deterministic, seeded generator that emits ~12 related tables with an
**explicit causal structure**. The point of modelling the causality — rather
than sprinkling random labels — is that the downstream cases become real:

* churn is *caused* by observable trajectories (usage decline, payment
  problems, unresolved support, weak engagement) plus unobserved satisfaction
  and noise, so a churn model can recover signal but never fit perfectly and
  never leaks;
* retention campaigns carry a *true* uplift, but are *targeted at high-risk
  customers*, so the naive "responders churn less" read is confounded — which
  is exactly what the incrementality case has to untangle.

Pure standard library on purpose: no numpy/pandas. The output is plain CSV that
anyone can diff, and CI can validate without installing project dependencies.
Every value is synthetic — see ``DATA_CARD.md``. No employer data is used.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from random import Random

from .config import Config

# --- Reference dimensions (small, fixed) ---------------------------------

PLANS = [
    # plan_id, name, family, monthly_fee, data_gb, voice_min, tier
    ("PP_S", "Prepaid S", "prepaid", 8.0, 3, 200, 1),
    ("PP_M", "Prepaid M", "prepaid", 12.0, 8, 400, 2),
    ("PP_L", "Prepaid L", "prepaid", 18.0, 20, 800, 3),
    ("PO_S", "Postpaid S", "postpaid", 20.0, 15, 600, 2),
    ("PO_M", "Postpaid M", "postpaid", 30.0, 40, 1200, 3),
    ("PO_L", "Postpaid L", "postpaid", 45.0, 100, 3000, 4),
    ("PO_XL", "Postpaid XL", "postpaid", 65.0, 300, 5000, 5),
]

OFFERS = [
    # offer_id, name, type, value, eligible_family
    ("OF_DISC10", "10% loyalty discount", "discount", 0.10, "any"),
    ("OF_DATA5", "+5 GB data bundle", "data_bundle", 5, "any"),
    ("OF_UP_M", "Upgrade to M", "upgrade", 1, "any"),
    ("OF_UP_L", "Upgrade to L", "upgrade", 1, "postpaid"),
    ("OF_WAIVE", "Late-fee waiver", "discount", 0.05, "any"),
]

CAMPAIGNS = [
    # campaign_id, name, channel, objective, offer_id, month_index
    ("CMP_RET_Q1", "Q1 Retention Save", "call", "retention", "OF_DISC10", 5),
    ("CMP_RET_Q3", "Q3 Retention Save", "sms", "retention", "OF_WAIVE", 17),
    ("CMP_UP_MID", "Mid-year Upsell", "email", "upsell", "OF_UP_M", 11),
    ("CMP_XSELL", "Data Cross-sell", "push", "crosssell", "OF_DATA5", 14),
]

REGIONS = [
    ("North", 0.28),
    ("Central", 0.34),
    ("South", 0.22),
    ("Coast", 0.16),
]
ACQ_CHANNELS = [
    ("retail_store", 0.34),
    ("online", 0.30),
    ("call_center", 0.14),
    ("reseller", 0.14),
    ("referral", 0.08),
]
AGE_BANDS = [("18-24", 0.18), ("25-34", 0.30), ("35-44", 0.24), ("45-59", 0.19), ("60+", 0.09)]
CONSENT_CHANNELS = ("email", "sms", "push", "call")
TICKET_REASONS = ("billing", "coverage", "device", "plan_change", "roaming", "other")

_PLAN_BY_ID = {p[0]: p for p in PLANS}


# --- Small helpers --------------------------------------------------------


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _weighted(rng: Random, items: list[tuple]) -> tuple:
    """Pick one (value, weight) pair by weight and return the value part(s)."""
    r = rng.random()
    acc = 0.0
    for item in items:
        acc += item[-1]
        if r <= acc:
            return item
    return items[-1]


def _month_start(cfg: Config, idx: int) -> date:
    y = cfg.start_year + (cfg.start_month_of_year - 1 + idx) // 12
    m = (cfg.start_month_of_year - 1 + idx) % 12 + 1
    return date(y, m, 1)


# --- Per-customer latent world -------------------------------------------


class _Customer:
    """The full latent + observed state of one customer, held in memory while
    the row-level tables are emitted. Latent fields never reach the CSVs."""

    __slots__ = (
        "cid", "signup_idx", "region", "acq_channel", "age_band",
        "plan_id", "family", "contract_type",
        "satisfaction", "price_sensitivity", "engagement_level", "plan_fit",
        "usage_base", "usage_decline", "active_from", "active_to",
        # accumulated observed scores used by the churn model
        "payment_problem_score", "unresolved_support_score",
        "retention_response", "targeted_risk_at_selection",
        # ...and the same scores *time-stamped*, so the risk proxy can be
        # evaluated at any cutoff rather than only at the end of the window.
        # This is bookkeeping only: it consumes no randomness, so adding it
        # leaves the generated tables byte-for-byte unchanged.
        "payment_problem_events", "unresolved_support_events",
        "retention_response_events",
    )

    def __init__(self, cid: str):
        self.cid = cid
        self.payment_problem_score = 0.0
        self.unresolved_support_score = 0.0
        self.retention_response = 0
        self.targeted_risk_at_selection = 0.0
        self.payment_problem_events: list[tuple[int, float]] = []  # (month_idx, weight)
        self.unresolved_support_events: list[int] = []  # month indices
        self.retention_response_events: list[int] = []  # campaign month indices


def _make_customers(cfg: Config, rng: Random) -> list[_Customer]:
    customers: list[_Customer] = []
    for i in range(cfg.n_customers):
        c = _Customer(f"C{i:06d}")

        # Signup skewed towards older tenure: more customers joined before the
        # window opened (signup_idx negative) so tenure varies realistically.
        c.signup_idx = int(rng.triangular(-36, cfg.n_months - 1, -6))
        c.active_from = max(0, c.signup_idx)

        c.region = _weighted(rng, REGIONS)[0]
        c.acq_channel = _weighted(rng, ACQ_CHANNELS)[0]
        c.age_band = _weighted(rng, AGE_BANDS)[0]

        family = "prepaid" if rng.random() < cfg.prepaid_share else "postpaid"
        plan = rng.choice([p for p in PLANS if p[2] == family])
        c.plan_id = plan[0]
        c.family = family
        c.contract_type = family

        # Latent traits (never written out).
        c.satisfaction = rng.gauss(0.0, 1.0)
        c.price_sensitivity = _clamp(rng.gauss(0.0, 1.0), -3, 3)
        c.engagement_level = _clamp(rng.gauss(0.0, 1.0), -3, 3)
        c.plan_fit = _clamp(rng.gauss(0.4, 0.8), -3, 3)  # slightly positive on avg

        # Usage baseline scaled by plan tier, with an individual multiplier.
        tier = plan[6]
        c.usage_base = max(0.2, rng.gauss(0.4 + 0.18 * tier, 0.5))
        # Some customers drift down over the window (an observable churn cause).
        c.usage_decline = _clamp(rng.gauss(0.0, 0.5) - 0.15, -1.5, 1.0)

        c.active_to = cfg.n_months - 1  # all history is pre-cutoff; churn is future
        customers.append(c)
    return customers


# --- Table emitters -------------------------------------------------------


def _emit_reference() -> dict[str, list[dict]]:
    plans = [
        dict(plan_id=p[0], name=p[1], family=p[2], monthly_fee=p[3],
             data_gb=p[4], voice_min=p[5], tier=p[6])
        for p in PLANS
    ]
    offers = [
        dict(offer_id=o[0], name=o[1], type=o[2], value=o[3], eligible_family=o[4])
        for o in OFFERS
    ]
    campaigns = [
        dict(campaign_id=c[0], name=c[1], channel=c[2], objective=c[3],
             offer_id=c[4], month_index=c[5])
        for c in CAMPAIGNS
    ]
    return {"plans": plans, "offers": offers, "campaigns": campaigns}


def _emit_customers_and_subscriptions(cfg: Config, customers: list[_Customer]):
    cust_rows, sub_rows = [], []
    for c in customers:
        signup = _month_start(cfg, c.signup_idx)
        tenure = cfg.n_months - c.active_from  # months observed in window
        cust_rows.append(dict(
            customer_id=c.cid,
            signup_date=signup.isoformat(),
            region=c.region,
            acquisition_channel=c.acq_channel,
            age_band=c.age_band,
            contract_type=c.contract_type,
            current_plan_id=c.plan_id,
            tenure_months=tenure,
        ))
        sub_rows.append(dict(
            subscription_id=f"S{c.cid[1:]}_0",
            customer_id=c.cid,
            plan_id=c.plan_id,
            start_date=signup.isoformat(),
            end_date="",  # still active at cutoff; churn happens after
            status="active",
        ))
    return cust_rows, sub_rows


def _emit_usage(cfg: Config, customers: list[_Customer], rng: Random):
    """Customer x month usage. Aggregated to *monthly* grain on purpose: churn,
    ARPU and RFM are modelled monthly, and daily would bloat the CSVs without
    adding analytical value. The schema doc states this deviation explicitly."""
    rows = []
    for c in customers:
        plan = _PLAN_BY_ID[c.plan_id]
        cap = plan[4]
        n_active = cfg.n_months - c.active_from
        for k in range(n_active):
            idx = c.active_from + k
            # Trend across the customer's active life, in [0,1].
            progress = k / max(1, n_active - 1)
            trend = 1.0 + c.usage_decline * progress
            level = max(0.05, c.usage_base * trend * (1 + rng.gauss(0, 0.12)))
            data_gb = round(_clamp(level * cap * 0.55, 0.05, cap * 1.4), 2)
            voice = int(max(0, level * plan[5] * 0.5 * (1 + rng.gauss(0, 0.2))))
            sms = int(max(0, rng.gauss(20 * level, 8)))
            active_days = int(_clamp(round(18 + 8 * level + rng.gauss(0, 3)), 1, 31))
            rows.append(dict(
                customer_id=c.cid,
                period_month=_month_start(cfg, idx).isoformat(),
                data_gb_used=data_gb,
                voice_min_used=voice,
                sms_count=sms,
                active_days=active_days,
            ))
    return rows


def _emit_billing(cfg: Config, customers: list[_Customer], rng: Random):
    rows = []
    for c in customers:
        plan = _PLAN_BY_ID[c.plan_id]
        fee = plan[3]
        n_active = cfg.n_months - c.active_from
        problems = 0
        for k in range(n_active):
            idx = c.active_from + k
            overage = round(max(0.0, rng.gauss(0, fee * 0.15)), 2)
            billed = round(fee + overage, 2)
            # Payment behaviour worsens with price sensitivity.
            p_late = _clamp(cfg.base_late_rate + 0.04 * c.price_sensitivity, 0.0, 0.6)
            p_fail = _clamp(cfg.base_fail_rate + 0.02 * c.price_sensitivity, 0.0, 0.4)
            r = rng.random()
            if r < p_fail:
                status, days_late, paid = "failed", 0, 0.0
                problems += 1
                c.payment_problem_events.append((idx, 1.0))
            elif r < p_fail + p_late:
                days_late = rng.randint(5, 45)
                status, paid = "late", billed
                problems += 0.5
                c.payment_problem_events.append((idx, 0.5))
            else:
                status, days_late, paid = "paid", 0, billed
            period = _month_start(cfg, idx)
            paid_date = "" if status == "failed" else (period + timedelta(days=days_late + 3)).isoformat()
            rows.append(dict(
                invoice_id=f"INV_{c.cid[1:]}_{idx:02d}",
                customer_id=c.cid,
                period_month=period.isoformat(),
                amount_billed=billed,
                amount_paid=round(paid, 2),
                paid_date=paid_date,
                days_late=days_late,
                status=status,
            ))
        c.payment_problem_score = problems / max(1, n_active)
    return rows


def _emit_digital(cfg: Config, customers: list[_Customer], rng: Random):
    rows = []
    for c in customers:
        n_active = cfg.n_months - c.active_from
        for k in range(n_active):
            idx = c.active_from + k
            base = 4 + 3 * c.engagement_level
            logins = int(_clamp(rng.gauss(base, 2), 0, 60))
            self_service = int(_clamp(rng.gauss(base * 0.4, 1.5), 0, 40))
            rows.append(dict(
                customer_id=c.cid,
                period_month=_month_start(cfg, idx).isoformat(),
                app_logins=logins,
                self_service_actions=self_service,
                nps=("" if rng.random() > 0.15 else int(_clamp(round(7 + 1.2 * c.satisfaction), 0, 10))),
            ))
    return rows


def _emit_support(cfg: Config, customers: list[_Customer], rng: Random):
    rows = []
    for c in customers:
        n_active = cfg.n_months - c.active_from
        expected = cfg.tickets_per_year * (n_active / 12.0)
        # More tickets for lower satisfaction.
        expected *= _clamp(1.0 - 0.25 * c.satisfaction, 0.4, 2.0)
        n_tickets = 0
        acc = 0.0
        # Simple Poisson-ish draw via successive intervals.
        while True:
            acc += rng.expovariate(max(0.05, expected / max(1, n_active)))
            if acc >= n_active:
                break
            n_tickets += 1
            idx = c.active_from + int(acc)
            escalated = rng.random() < 0.22
            resolved = rng.random() < (0.85 - 0.25 * (1 if escalated else 0))
            unresolved_esc = escalated and not resolved
            if unresolved_esc:
                c.unresolved_support_score += 1
                c.unresolved_support_events.append(idx)
            rows.append(dict(
                ticket_id=f"TK_{c.cid[1:]}_{n_tickets:02d}",
                customer_id=c.cid,
                period_month=_month_start(cfg, idx).isoformat(),
                reason=rng.choice(TICKET_REASONS),
                channel=rng.choice(("call", "chat", "store", "app")),
                escalated=int(escalated),
                resolved=int(resolved),
                csat=("" if not resolved else int(_clamp(round(4 + c.satisfaction), 1, 5))),
            ))
    return rows


def _emit_consent(customers: list[_Customer], rng: Random):
    rows = []
    for c in customers:
        for ch in CONSENT_CHANNELS:
            # Engaged customers opt in more; call is opted-in least.
            base = 0.6 + 0.1 * c.engagement_level - (0.25 if ch == "call" else 0.0)
            consent = int(rng.random() < _clamp(base, 0.05, 0.95))
            rows.append(dict(
                customer_id=c.cid,
                channel=ch,
                consent=consent,
            ))
    return rows


def _risk_proxy_at(cfg: Config, c: _Customer, cutoff_idx: int) -> float:
    """Observable-ish risk **as of ``cutoff_idx``**, used both for campaign
    targeting (the confounder) and as the backbone of the churn propensity.
    Kept as a log-odds contribution.

    Evaluating it at an arbitrary cutoff — rather than only at the end of the
    window — is what lets the generator emit a second, earlier label without a
    trace of hindsight in it. Traits (usage trend, engagement, plan fit) are
    latent and time-invariant; the accumulated scores are re-derived from the
    events that had actually happened by ``cutoff_idx``.
    """
    months_observed = cutoff_idx + 1 - c.active_from
    payment_problems = sum(w for m, w in c.payment_problem_events if m <= cutoff_idx)
    payment_problem_score = payment_problems / max(1, months_observed)
    unresolved_support = sum(1 for m in c.unresolved_support_events if m <= cutoff_idx)

    usage_decline_score = _clamp(-c.usage_decline, 0.0, 1.5)  # steeper decline -> higher
    return (
        cfg.w_usage_decline * usage_decline_score
        + cfg.w_payment_problems * payment_problem_score
        + cfg.w_unresolved_support * _clamp(unresolved_support, 0, 3)
        + cfg.w_low_engagement * _clamp(-c.engagement_level, 0.0, 2.0)
        + cfg.w_early_life * (1.0 if months_observed <= 6 else 0.0)
        + cfg.w_plan_misfit * _clamp(-c.plan_fit, 0.0, 2.0)
    )


def _risk_proxy(cfg: Config, c: _Customer) -> float:
    """Risk at the final cutoff — the last month of history."""
    return _risk_proxy_at(cfg, c, cfg.n_months - 1)


def _emit_exposures(cfg: Config, customers: list[_Customer], rng: Random):
    """Assign campaign audiences. Retention campaigns are *targeted at risk*
    (selection bias) and carry a *true* uplift for genuine responders, split
    into exposed vs a held-out control so incrementality is recoverable."""
    rows = []
    exp_n = 0
    for camp in CAMPAIGNS:
        camp_id, _, channel, objective, offer_id, camp_month = camp
        for c in customers:
            risk = _risk_proxy(cfg, c)
            if objective == "retention":
                # Target high-risk customers (the confounder).
                p_target = _sigmoid(-1.4 + cfg.retention_selection_bias * (risk - 2.0))
            elif objective in ("upsell", "crosssell"):
                # Target engaged, higher-tier customers.
                p_target = _sigmoid(-1.6 + 0.7 * c.engagement_level + 0.3 * _PLAN_BY_ID[c.plan_id][6])
            else:
                p_target = 0.2
            if rng.random() >= p_target:
                continue
            exposed = int(rng.random() >= cfg.control_share)  # control held out
            # Response depends on offer relevance; true effect only if exposed.
            base_resp = 0.12 + 0.05 * c.engagement_level
            if objective == "retention":
                base_resp += 0.10 * _clamp(risk - 1.5, 0, 3)  # risk customers value a save
            responded = int(exposed and rng.random() < _clamp(base_resp, 0.02, 0.7))
            if objective == "retention" and responded:
                c.retention_response = 1  # feeds the true churn uplift
                c.retention_response_events.append(camp_month)
                c.targeted_risk_at_selection = risk
            exp_n += 1
            rows.append(dict(
                exposure_id=f"EXP_{exp_n:07d}",
                campaign_id=camp_id,
                customer_id=c.cid,
                exposed=exposed,
                responded=responded,
                channel=channel,
            ))
    return rows


def _emit_churn_labels_at(cfg: Config, customers: list[_Customer], rng: Random, cutoff_idx: int):
    """The modelling target, observed at ``cutoff_idx`` and predicting the
    *next 90 days*. Because every fact table stops at the final cutoff — and the
    risk proxy is re-derived from only the events that had happened by
    ``cutoff_idx`` — there is nothing post-outcome to leak: features are
    strictly pre-cutoff.

    Customers who had not signed up yet at ``cutoff_idx`` are omitted: they did
    not exist to be scored. At the final cutoff that excludes nobody.

    Returns the labels **and** their potential outcome under no campaign — see
    :func:`_counterfactual_row`. The second list is ground truth about the
    generator, not a fact any real dataset carries.
    """
    cutoff = _month_start(cfg, cutoff_idx)
    rows, counterfactual = [], []
    for c in customers:
        if c.active_from > cutoff_idx:
            continue
        retention_response = int(any(m <= cutoff_idx for m in c.retention_response_events))
        z = cfg.churn_intercept + _risk_proxy_at(cfg, c, cutoff_idx)
        z -= 0.4 * c.satisfaction  # latent, unobserved -> irreducible error
        z -= cfg.w_retention_response * retention_response  # the true uplift
        z += rng.gauss(0.0, cfg.churn_noise_sd)
        p = _sigmoid(z)
        # The uniform draw is held rather than consumed inline, so the same
        # draw can decide both potential outcomes. That is the whole trick: it
        # costs no extra randomness, so the tables above stay byte-for-byte
        # identical to a run without any of this.
        u = rng.random()
        churned = int(u < p)
        churn_date = ""
        if churned:
            churn_date = (cutoff + timedelta(days=rng.randint(1, 90))).isoformat()
        rows.append(dict(
            customer_id=c.cid,
            observation_cutoff=cutoff.isoformat(),
            churned_next_90d=churned,
            churn_date=churn_date,
        ))
        counterfactual.append(_counterfactual_row(cfg, c, cutoff, z, u, retention_response))
    return rows, counterfactual


def _counterfactual_row(cfg: Config, c: _Customer, cutoff: date, z: float, u: float,
                        retention_response: int) -> dict:
    """The same customer's outcome in a world where the campaign did nothing.

    Adding ``w_retention_response`` back to the log-odds undoes the treatment;
    comparing the two outcomes **at the same uniform draw** yields the
    individual-level causal effect rather than an average over a second, noisier
    world. Re-running the generator with the weight set to zero would *not* give
    this: the first customer whose outcome flips stops drawing a churn date, the
    RNG stream desynchronises, and every customer after them differs for reasons
    that have nothing to do with the campaign.

    **No real dataset has this column.** It exists so an estimator can be checked
    against the answer, which is the one thing a synthetic world is uniquely good
    for. It is ground truth, never an input: any case that reads it to *produce*
    an estimate has stopped measuring anything.
    """
    z_untreated = z + cfg.w_retention_response * retention_response
    return dict(
        customer_id=c.cid,
        observation_cutoff=cutoff.isoformat(),
        churned_next_90d_if_no_campaign=int(u < _sigmoid(z_untreated)),
        treated=retention_response,
    )


# --- Public entrypoint ----------------------------------------------------


def generate(cfg: Config) -> dict[str, list[dict]]:
    """Build the full data model and return it as a dict of table_name -> rows.

    Order matters: billing/support/exposures accumulate the observed scores that
    the churn label reads, so the churn labels are generated last.
    """
    rng = Random(cfg.seed)
    tables = _emit_reference()

    customers = _make_customers(cfg, rng)
    cust_rows, sub_rows = _emit_customers_and_subscriptions(cfg, customers)
    tables["customers"] = cust_rows
    tables["subscriptions"] = sub_rows

    tables["usage_monthly"] = _emit_usage(cfg, customers, rng)
    tables["billing"] = _emit_billing(cfg, customers, rng)  # sets payment scores
    tables["digital_monthly"] = _emit_digital(cfg, customers, rng)
    tables["support_interactions"] = _emit_support(cfg, customers, rng)  # sets support scores
    tables["consent"] = _emit_consent(customers, rng)
    tables["campaign_exposures"] = _emit_exposures(cfg, customers, rng)  # sets retention_response
    tables["churn_labels"], potential = _emit_churn_labels_at(cfg, customers, rng, cfg.n_months - 1)

    # The earlier cutoff is emitted *last*, on purpose: every table above draws
    # from `rng` in a fixed order, so appending here leaves their output
    # byte-for-byte identical to a run without this table at all.
    tables["churn_labels_prior"], potential_prior = _emit_churn_labels_at(
        cfg, customers, rng, cfg.n_months - 1 - cfg.prior_cutoff_offset
    )

    # Ground truth for the incrementality case, at both cutoffs. Derived from
    # draws already made, so it too leaves every table above untouched.
    tables["churn_potential_outcomes"] = potential + potential_prior

    return tables
