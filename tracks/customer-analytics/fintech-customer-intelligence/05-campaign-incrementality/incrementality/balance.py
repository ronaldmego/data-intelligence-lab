"""The diagnostic every experiment readout is supposed to open with.

If the coin flip was fair, the two arms should look alike on everything that was
already true before it. Comparing them is the one check available *without* the
answer key — so it is the check a real analyst runs, and the reason it is here is
to find out how much protection it actually buys.

Two rules make it honest:

* **Only pre-campaign facts.** Covariates are built as of the month before the
  campaign ran. Anything measured afterwards may have been changed by the
  campaign, and balancing on it would be balancing away the effect.
* **A standardised difference is judged against its own sampling noise**, not
  against a folklore threshold. With enough covariates, some will exceed 0.10 in
  a perfectly fair randomisation, and reporting those as evidence of a broken
  experiment is its own error.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

# Reuse case 02's feature builder rather than writing a second one: it is tested,
# and its cutoff boundary is exactly the guarantee this module needs — covariates
# built as of a date, with nothing after it.
_CHURN_CASE = Path(__file__).resolve().parents[2] / "02-churn-prediction"
if str(_CHURN_CASE) not in sys.path:
    sys.path.insert(0, str(_CHURN_CASE))

from churn.features import FEATURE_NAMES, build_features  # noqa: E402


@dataclass(frozen=True)
class Covariate:
    """One pre-campaign characteristic, compared across the arms."""

    name: str
    mean_exposed: float
    mean_control: float
    standardised_difference: float
    standard_error: float

    @property
    def beyond_noise(self) -> bool:
        """Larger than two standard errors — a difference the flip struggles to explain."""
        return abs(self.standardised_difference) > 2 * self.standard_error

    @property
    def beyond_convention(self) -> bool:
        """Larger than the customary 0.10 threshold."""
        return abs(self.standardised_difference) > 0.10


@dataclass(frozen=True)
class BalanceReport:
    campaign_id: str
    cutoff: str
    covariates: list[Covariate]
    n_exposed: int
    n_control: int

    @property
    def n_beyond_noise(self) -> int:
        return sum(1 for c in self.covariates if c.beyond_noise)

    @property
    def n_beyond_convention(self) -> int:
        return sum(1 for c in self.covariates if c.beyond_convention)

    @property
    def expected_beyond_convention(self) -> float:
        """How many covariates would clear 0.10 under a perfectly fair flip.

        The comparison that stops the balance table from being read as damning
        whenever it has enough rows. A standardised difference has a sampling
        distribution of its own; 0.10 is a fixed number, so with small arms it
        is routinely exceeded by chance.
        """
        if not self.covariates:
            return 0.0
        se = self.covariates[0].standard_error
        if se <= 0:
            return 0.0
        tail = 2 * (1 - 0.5 * (1 + math.erf(0.10 / (se * math.sqrt(2)))))
        return len(self.covariates) * tail

    @property
    def worst(self) -> list[Covariate]:
        return sorted(self.covariates, key=lambda c: -abs(c.standardised_difference))

    @property
    def verdict(self) -> str:
        """What the table supports — deliberately not a pass/fail stamp."""
        if self.n_beyond_noise == 0:
            return "no imbalance beyond sampling noise"
        if self.n_beyond_noise <= max(1, len(self.covariates) // 20):
            return "consistent with a fair flip (about as many as chance predicts)"
        return "more imbalance than chance predicts — treat the estimate with suspicion"


def check_balance(tables, audience) -> BalanceReport:
    """Compare the arms on every pre-campaign covariate case 02 already defines."""
    ids = audience.members
    exposed = set(audience.exposed)
    matrix = build_features(tables, audience.campaign.prior_month, ids)

    n_e = len(audience.exposed)
    n_c = len(audience.control)
    # Sampling SD of a standardised mean difference under random assignment.
    se = math.sqrt(1 / n_e + 1 / n_c) if n_e and n_c else float("inf")

    covariates = []
    for column, name in enumerate(FEATURE_NAMES):
        a = [matrix[i][column] for i, cid in enumerate(ids) if cid in exposed]
        b = [matrix[i][column] for i, cid in enumerate(ids) if cid not in exposed]
        mean_a, mean_b = _mean(a), _mean(b)
        pooled_sd = math.sqrt((_variance(a, mean_a) + _variance(b, mean_b)) / 2)
        if pooled_sd == 0:
            # Constant before the campaign — carries no information about the
            # flip. Dropped rather than reported as perfectly balanced, which
            # would pad the table with rows that can never fail.
            continue
        covariates.append(Covariate(
            name=name,
            mean_exposed=mean_a,
            mean_control=mean_b,
            standardised_difference=(mean_a - mean_b) / pooled_sd,
            standard_error=se,
        ))

    return BalanceReport(
        campaign_id=audience.campaign.campaign_id,
        cutoff=audience.campaign.prior_month,
        covariates=covariates,
        n_exposed=n_e,
        n_control=n_c,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _variance(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)
