"""The estimators — and the intervals without which none of them mean anything.

Every number here is a difference between two proportions. The arithmetic is
trivial; which two proportions is the entire case. So each estimator carries the
groups it was computed from, and every one of them reports a standard error,
because the finding of this case is that the intervals are wider than the effects
and no point estimate survives being quoted alone.

Nothing in this module knows the right answer. It is handed two lists of
outcomes and returns what they support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Normal quantiles, hard-coded so the module stays standard-library only and the
# report cannot drift because a stats package changed a default.
Z_95 = 1.959963984540054
Z_POWER_80 = 0.8416212335729143


@dataclass(frozen=True)
class Estimate:
    """A difference in proportions, with everything needed to judge it."""

    name: str
    value: float
    standard_error: float
    n_treatment: int
    n_control: int
    question: str = ""

    @property
    def ci_low(self) -> float:
        return self.value - Z_95 * self.standard_error

    @property
    def ci_high(self) -> float:
        return self.value + Z_95 * self.standard_error

    @property
    def significant(self) -> bool:
        """Does the 95% interval exclude zero?"""
        return self.ci_low > 0.0 or self.ci_high < 0.0

    @property
    def z(self) -> float:
        return self.value / self.standard_error if self.standard_error else 0.0


def difference_in_proportions(name: str, treatment: list[int], control: list[int],
                              question: str = "") -> Estimate:
    """The workhorse: mean(treatment) - mean(control), with the unpooled SE.

    Unpooled because the two arms are not assumed to share a rate — under a real
    effect they do not, and the pooled variance used for a null-hypothesis test
    is the wrong one for an interval around the estimate itself.
    """
    n_t, n_c = len(treatment), len(control)
    p_t = sum(treatment) / n_t if n_t else 0.0
    p_c = sum(control) / n_c if n_c else 0.0
    variance = (p_t * (1 - p_t) / n_t if n_t else 0.0) + (p_c * (1 - p_c) / n_c if n_c else 0.0)
    return Estimate(
        name=name,
        value=p_t - p_c,
        standard_error=math.sqrt(variance),
        n_treatment=n_t,
        n_control=n_c,
        question=question,
    )


def intent_to_treat(audience, name: str | None = None) -> Estimate:
    """Exposed vs control, everyone kept in the arm they were assigned to.

    The only estimate here that needs no assumption beyond the randomisation
    itself. It answers the question a budget holder actually has — *what did
    running this campaign do?* — and it answers it about contacting people, not
    about the offer, because some of the contacted ignored it.
    """
    return difference_in_proportions(
        name or f"ITT — {audience.campaign.campaign_id}",
        audience.outcomes(audience.exposed),
        audience.outcomes(audience.control),
        question="What did contacting this audience do?",
    )


def first_stage(audience, name: str | None = None) -> Estimate:
    """How much more treatment the exposed arm actually received.

    The control arm is not at zero: a customer held back from *this* campaign
    could still have accepted an offer from another one. That contamination is
    balanced across the arms — the flips are independent — so it does not bias
    the ITT. It does shrink the gap the ITT is spread over, which is exactly
    what this number measures and what the Wald estimator divides by.
    """
    return difference_in_proportions(
        name or f"first stage — {audience.campaign.campaign_id}",
        audience.treated_flags(audience.exposed),
        audience.treated_flags(audience.control),
        question="How much more treatment did exposure deliver?",
    )


def wald(itt: Estimate, compliance: Estimate, name: str = "CACE") -> Estimate:
    """The effect on those who took the offer: ITT divided by the first stage.

    Valid here because non-compliance is one-sided by construction — a held-back
    customer cannot respond to a campaign they were never sent — so the exposed
    arm's extra outcomes have to have come through the extra offers taken.

    The standard error uses the Bloom approximation, ``SE(ITT) / first stage``,
    which treats the denominator as known. That is defensible when the first
    stage is strong and dishonest when it is not: as compliance approaches zero
    the ratio explodes and its interval does not, which is how a campaign with no
    first stage comes to report a spectacular effect. :func:`is_weak` is the
    guard, and the report prints it next to every Wald estimate rather than
    leaving the reader to notice.
    """
    if compliance.value == 0.0:
        return Estimate(name, float("nan"), float("inf"), itt.n_treatment, itt.n_control,
                        question="Effect on those who took the offer")
    return Estimate(
        name=name,
        value=itt.value / compliance.value,
        standard_error=itt.standard_error / abs(compliance.value),
        n_treatment=itt.n_treatment,
        n_control=itt.n_control,
        question="Effect on those who took the offer",
    )


def is_weak(compliance: Estimate, threshold: float = 4.0) -> bool:
    """Is the first stage too small to divide by?

    The conventional bar for an instrument is a first-stage F above 10, which for
    a single binary instrument is roughly a t of 3.2. This uses a deliberately
    lenient threshold: the point is not to be strict, it is that the campaigns
    which fail it here fail it by an order of magnitude.
    """
    return abs(compliance.z) < threshold


def pool(estimates: list[Estimate], name: str) -> Estimate:
    """Inverse-variance weighted average — each estimate counted by its precision.

    The right way to combine two readings of the same quantity, and the reason
    the pooled interval is narrower than either. It assumes the estimates are
    independent; when audiences overlap they are not, and the report says so
    rather than quietly banking the narrower interval.
    """
    usable = [e for e in estimates if e.standard_error > 0 and math.isfinite(e.standard_error)]
    if not usable:
        return Estimate(name, float("nan"), float("inf"), 0, 0)
    weights = [1.0 / e.standard_error ** 2 for e in usable]
    total = sum(weights)
    return Estimate(
        name=name,
        value=sum(w * e.value for w, e in zip(weights, usable, strict=True)) / total,
        standard_error=math.sqrt(1.0 / total),
        n_treatment=sum(e.n_treatment for e in usable),
        n_control=sum(e.n_control for e in usable),
        question=usable[0].question,
    )


def minimum_detectable_effect(n_treatment: int, n_control: int, base_rate: float,
                              power: float = 0.80, alpha: float = 0.05) -> float:
    """The smallest true effect this design would find, most of the time.

    Reported *before* any result is interpreted, because a null finding from an
    experiment that could never have detected the effect is not evidence of
    absence — and it is indistinguishable, in the output, from one that is.
    """
    if n_treatment <= 0 or n_control <= 0:
        return float("inf")
    z_alpha = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_two_sided(alpha)
    z_beta = Z_POWER_80 if abs(power - 0.80) < 1e-9 else _z_one_sided(power)
    variance = base_rate * (1 - base_rate) * (1 / n_treatment + 1 / n_control)
    return (z_alpha + z_beta) * math.sqrt(variance)


def detectable_from_standard_error(standard_error: float, power: float = 0.80, alpha: float = 0.05) -> float:
    """The MDE implied by an interval that has already been computed.

    Same quantity as :func:`minimum_detectable_effect`, reached from the standard
    error rather than from the arm sizes — which is the only route available for
    a pooled estimate, where there is no single pair of arms to plug in.
    """
    z_alpha = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_two_sided(alpha)
    z_beta = Z_POWER_80 if abs(power - 0.80) < 1e-9 else _z_one_sided(power)
    return (z_alpha + z_beta) * standard_error


def required_per_arm(effect: float, base_rate: float, power: float = 0.80, alpha: float = 0.05) -> int:
    """Customers per arm needed to detect ``effect`` — the design fix, quantified."""
    if effect == 0:
        return 0
    z_alpha = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_two_sided(alpha)
    z_beta = Z_POWER_80 if abs(power - 0.80) < 1e-9 else _z_one_sided(power)
    return math.ceil(2 * (z_alpha + z_beta) ** 2 * base_rate * (1 - base_rate) / effect ** 2)


def power_at(effect: float, standard_error: float, alpha: float = 0.05) -> float:
    """The chance this design calls a true ``effect`` significant.

    The number that turns "we found nothing" into either a finding or a receipt
    for an experiment that was never going to work.
    """
    if standard_error <= 0 or not math.isfinite(standard_error):
        return 0.0
    z_alpha = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_two_sided(alpha)
    shift = abs(effect) / standard_error
    return _normal_cdf(shift - z_alpha) + _normal_cdf(-shift - z_alpha)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_quantile(p: float) -> float:
    """Inverse normal CDF by bisection — exact enough, and dependency-free."""
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _normal_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _z_two_sided(alpha: float) -> float:
    return _normal_quantile(1 - alpha / 2)


def _z_one_sided(power: float) -> float:
    return _normal_quantile(power)
