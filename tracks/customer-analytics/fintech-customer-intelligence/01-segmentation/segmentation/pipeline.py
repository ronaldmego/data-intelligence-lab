"""The case end to end.

The order matters and is worth reading once. Everything that produces a
*decision* — the grid, the deliverability of each action, the two contact lists
— runs before anything that reads the answer key. The causal audit is last, and
nothing downstream of it exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import audit as causal_audit
from . import decision, reach, rfm, stability
from .data import (
    Population,
    RiskModel,
    Snapshot,
    Tables,
    build_features,
    build_snapshot,
    load_tables,
    scoreable_population,
    stride,
)
from .grid import Cuts, Play, Segment, build_segments, load_playbook, quantile_cuts

# The save rate case 05 measured. Case 02 assumed 0.25 and case 05 showed the
# experiment cannot support it; every case since uses the measured figure, and
# imports rather than restates it.
try:  # pragma: no cover - the import path is exercised in the case run
    import sys
    from pathlib import Path
    _NBO = str(Path(__file__).resolve().parents[2] / "03-next-best-offer")
    if _NBO not in sys.path:
        sys.path.insert(0, _NBO)
    from nbo.value import MEASURED_SAVE_RATE
except ImportError:  # pragma: no cover
    MEASURED_SAVE_RATE = 0.124

from churn.economics import Economics  # noqa: E402


@dataclass
class CaseResult:
    """Every number the report needs."""

    tables: Tables
    train: Population
    test: Population
    before: Snapshot
    after: Snapshot
    cuts: Cuts
    playbook: dict[tuple[int, int], Play]
    segments: list[Segment] = field(default_factory=list)
    letters: list[rfm.Letter] = field(default_factory=list)
    repaired_recency: rfm.Letter | None = None
    frequency_tenure_correlation: float = 0.0
    migrations: list[stability.Migration] = field(default_factory=list)
    deliverability: list[reach.Deliverability] = field(default_factory=list)
    policy_reach: list[reach.PolicyReach] = field(default_factory=list)
    reach_falls_with_risk: bool = False
    reach_low_risk_third: float = 0.0
    reach_high_risk_third: float = 0.0
    decision: decision.DecisionTest | None = None
    causal: causal_audit.CausalAudit | None = None
    economics: Economics = field(default_factory=Economics)

    @property
    def contacting_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.play.contacts]

    @property
    def profitable_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.worth_contacting]

    @property
    def honest_migration(self) -> stability.Migration:
        """The cross-fitted one — the number to quote."""
        return next((m for m in self.migrations if m.basis == "cross-fitted"), self.migrations[0])

    @property
    def in_sample_migration(self) -> stability.Migration:
        return next((m for m in self.migrations if m.basis == "in-sample"), self.migrations[0])


def _months_between(earlier: str, later: str) -> int:
    a, b = date.fromisoformat(earlier), date.fromisoformat(later)
    return (b.year - a.year) * 12 + (b.month - a.month)


def run_case(
    tables: Tables | None = None,
    bands: int = 3,
    capacity_share: float = 0.10,
    save_rate: float = MEASURED_SAVE_RATE,
    playbook_path=None,
) -> CaseResult:
    """Build the segmentation, then attack it four ways."""
    tables = tables if tables is not None else load_tables()
    economics = Economics(save_rate=save_rate)

    train = scoreable_population(tables, "churn_labels_prior")
    test = scoreable_population(tables, "churn_labels", exclude_churned_in="churn_labels_prior")

    x_train = build_features(tables, train.cutoff, train.customer_ids)
    x_test = build_features(tables, test.cutoff, test.customer_ids)
    y_train = [train.labels[c] for c in train.customer_ids]

    # Case 02's fit: four fifths to fit, one fifth reserved for the calibrator.
    fit_rows, calibration_rows = stride(len(y_train), every=5)
    model = RiskModel.fit(x_train, y_train, fit_rows, calibration_rows)

    before = build_snapshot(tables, train, model, features=x_train)
    after = build_snapshot(tables, test, model, features=x_test)

    playbook = load_playbook(playbook_path) if playbook_path else load_playbook()
    cuts = Cuts.from_snapshot(after, bands)
    cuts_before = Cuts.from_snapshot(before, bands)

    result = CaseResult(
        tables=tables, train=train, test=test, before=before, after=after,
        cuts=cuts, playbook=playbook, economics=economics,
    )

    # --- what the grid is ------------------------------------------------
    result.segments = build_segments(after, cuts, playbook, economics)

    months = sorted({r["period_month"] for r in tables["activity_monthly"]})
    labels = {c: test.labels[c] for c in test.customer_ids}
    result.letters = rfm.classic_rfm(tables, test.cutoff, test.customer_ids, labels, months)
    result.repaired_recency = rfm.engagement_recency(tables, test.cutoff, test.customer_ids, labels, months)
    frequency = next(letter for letter in result.letters if letter.symbol == "F")
    result.frequency_tenure_correlation = rfm.correlation(
        frequency.values, rfm.tenure_of(tables, test.customer_ids),
    )

    # --- does it survive six months? -------------------------------------
    gap = _months_between(train.cutoff, test.cutoff)
    result.migrations.append(stability.measure(
        before, after, cuts_before, cuts, playbook, basis="in-sample", months_apart=gap,
    ))

    # The same comparison with the earlier score produced by a model that never
    # saw those customers: fit on the calibration fold, score the rest.
    cross = RiskModel.fit(x_train, y_train, calibration_rows, fit_rows)
    cross_scores = cross.probabilities([x_train[i] for i in fit_rows])
    result.migrations.append(stability.measure(
        before, after, cuts_before, cuts, playbook, basis="cross-fitted", months_apart=gap,
        risk_before={train.customer_ids[row]: score
                     for row, score in zip(fit_rows, cross_scores, strict=True)},
    ))

    # --- can the action be delivered? ------------------------------------
    permissions = reach.build_permissions(tables, after)
    result.policy_reach = reach.policy_reach(after, result.segments, permissions)
    result.reach_falls_with_risk = reach.falls_with_risk(result.policy_reach)
    result.reach_low_risk_third, result.reach_high_risk_third = reach.risk_band_gap(
        result.policy_reach, bands,
    )
    result.deliverability = reach.deliverability(after, result.segments, permissions)

    # --- does the grid change the decision? ------------------------------
    result.decision = decision.run(after, result.segments, economics, capacity_share)

    # --- last, and downstream of nothing ---------------------------------
    result.causal = causal_audit.run(tables, after, result.segments)
    return result


__all__ = ["CaseResult", "MEASURED_SAVE_RATE", "quantile_cuts", "run_case"]
