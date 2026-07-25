"""Where does the effect live — and can this experiment see it?

Two different questions, and conflating them is how uplift modelling gets sold.
An effect can be strongly concentrated in one part of the base while an
experiment has no ability whatsoever to locate it, because splitting an audience
into strata divides the sample and multiplies the intervals.

So this module reports both: the estimate per stratum with its interval, and —
from the answer key, and only in the reporting layer — what the effect really
was. The interesting outcome is the one that actually occurs here: the point
estimates line up with the truth, and the intervals are wide enough that they
would have lined up wrongly about as often.

Strata are built from a risk score fitted **on untreated customers only**. A
model fitted on everyone would have learned part of the treatment effect and
then been used to decide where the treatment effect is, which is circular.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .estimators import Estimate, difference_in_proportions

_CHURN_CASE = Path(__file__).resolve().parents[2] / "02-churn-prediction"
if str(_CHURN_CASE) not in sys.path:
    sys.path.insert(0, str(_CHURN_CASE))

from churn.features import build_features  # noqa: E402
from churn.model import CollinearityFilter, LogisticRegression, Standardiser, sigmoid  # noqa: E402


@dataclass(frozen=True)
class Stratum:
    """One slice of the audience, ordered by pre-campaign risk."""

    index: int
    label: str
    n_exposed: int
    n_control: int
    mean_risk: float
    estimate: Estimate
    true_effect: float | None = None           # the true value of *this stratum's* ITT
    true_effect_on_treated: float | None = None  # the population effect among those treated here

    @property
    def covers_truth(self) -> bool | None:
        if self.true_effect is None:
            return None
        return self.estimate.ci_low <= self.true_effect <= self.estimate.ci_high


@dataclass(frozen=True)
class Heterogeneity:
    campaign_id: str
    strata: list[Stratum]
    spread: float             # highest-risk stratum minus lowest, as estimated
    true_spread: float | None  # the same difference in the answer key

    @property
    def widest_interval(self) -> float:
        return max((s.estimate.ci_high - s.estimate.ci_low) for s in self.strata)

    @property
    def resolvable(self) -> bool:
        """Is the estimated spread larger than the intervals it is read from?

        The test that decides whether a targeting rule can be built from this.
        When it fails, the ordering of the strata is a coin flip dressed as a
        finding — and it will still look monotone often enough to be believed.
        """
        return abs(self.spread) > self.widest_interval

    @property
    def ordering_matches_truth(self) -> bool | None:
        if self.true_spread is None:
            return None
        return (self.spread < 0) == (self.true_spread < 0)

    @property
    def true_spread_on_treated(self) -> float | None:
        """How much the effect *on an acceptor* really varies across risk.

        The stable version of the question. A stratum's ITT depends on how many
        of its members happened to accept, which is a small-sample quantity; the
        effect on those who did accept is a property of the customers, and it is
        the one a targeting rule would have to exploit.
        """
        first, last = self.strata[0].true_effect_on_treated, self.strata[-1].true_effect_on_treated
        if first is None or last is None:
            return None
        return last - first


def _fit_risk_score(tables, cutoff: str, treated: set[str], label_table: str) -> dict[str, float]:
    """A churn score as of ``cutoff``, fitted on customers no campaign treated."""
    labels = {r["customer_id"]: int(r["churned_next_90d"]) for r in tables[label_table]}
    train_ids = [c for c in labels if c not in treated]

    x_train = build_features(tables, cutoff, train_ids)
    y_train = [labels[c] for c in train_ids]

    pruner = CollinearityFilter().fit(x_train)
    standardiser = Standardiser().fit(pruner.transform(x_train))
    model = LogisticRegression(l2=1.0).fit(standardiser.transform(pruner.transform(x_train)), y_train)

    all_ids = list(labels)
    x_all = build_features(tables, cutoff, all_ids)
    scores = model.decision_function(standardiser.transform(pruner.transform(x_all)))
    return {cid: sigmoid(z) for cid, z in zip(all_ids, scores, strict=True)}


def by_risk(tables, audience, truth=None, n_strata: int = 3,
            label_table: str = "churn_labels") -> Heterogeneity:
    """Estimate the effect within pre-campaign risk strata."""
    risk = _fit_risk_score(tables, audience.campaign.prior_month, audience.treated, label_table)

    members = sorted(audience.members, key=lambda c: risk.get(c, 0.0))
    exposed = set(audience.exposed)
    n = len(members)
    names = {3: ("lowest risk", "middle", "highest risk")}.get(n_strata)

    strata: list[Stratum] = []
    for k in range(n_strata):
        group = members[k * n // n_strata:(k + 1) * n // n_strata]
        arm_e = [c for c in group if c in exposed]
        arm_c = [c for c in group if c not in exposed]
        estimate = difference_in_proportions(
            f"stratum {k + 1}", audience.outcomes(arm_e), audience.outcomes(arm_c),
            question="Effect within this risk stratum",
        )
        treated_here = [c for c in group if c in audience.treated]
        strata.append(Stratum(
            index=k,
            label=names[k] if names else f"stratum {k + 1}",
            n_exposed=len(arm_e),
            n_control=len(arm_c),
            mean_risk=sum(risk.get(c, 0.0) for c in group) / max(1, len(group)),
            estimate=estimate,
            true_effect=(truth.average_over(arm_e) - truth.average_over(arm_c)) if truth else None,
            # The population quantity: how much an accepted offer is worth to
            # this kind of customer. Unlike the stratum ITT above it does not
            # depend on how the flip happened to split this particular stratum,
            # so it is the one that answers "where does the effect live?".
            true_effect_on_treated=truth.average_over(treated_here) if truth and treated_here else None,
        ))

    spread = strata[-1].estimate.value - strata[0].estimate.value
    true_spread = None
    if truth is not None and strata[-1].true_effect is not None and strata[0].true_effect is not None:
        true_spread = strata[-1].true_effect - strata[0].true_effect

    return Heterogeneity(
        campaign_id=audience.campaign.campaign_id,
        strata=strata,
        spread=spread,
        true_spread=true_spread,
    )
