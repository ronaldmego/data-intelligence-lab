"""The case, end to end — four readings of one campaign, and why they disagree.

The same retention campaign is read four ways, in the order a real analysis
tends to travel:

1. **Responders vs the base.** The number a campaign report opens with. It says
   the campaign made things *worse*, because retention campaigns are aimed at
   people who were already leaving.
2. **Responders vs non-responders in the audience.** Targeting is now held
   constant, and the sign flips to spectacular. Still wrong: responding is a
   choice, and the people who take a retention offer differ from the people who
   ignore it in exactly the ways that predict churn.
3. **Exposed vs control.** The comparison the held-back group was bought for.
   Assumption-free, and the only one of the four that is.
4. **Divided by the first stage.** Rescales the third from *the effect of being
   contacted* to *the effect on those who accepted*, which is a different — and
   much larger — number that is routinely reported as if it were the third.

Then the case turns on itself: two identical campaigns are run through the same
machinery and disagree completely, a campaign with no possible effect on churn
is used as a negative control, and the answer key is opened to find out which
readings were right and why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .balance import BalanceReport, check_balance
from .data import Audience, Campaign, Tables, build_audience, load_campaigns, load_tables, untargeted
from .economics import Economics, Repricing, SaveRate, measured_save_rate, reprice_case_02
from .estimators import (
    Estimate,
    difference_in_proportions,
    first_stage,
    intent_to_treat,
    is_weak,
    minimum_detectable_effect,
    pool,
    power_at,
    required_per_arm,
    wald,
)
from .heterogeneity import Heterogeneity, by_risk
from .truth import Decomposition, Truth, decompose, load_truth


@dataclass
class CampaignResult:
    """Everything one campaign's randomisation supports."""

    audience: Audience
    itt: Estimate
    compliance: Estimate
    cace: Estimate
    balance: BalanceReport
    decomposition: Decomposition | None = None
    heterogeneity: Heterogeneity | None = None

    @property
    def weak_first_stage(self) -> bool:
        return is_weak(self.compliance)

    @property
    def minimum_detectable(self) -> float:
        return minimum_detectable_effect(
            len(self.audience.exposed), len(self.audience.control), self.audience.control_churn,
        )

    def power_against(self, effect: float) -> float:
        """The chance this campaign would have called ``effect`` significant."""
        return power_at(effect, self.itt.standard_error)


@dataclass
class Exclusion:
    """What happens when a post-treatment filter is applied to a causal estimate.

    Case 02 excludes customers who churned in the earlier window, correctly: a
    model should not be scored on people who have already gone. Carrying that
    same filter into an incrementality read is a different act, because the
    treatment changed who ends up in the filter — so the two arms are no longer
    the two arms that were randomised.
    """

    campaign_id: str
    full: Estimate
    filtered: Estimate
    dropped_exposed: float
    dropped_control: float

    @property
    def shift(self) -> float:
        return self.filtered.value - self.full.value

    @property
    def differential(self) -> float:
        """How much more of the control arm the filter removed.

        Non-zero *because the campaign worked*: fewer treated customers churned
        in the earlier window, so fewer of them are filtered out. The filter is
        reading the treatment.
        """
        return self.dropped_control - self.dropped_exposed


