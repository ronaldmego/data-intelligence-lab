"""The case, end to end.

Order matters, and it is the order a real programme has to work in:

1. **Refit case 02's churn model** — the risk score is an input here, not a
   deliverable, and importing the case rather than its published numbers means
   the two cannot drift.
2. **Read the policy out of the data model** and build the permission matrix,
   with every refusal attributed to the rule that caused it.
3. **Price every offer for every customer**, with growth offers discounted by
   the churn risk from step 1.
4. **Build three contact lists** — governed, governed-in-the-wrong-order, and
   ungoverned — and compare them.
5. **Audit the campaigns that already ran** against the answer key, which is the
   only part of this that can be checked rather than estimated.

Step 5 is deliberately last and deliberately separate: it is the only place the
counterfactual is consulted, and it consults it through case 05's quarantined
module rather than opening the table here.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

_CHURN_CASE = Path(__file__).resolve().parents[2] / "02-churn-prediction"
if str(_CHURN_CASE) not in sys.path:
    sys.path.insert(0, str(_CHURN_CASE))

from churn import run_case as run_churn_case  # noqa: E402
from churn.economics import Economics  # noqa: E402
from churn.pipeline import CaseResult as ChurnResult  # noqa: E402

from .allocation import (  # noqa: E402
    Plan,
    PlanComparison,
    best_unconstrained_offers,
    filter_then_rank,
    rank_then_filter,
    realised_retention_profit,
    ungoverned,
)
from .audit import CampaignAudit, audit_retention_campaigns, channel_reach  # noqa: E402
from .data import (  # noqa: E402
    ContactHistory,
    Offer,
    PlanLadder,
    Tables,
    Wave,
    build_wave,
    churn_labels,
    load_consent,
    load_offers,
    load_tables,
    priced_offers,
)
from .policy import (  # noqa: E402
    COOL_OFF,
    CampaignComplianceRow,
    ContactPolicy,
    CustomerFacts,
    PermissionMatrix,
    audit_campaigns,
    consent_by_channel,
    evaluate,
    unreachable_customers,
)
from .value import (  # noqa: E402
    MEASURED_SAVE_RATE,
    AcceptanceModel,
    OfferEconomics,
    OfferValue,
    feature_matrix,
    fit_acceptance_models,
    score_offers,
)


@dataclass(frozen=True)
class RuleCost:
    """What one rule refuses, counted three ways because one number would mislead.

    ``blocked_pairs`` counts every refusal the rule makes; ``sole_blocker_pairs``
    counts only the refusals that would be reversed by dropping this rule alone.
    Overlapping rules make the first sum to more than the total blocked, and the
    second sum to less. Reporting either as "the cost of the rule" is how a rule
    gets blamed for a cost it shares with three others.

    ``customers_removed`` is the operational one: customers whose *best* offer
    this rule refuses — the people it actually takes off the list. Counting
    instead every customer the rule touches on any offer makes consent look
    universal (almost nobody has opted in to all four channels) and says nothing
    about who was lost.

    The churn figures beside it are the point of the whole table. A gate that
    removed a random slice of the base would leave them at the base rate; none
    of these do.
    """

    rule: str
    policy_id: str
    rationale: str
    blocked_pairs: int
    sole_blocker_pairs: int
    customers_removed: int
    mean_churn_probability: float
    realised_churn_rate: float


@dataclass(frozen=True)
class ConsentProfile:
    """Opt-in on one channel, and what those customers went on to do.

    Consent is not missing at random with respect to the outcome: in this data
    model engaged customers opt in more, and weak engagement is a churn driver.
    So permission is negatively correlated with risk *by construction* — which
    is a modelling choice, but not an arbitrary one. It is what makes the
    permitted population a different population rather than a smaller one.
    """

    channel: str
    opt_in_rate: float
    n_opted_in: int
    n_opted_out: int
    churn_opted_in: float
    churn_opted_out: float
    gap_standard_error: float

    @property
    def gap(self) -> float:
        return self.churn_opted_out - self.churn_opted_in

    @property
    def resolvable(self) -> bool:
        """Is the gap larger than its own sampling noise?

        It is not on every channel, and saying which is the difference between
        a finding and a story that happens to fit.
        """
        return abs(self.gap) > 1.96 * self.gap_standard_error


@dataclass(frozen=True)
class SensitivityPoint:
    """One setting of one policy parameter, and what it costs."""

    value: float
    blocked_customers: int
    mean_churn_probability_blocked: float
    plan_expected_value: float
    reachable_customers: int


@dataclass(frozen=True)
class AcceptanceComparison:
    """The same model fitted on everyone contacted, and on those we were allowed to.

    Going forward the policy only permits contact with the second group, so the
    first model is fitted on a population that can no longer be addressed. This
    is the quiet half of a governance retrofit: the constraint does not only
    limit the action, it invalidates part of the evidence used to choose it.
    """

    objective: str
    n_all: int
    n_permitted: int
    base_rate_all: float
    base_rate_permitted: float
    mean_prediction_all: float
    mean_prediction_permitted: float

    @property
    def training_rows_lost(self) -> float:
        return 1.0 - (self.n_permitted / self.n_all) if self.n_all else 0.0


@dataclass
class CaseResult:
    wave: Wave
    offers: list[Offer]
    policy: ContactPolicy
    matrix: PermissionMatrix
    churn: ChurnResult
    economics: OfferEconomics
    churn_probability: dict[str, float] = field(default_factory=dict)
    revenue: dict[str, float] = field(default_factory=dict)
    labels: dict[str, int] = field(default_factory=dict)
    values: dict[tuple[str, str], OfferValue] = field(default_factory=dict)
    acceptance: dict[str, AcceptanceModel] = field(default_factory=dict)
    acceptance_comparison: list[AcceptanceComparison] = field(default_factory=list)
    rule_costs: list[RuleCost] = field(default_factory=list)
    consent_rates: dict[str, float] = field(default_factory=dict)
    unreachable: int = 0
    compliance: list[CampaignComplianceRow] = field(default_factory=list)
    comparison: PlanComparison | None = None
    realised: dict[str, tuple[float, int]] = field(default_factory=dict)
    audits: list[CampaignAudit] = field(default_factory=list)
    channel_reach: dict[str, float] = field(default_factory=dict)
    sensitivity: list[SensitivityPoint] = field(default_factory=list)
    consent_profiles: list[ConsentProfile] = field(default_factory=list)
    # The catalogue split: offers a campaign has actually sent, and the ones
    # that have never run and therefore have no acceptance evidence at all.
    # ``catalogue`` is both together — governance applies to an offer whether
    # or not anyone can price it, so every permission matrix is built over it.
    catalogue: list[Offer] = field(default_factory=list)
    priced: list[Offer] = field(default_factory=list)
    unpriced: list[Offer] = field(default_factory=list)
    # What happens when the unpriced offers are scored anyway, which is what an
    # engine does by default. Reported as an experiment, not as the plan.
    speculative: Plan | None = None

    @property
    def reachable(self) -> int:
        return len(self.matrix.reachable_customers())

    @property
    def plans(self) -> list[Plan]:
        assert self.comparison is not None
        return [self.comparison.ungoverned, self.comparison.governed, self.comparison.suppressed]

    def realised_churn_of(self, customer_ids: list[str]) -> float:
        seen = [self.labels[c] for c in customer_ids if c in self.labels]
        return sum(seen) / len(seen) if seen else 0.0

    def mean_risk_of(self, customer_ids: list[str]) -> float:
        seen = [self.churn_probability[c] for c in customer_ids if c in self.churn_probability]
        return sum(seen) / len(seen) if seen else 0.0


def _rule_costs(result: CaseResult, best_offer: dict[str, str]) -> list[RuleCost]:
    costs = []
    for rule in result.matrix.rules_fired():
        removed = [
            cid for cid, offer_id in best_offer.items()
            if rule in result.matrix.permissions[(cid, offer_id)].blocked_by
        ]
        declared = result.policy.get(rule)
        costs.append(RuleCost(
            rule=rule,
            policy_id=declared.policy_id if declared else rule,
            rationale=declared.rationale if declared else "product eligibility rule (offer catalogue)",
            blocked_pairs=result.matrix.blocked_pairs(rule),
            sole_blocker_pairs=result.matrix.sole_blocker_pairs(rule),
            customers_removed=len(removed),
            mean_churn_probability=result.mean_risk_of(removed),
            realised_churn_rate=result.realised_churn_of(removed),
        ))
    return sorted(costs, key=lambda c: -c.customers_removed)


def _consent_profiles(
    consent: dict[str, dict[str, bool]],
    customer_ids: list[str],
    labels: dict[str, int],
    channels: tuple[str, ...] = ("push", "email", "sms", "call"),
) -> list[ConsentProfile]:
    profiles = []
    for channel in channels:
        opted_in = [c for c in customer_ids if consent.get(c, {}).get(channel, False)]
        opted_out = [c for c in customer_ids if not consent.get(c, {}).get(channel, False)]

        def rate(ids: list[str]) -> tuple[float, int]:
            seen = [labels[c] for c in ids if c in labels]
            return (sum(seen) / len(seen) if seen else 0.0), len(seen)

        p_in, n_in = rate(opted_in)
        p_out, n_out = rate(opted_out)
        variance = (p_in * (1 - p_in) / n_in if n_in else 0.0) + \
                   (p_out * (1 - p_out) / n_out if n_out else 0.0)

        profiles.append(ConsentProfile(
            channel=channel,
            opt_in_rate=len(opted_in) / len(customer_ids) if customer_ids else 0.0,
            n_opted_in=len(opted_in),
            n_opted_out=len(opted_out),
            churn_opted_in=p_in,
            churn_opted_out=p_out,
            gap_standard_error=math.sqrt(variance),
        ))
    return profiles


def _sensitivity(
    tables: Tables,
    result: CaseResult,
    ladder: PlanLadder,
    consent: dict[str, dict[str, bool]],
    history: ContactHistory,
    facts: CustomerFacts,
    windows: tuple[int, ...],
) -> list[SensitivityPoint]:
    """Sweep the cool-off window and re-price the plan at each setting.

    The single number "the cool-off costs us X" is the least useful form of this
    answer, because the cost is a step function of where the window falls
    relative to the last campaign — and nobody looks at that until they cross a
    step.
    """
    points = []
    for window in windows:
        policy = result.policy.replace(COOL_OFF, float(window))
        # Over the whole catalogue, exactly like the case's own matrix — a
        # sweep built on a different offer set produces "reachable" counts that
        # silently disagree with the headline.
        matrix = evaluate(tables, result.catalogue, result.wave.customer_ids, result.wave.cutoff,
                          policy, ladder, consent, history, facts)
        blocked = [
            cid for cid in matrix.customer_ids
            if any(COOL_OFF in matrix.permissions[(cid, oid)].blocked_by for oid in matrix.offer_ids)
        ]
        plan = filter_then_rank(result.wave.customer_ids, result.offers, result.values,
                                matrix, result.wave.capacity)
        points.append(SensitivityPoint(
            value=float(window),
            blocked_customers=len(blocked),
            mean_churn_probability_blocked=result.mean_risk_of(blocked),
            plan_expected_value=plan.expected_value,
            reachable_customers=len(matrix.reachable_customers()),
        ))
    return points


def run_case(
    tables: Tables | None = None,
    capacity_share: float = 0.10,
    save_rate: float = MEASURED_SAVE_RATE,
    churn_result: ChurnResult | None = None,
    sensitivity_windows: tuple[int, ...] = (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 365),
) -> CaseResult:
    """Run the whole case and return every number the report needs."""
    tables = tables if tables is not None else load_tables()
    economics = OfferEconomics(base=Economics(save_rate=save_rate))

    # --- 1. risk, from case 02 -------------------------------------------
    churn = churn_result or run_churn_case(tables, economics=economics.base,
                                           capacity_share=capacity_share)
    wave = build_wave(tables, churn.test.cutoff, churn.test.customer_ids, capacity_share)
    churn_probability = dict(zip(churn.test.customer_ids, churn.probabilities, strict=True))
    revenue = dict(zip(churn.test.customer_ids, churn.monthly_revenue, strict=True))

    catalogue = load_offers(tables)
    # Only offers a campaign has actually sent can be given an acceptance
    # probability from evidence. The rest are scored too — so the report can
    # show what happens — but they are held out of the plan.
    offers = priced_offers(catalogue)
    ladder = PlanLadder.build(tables)
    consent = load_consent(tables)
    history = ContactHistory.build(tables)
    facts = CustomerFacts.build(tables, wave.cutoff, wave.customer_ids)
    policy = ContactPolicy.load(tables)

    result = CaseResult(
        wave=wave, offers=offers, policy=policy,
        matrix=PermissionMatrix(), churn=churn, economics=economics,
        churn_probability=churn_probability, revenue=revenue, labels=churn_labels(tables),
        catalogue=catalogue, priced=offers,
        unpriced=[o for o in catalogue if not o.has_history],
    )

    # --- 2. permissions ---------------------------------------------------
    # The matrix covers the *whole* catalogue: governance applies to an offer
    # whether or not anyone can price it.
    result.matrix = evaluate(tables, catalogue, wave.customer_ids, wave.cutoff,
                             policy, ladder, consent, history, facts)
    result.consent_rates = consent_by_channel(tables, wave.customer_ids)
    result.unreachable = len(unreachable_customers(consent, wave.customer_ids))
    result.compliance = audit_campaigns(tables, catalogue, ladder, consent)
    result.channel_reach = channel_reach(tables, consent, wave.customer_ids)
    result.consent_profiles = _consent_profiles(consent, wave.customer_ids, result.labels)

    # --- 3. value ---------------------------------------------------------
    objectives = sorted({o.objective for o in catalogue})
    models = fit_acceptance_models(tables, objectives, consent, consented_only=False)
    permitted_models = fit_acceptance_models(tables, objectives, consent, consented_only=True)
    result.acceptance = models

    x = feature_matrix(tables, wave.cutoff, wave.customer_ids)
    acceptance = {
        objective: dict(zip(wave.customer_ids, model.predict(x), strict=True))
        for objective, model in models.items()
    }
    permitted_predictions = {
        objective: model.predict(x) for objective, model in permitted_models.items()
    }
    result.acceptance_comparison = [
        AcceptanceComparison(
            objective=objective,
            n_all=models[objective].n_train,
            n_permitted=permitted_models[objective].n_train,
            base_rate_all=models[objective].base_rate,
            base_rate_permitted=permitted_models[objective].base_rate,
            mean_prediction_all=sum(acceptance[objective].values()) / max(1, len(wave)),
            mean_prediction_permitted=(sum(permitted_predictions[objective])
                                       / max(1, len(permitted_predictions[objective]))),
        )
        for objective in objectives
    ]

    result.values = score_offers(tables, catalogue, wave.customer_ids, churn_probability,
                                 acceptance, revenue, ladder, economics)

    # --- 4. the three lists ------------------------------------------------
    result.comparison = PlanComparison(
        governed=filter_then_rank(wave.customer_ids, offers, result.values,
                                  result.matrix, wave.capacity),
        suppressed=rank_then_filter(wave.customer_ids, offers, result.values,
                                    result.matrix, wave.capacity),
        ungoverned=ungoverned(wave.customer_ids, offers, result.values, wave.capacity),
    )
    if result.unpriced:
        result.speculative = filter_then_rank(
            wave.customer_ids, catalogue, result.values, result.matrix, wave.capacity,
            name="governed, pricing offers that never ran",
        )
    result.realised = {
        plan.name: realised_retention_profit(plan, result.labels, revenue, catalogue, economics)
        for plan in result.plans
    }
    result.rule_costs = _rule_costs(
        result, best_unconstrained_offers(wave.customer_ids, offers, result.values),
    )

    # --- 5. the retrospective check ---------------------------------------
    result.audits = audit_retention_campaigns(tables, offers, ladder, consent)
    result.sensitivity = _sensitivity(tables, result, ladder, consent, history, facts,
                                      sensitivity_windows)
    return result
