"""Paying off case 02's debt, in case 02's own units.

Case 02 built a contact list and priced it with a **save rate of 0.25** — the
share of would-be churners a contact retains — and said plainly that the number
was assumed, that no observational data could establish it, and that case 05 was
where it would be settled. This module settles it, or reports honestly that the
experiment cannot.

The translation matters, because the experiment does not measure a save rate
directly. It measures a reduction in churn per *contacted* customer:

    saves per contact          = −ITT
    would-be churners contacted = churn rate in the control arm
    save rate                   = −ITT / control churn rate

That ratio is exactly case 02's parameter: the fraction of the churn that was
going to happen anyway which a contact prevents. It is not the CACE — the effect
on customers who *took* the offer — and quoting one for the other inflates the
number by the reciprocal of the response rate, which here is about five.

Because realised profit is linear in the save rate and the value ranking is
invariant to it (the save rate is a positive constant common to every customer's
expected value), the whole of case 02's targeting comparison can be re-priced
from its already-scored population without refitting anything.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .estimators import Estimate

_CHURN_CASE = Path(__file__).resolve().parents[2] / "02-churn-prediction"
if str(_CHURN_CASE) not in sys.path:
    sys.path.insert(0, str(_CHURN_CASE))

from churn.economics import Economics, compare_policies  # noqa: E402


@dataclass(frozen=True)
class SaveRate:
    """The measured save rate, in the units case 02 assumed one."""

    value: float
    ci_low: float
    ci_high: float
    control_churn: float
    assumed: float
    true_value: float | None = None

    @property
    def covers_assumption(self) -> bool:
        """Can the experiment rule out the number case 02 used?"""
        return self.ci_low <= self.assumed <= self.ci_high

    @property
    def covers_zero(self) -> bool:
        """Can the experiment rule out the campaign doing nothing at all?"""
        return self.ci_low <= 0.0 <= self.ci_high

    @property
    def assumption_error(self) -> float | None:
        """How far the assumption sat from the truth, as a multiple.

        Knowable only here. In production this line does not exist, which is the
        point: the assumption was wrong and the experiment could not say so.
        """
        if not self.true_value:
            return None
        return self.assumed / self.true_value


def measured_save_rate(itt: Estimate, control_churn: float, assumed: float,
                       true_effect: float | None = None,
                       true_baseline: float | None = None) -> SaveRate:
    """Convert an ITT into case 02's save rate, carrying its interval across.

    ``true_effect`` and ``true_baseline`` are the answer key's version of the
    same ratio — the true ITT over the churn the contacted arm would have had
    anyway. Supplied only so the report can say whether the measurement landed.
    """
    if control_churn <= 0:
        return SaveRate(float("nan"), float("nan"), float("nan"), control_churn, assumed)
    true_value = None
    if true_effect is not None and true_baseline:
        true_value = -true_effect / true_baseline
    return SaveRate(
        value=-itt.value / control_churn,
        # The interval flips because the transform negates: the most negative
        # ITT is the *highest* save rate.
        ci_low=-itt.ci_high / control_churn,
        ci_high=-itt.ci_low / control_churn,
        control_churn=control_churn,
        assumed=assumed,
        true_value=true_value,
    )


@dataclass(frozen=True)
class Repricing:
    """Case 02's targeting decision, re-priced at one save rate."""

    label: str
    save_rate: float
    profit_by_risk: float
    profit_by_value: float
    optimal_contacts: int
    optimal_profit: float

    @property
    def uplift(self) -> float:
        return self.profit_by_value - self.profit_by_risk


def reprice_case_02(churn_result, save_rates: list[tuple[str, float]],
                    capacity_share: float = 0.10) -> list[Repricing]:
    """Re-run case 02's risk-vs-value comparison at each save rate.

    Uses the population case 02 already scored, so the model, the probabilities
    and the contact budget are identical and the only thing that moves is the
    assumption under test.
    """
    out = []
    for label, rate in save_rates:
        economics = Economics(save_rate=rate)
        comparison = compare_policies(
            churn_result.probabilities,
            churn_result.monthly_revenue,
            churn_result.y_test,
            economics,
            capacity_share=capacity_share,
        )
        n_opt, profit_opt = comparison.by_value.optimal
        out.append(Repricing(
            label=label,
            save_rate=rate,
            profit_by_risk=comparison.by_risk.profit_at(comparison.capacity),
            profit_by_value=comparison.by_value.profit_at(comparison.capacity),
            optimal_contacts=n_opt,
            optimal_profit=profit_opt,
        ))
    return out