@dataclass
class CaseResult:
    tables: Tables
    campaigns: list[Campaign]
    retention: list[CampaignResult] = field(default_factory=list)
    negative_controls: list[CampaignResult] = field(default_factory=list)
    naive: list[Estimate] = field(default_factory=list)
    pooled_itt: Estimate | None = None
    pooled_compliance: Estimate | None = None
    pooled_cace: Estimate | None = None
    truth: Truth | None = None
    exclusions: list[Exclusion] = field(default_factory=list)
    save_rate: SaveRate | None = None
    repricing: list[Repricing] = field(default_factory=list)
    audience_size: int = 0
    overlap: int = 0
    economics: Economics = field(default_factory=Economics)

    @property
    def pooled_control_churn(self) -> float:
        """Control churn across the retention audiences, weighted by control size."""
        total = sum(len(r.audience.control) for r in self.retention)
        if not total:
            return 0.0
        return sum(r.audience.control_churn * len(r.audience.control) for r in self.retention) / total

    @property
    def true_delivered(self) -> float | None:
        """The true value of the pooled ITT — the estimand, not the effect on the treated.

        Pooled with the same precision weights the observed estimate uses, so the
        two are directly comparable. This is deliberately *not* the average
        effect among exposed customers: that number is larger, because the
        control arm is not untreated (it could accept the other campaign's
        offer), and comparing an estimate of a difference against an average
        over one arm would manufacture a discrepancy that is pure bookkeeping.
        """
        if self.truth is None or not self.retention:
            return None
        return _precision_weighted(
            [r.decomposition.delivered for r in self.retention if r.decomposition],
            [r.itt for r in self.retention],
        )

    @property
    def true_baseline(self) -> float | None:
        """Churn among the contacted, in the world where no campaign ran.

        The denominator of a save rate, as the truth rather than as the control
        arm's estimate of it.
        """
        if self.truth is None:
            return None
        return self.truth.untreated_rate([c for r in self.retention for c in r.audience.exposed])

    @property
    def target_effect(self) -> float:
        """The effect the design should have been sized to find."""
        return abs(self.true_delivered if self.true_delivered is not None else self.pooled_itt.value)

    def standard_error_at(self, n_control: int) -> float:
        """The pooled standard error this design would have at a given control size.

        Holds the design fixed and varies only its scale: the same contacted-to-
        held-back ratio the campaigns actually used, and the same pooling across
        both of them. One power model, used for the reported requirement and for
        the curve alike — computing the two from different assumptions is how a
        chart comes to contradict the table beside it.
        """
        audience = self.retention[0].audience
        ratio = len(audience.exposed) / len(audience.control)
        base = self.pooled_control_churn
        n_control = max(2, n_control)
        n_exposed = max(2, round(n_control * ratio))
        variance = base * (1 - base) * (1 / n_exposed + 1 / n_control)
        return math.sqrt(variance / max(1, len(self.retention)))

    def power_at_control(self, n_control: int) -> float:
        return power_at(self.target_effect, self.standard_error_at(n_control))

    @property
    def required_control(self) -> int:
        """Customers to hold back per campaign for an 80% chance of finding the effect.

        Solved against :meth:`standard_error_at`, so it is the requirement for
        *this* design scaled up — unequal arms, two campaigns pooled — rather
        than the textbook equal-arms figure, which describes an experiment
        nobody here ran.
        """
        lo, hi = 2, 2
        while self.power_at_control(hi) < 0.80 and hi < 10_000_000:
            hi *= 2
        while lo < hi:
            mid = (lo + hi) // 2
            if self.power_at_control(mid) < 0.80:
                lo = mid + 1
            else:
                hi = mid
        return lo

    @property
    def required_equal_arms(self) -> int:
        """The same target, as the textbook equal-arms formula would size it.

        Reported alongside because it is the number a sample-size calculator
        returns, and it is roughly three times larger — the cost of splitting an
        audience 70/30 and reading one campaign at a time.
        """
        return required_per_arm(self.target_effect, self.pooled_control_churn)

    @property
    def realised_power(self) -> float:
        """The chance the pooled design called the real effect significant."""
        if self.pooled_itt is None:
            return 0.0
        return power_at(self.target_effect, self.pooled_itt.standard_error)


def _precision_weighted(values: list[float], estimates: list[Estimate]) -> float:
    """Average ``values`` using the precision weights of ``estimates``.

    Lets a ground-truth quantity be pooled exactly the way its estimate was, so
    the comparison between them is like-for-like.
    """
    usable = [(v, e) for v, e in zip(values, estimates, strict=True) if e.standard_error > 0]
    if not usable:
        return 0.0
    weights = [1.0 / e.standard_error ** 2 for _, e in usable]
    return sum(w * v for w, (v, _) in zip(weights, usable, strict=True)) / sum(weights)


def _naive_reads(tables: Tables, audiences: list[Audience], treated: set[str],
                 outcome: dict[str, int]) -> list[Estimate]:
    """The comparisons that are available without a control group, and wrong."""
    members = sorted({c for a in audiences for c in a.members})
    responders = [c for c in members if c in treated]
    non_responders = [c for c in members if c not in treated]
    never_targeted = untargeted(tables, audiences)
    everyone = sorted(outcome)

    def y(ids: list[str]) -> list[int]:
        return [outcome[c] for c in ids if c in outcome]

    return [
        difference_in_proportions(
            "Responders vs the whole base", y(responders), y(everyone),
            question="Do customers who took the offer churn less than everybody else?",
        ),
        difference_in_proportions(
            "Responders vs customers no retention campaign targeted", y(responders), y(never_targeted),
            question="Do they churn less than the untargeted?",
        ),
        difference_in_proportions(
            "Responders vs non-responders in the same audience", y(responders), y(non_responders),
            question="Do they churn less than others the campaign also chose?",
        ),
    ]


