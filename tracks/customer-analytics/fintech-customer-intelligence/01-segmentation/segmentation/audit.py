"""The question every segmentation gets asked next, and cannot answer.

*"Which segment responded best?"* It is the natural follow-up, it sounds like a
reporting task, and answering it is how a segmentation acquires a causal claim
it was never designed to support.

Case 05 established the ceiling: pooled across the whole base, the retention
experiment could not distinguish a 25% save rate from 11% or from zero. Cutting
that same experiment by segment divides the evidence again — and this module
shows what is left, using the answer key to check rather than to estimate.

**The fence, as case 03 built it.** The counterfactual table is read through
case 05's quarantined ``truth`` module and nowhere else, so exactly one file in
the track touches it. Nothing here feeds a decision: the grid, the deliverability
and the contact lists are all computed before this runs and none of them import
it. A test corrupts the table and asserts that every decision is unmoved while
these numbers move.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_INCREMENTALITY = str(Path(__file__).resolve().parents[2] / "05-campaign-incrementality")
if _INCREMENTALITY not in sys.path:
    sys.path.insert(0, _INCREMENTALITY)

from incrementality.truth import Truth, load_truth  # noqa: E402

from .data import Snapshot  # noqa: E402
from .grid import Segment  # noqa: E402


@dataclass(frozen=True)
class SegmentEffect:
    """What the campaign actually did inside one segment, from the answer key."""

    segment: str
    treated: int
    outcomes_changed: int      # customers whose churn the campaign actually flipped
    true_effect: float         # mean individual effect among the treated

    @property
    def readable(self) -> bool:
        """Is there enough here to rank this segment against another?

        Ten flipped outcomes is the point below which the ordering of segments
        is decided by which customers happened to sit near their own threshold.
        It is a judgement, stated as a number so it can be argued with rather
        than applied silently.
        """
        return self.outcomes_changed >= 10


@dataclass(frozen=True)
class CausalAudit:
    """The per-segment causal read, and whether it exists."""

    cutoff: str
    total_outcomes_changed: int
    total_treated: int
    effects: list[SegmentEffect]

    @property
    def readable_segments(self) -> int:
        return sum(1 for e in self.effects if e.readable)

    @property
    def outcomes_per_segment(self) -> float:
        return self.total_outcomes_changed / len(self.effects) if self.effects else 0.0

    @property
    def strongest(self) -> SegmentEffect | None:
        """The segment the answer key says the campaign helped most."""
        return min(self.effects, key=lambda e: e.true_effect, default=None)

    @property
    def riskiest_rank(self) -> int | None:
        """Where the highest-risk segment lands when segments are ranked by true effect.

        Reported because "target the high-risk segment, it responds best" is the
        assumption the whole exercise rests on, and here it can be checked
        against the truth instead of assumed — with the caveat that at these
        counts the ranking itself is noise, which is the finding.
        """
        if not self.effects:
            return None
        order = sorted(self.effects, key=lambda e: e.true_effect)
        for position, effect in enumerate(order, start=1):
            if effect.segment == self.effects[0].segment:
                return position
        return None


def run(tables, snapshot: Snapshot, segments: list[Segment]) -> CausalAudit:
    """Read the answer key, per segment, and report how little it says.

    ``segments`` arrives in reading order (riskiest first), and that order is
    preserved so the first entry is the segment the plan is built around.
    """
    treated = {r["customer_id"] for r in tables["campaign_exposures"] if int(r["exposed"]) == 1}
    truth: Truth = load_truth(tables, snapshot.cutoff, treated)

    effects = []
    for segment in segments:
        members = [snapshot.customer_ids[i] for i in segment.members]
        treated_here = [c for c in members if c in treated]
        effects.append(SegmentEffect(
            segment=segment.name,
            treated=len(treated_here),
            outcomes_changed=sum(1 for c in treated_here if truth.effect.get(c, 0) != 0),
            true_effect=truth.average_over(treated_here),
        ))

    return CausalAudit(
        cutoff=snapshot.cutoff,
        total_outcomes_changed=truth.n_affected,
        total_treated=len(treated),
        effects=effects,
    )