def _exclusion_demo(tables: Tables, audience: Audience) -> Exclusion:
    """Re-run the ITT with case 02's population filter applied, and measure the damage."""
    gone = {r["customer_id"] for r in tables["churn_labels_prior"] if int(r["churned_next_90d"]) == 1}
    exposed = [c for c in audience.exposed if c not in gone]
    control = [c for c in audience.control if c not in gone]
    return Exclusion(
        campaign_id=audience.campaign.campaign_id,
        full=intent_to_treat(audience),
        filtered=difference_in_proportions(
            "ITT after excluding earlier churners",
            audience.outcomes(exposed), audience.outcomes(control),
        ),
        dropped_exposed=1 - len(exposed) / len(audience.exposed),
        dropped_control=1 - len(control) / len(audience.control),
    )


def run_case(tables: Tables | None = None, churn_result=None, economics: Economics | None = None,
             use_truth: bool = True, with_heterogeneity: bool = True) -> CaseResult:
    """Run the whole case and return every number the report needs.

    ``churn_result`` is case 02's output. When supplied, the save rate measured
    here is fed back through its targeting comparison; when omitted, everything
    except the repricing section is still produced.
    """
    tables = tables if tables is not None else load_tables()
    economics = economics or Economics()
    campaigns = load_campaigns(tables)

    audiences = {c.campaign_id: build_audience(tables, c) for c in campaigns}
    retention_audiences = [audiences[c.campaign_id] for c in campaigns if c.is_retention]
    control_audiences = [audiences[c.campaign_id] for c in campaigns if not c.is_retention]

    outcome = retention_audiences[0].outcome
    treated = retention_audiences[0].treated
    cutoff = retention_audiences[0].cutoff

    result = CaseResult(tables=tables, campaigns=campaigns, economics=economics)
    result.truth = load_truth(tables, cutoff, treated) if use_truth else None

    def build(audience: Audience, heterogeneity: bool) -> CampaignResult:
        itt = intent_to_treat(audience)
        compliance = first_stage(audience)
        return CampaignResult(
            audience=audience,
            itt=itt,
            compliance=compliance,
            cace=wald(itt, compliance),
            balance=check_balance(tables, audience),
            decomposition=decompose(audience, result.truth) if result.truth else None,
            heterogeneity=(by_risk(tables, audience, result.truth)
                           if heterogeneity and with_heterogeneity else None),
        )

    result.retention = [build(a, heterogeneity=True) for a in retention_audiences]
    result.negative_controls = [build(a, heterogeneity=False) for a in control_audiences]

    result.naive = _naive_reads(tables, retention_audiences, treated, outcome)

    # Pooled across the two retention campaigns. Each per-campaign ITT is
    # unbiased on its own; combining them by precision is the standard way to
    # read two runs of the same test. The audiences overlap, so the pooled
    # interval is mildly optimistic — flagged in the report, and it does not
    # change the verdict, which is that the interval is far too wide either way.
    result.pooled_itt = pool([r.itt for r in result.retention], "Pooled ITT (both retention campaigns)")
    result.pooled_compliance = pool([r.compliance for r in result.retention], "Pooled first stage")
    result.pooled_cace = wald(result.pooled_itt, result.pooled_compliance, "Pooled CACE")

    members = [set(a.members) for a in retention_audiences]
    result.audience_size = len(set().union(*members))
    result.overlap = len(members[0] & members[1]) if len(members) == 2 else 0

    result.exclusions = [_exclusion_demo(tables, a) for a in retention_audiences]

    result.save_rate = measured_save_rate(
        result.pooled_itt,
        result.pooled_control_churn,
        assumed=economics.save_rate,
        true_effect=result.true_delivered,
        true_baseline=result.true_baseline,
    )

    if churn_result is not None:
        result.repricing = reprice_case_02(churn_result, [
            ("assumed by case 02", economics.save_rate),
            ("measured", result.save_rate.value),
            ("low end of the interval", max(0.0, result.save_rate.ci_low)),
            ("high end of the interval", result.save_rate.ci_high),
        ])

    return result
