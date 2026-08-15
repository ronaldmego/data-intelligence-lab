"""Does a segment last long enough to act on?

A segmentation is built once and then used for a quarter — the plan is written
against it, the creative is briefed against it, the budget is split by it. That
only works if a customer is still in the cell that earned them their action by
the time the action reaches them.

The data model emits two observation cutoffs six months apart, so this is
measurable rather than assumable: apply the same rule at both, and count.

**Two traps this module is built around.**

*The first is the flattering measurement.* Scoring the earlier cutoff with the
model that was fitted on it is in-sample: the score has partly memorised those
customers, which makes them look more like themselves than they are. Migration
measured that way is a floor. So it is also measured cross-fitted — the model
fitted on one fold, scoring the other — and both numbers are reported, because
the gap between them is itself the evidence that the floor is a floor.

*The second is the aggregate that hides it.* Re-cutting the axes at each cutoff
keeps every cell the same size by construction, so the segment sizes barely move
and the dashboard looks stable. That is exactly the illusion: the distribution is
stationary while the individuals underneath it are not.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .data import Snapshot
from .grid import Cuts, Play


@dataclass(frozen=True)
class Migration:
    """How much of the base changed cell between two cutoffs."""

    basis: str                  # how the earlier score was produced
    months_apart: int
    n: int
    risk_band_changed: int
    value_band_changed: int
    cell_changed: int
    segment_changed: int
    contact_decision_changed: int
    flows: Counter = field(default_factory=Counter)   # (from segment, to segment) -> n
    sizes_before: Counter = field(default_factory=Counter)
    sizes_after: Counter = field(default_factory=Counter)

    def share(self, count: int) -> float:
        return count / self.n if self.n else 0.0

    @property
    def largest_flows(self) -> list[tuple[tuple[str, str], int]]:
        """The biggest moves between *different* segments."""
        return [(k, v) for k, v in self.flows.most_common() if k[0] != k[1]]

    @property
    def size_drift(self) -> float:
        """The largest change in any segment's share of the base.

        Near zero whenever the axes are re-cut at each cutoff — which is the
        point being made, not a bug being reported.
        """
        total_before = sum(self.sizes_before.values()) or 1
        total_after = sum(self.sizes_after.values()) or 1
        names = set(self.sizes_before) | set(self.sizes_after)
        return max(
            (abs(self.sizes_before[n] / total_before - self.sizes_after[n] / total_after) for n in names),
            default=0.0,
        )


def measure(
    before: Snapshot,
    after: Snapshot,
    cuts_before: Cuts,
    cuts_after: Cuts,
    playbook: dict[tuple[int, int], Play],
    basis: str,
    months_apart: int,
    risk_before: dict[str, float] | None = None,
) -> Migration:
    """Compare cell membership at two cutoffs, over the customers present in both.

    ``risk_before`` overrides the earlier snapshot's own risk scores, which is
    how the cross-fitted variant is produced without rebuilding the snapshot:
    same customers, same features, a score from a model that never saw them.
    Customers missing from it are skipped rather than filled in.
    """
    index_before = before.index_of()
    risk_lookup = risk_before if risk_before is not None else {
        cid: before.risk[i] for cid, i in index_before.items()
    }
    # Re-cut the earlier axis on whatever scores are actually in use: a threshold
    # taken from one model's scale and applied to another's would manufacture
    # migration out of a units mismatch.
    if risk_before is not None:
        from .grid import quantile_cuts
        cuts_before = Cuts(risk=quantile_cuts(list(risk_before.values())), value=cuts_before.value)

    counts = dict(risk=0, value=0, cell=0, segment=0, contact=0)
    flows: Counter = Counter()
    sizes_before: Counter = Counter()
    sizes_after: Counter = Counter()
    n = 0

    for after_index, cid in enumerate(after.customer_ids):
        before_index = index_before.get(cid)
        if before_index is None or cid not in risk_lookup:
            continue
        n += 1

        old = cuts_before.cell_of(risk_lookup[cid], before.value[before_index])
        new = cuts_after.cell_of(after.risk[after_index], after.value[after_index])

        if old[0] != new[0]:
            counts["risk"] += 1
        if old[1] != new[1]:
            counts["value"] += 1
        if old != new:
            counts["cell"] += 1

        play_old, play_new = playbook.get(old), playbook.get(new)
        if play_old is None or play_new is None:
            continue
        sizes_before[play_old.segment] += 1
        sizes_after[play_new.segment] += 1
        flows[(play_old.segment, play_new.segment)] += 1
        if play_old.segment != play_new.segment:
            counts["segment"] += 1
        if play_old.contacts != play_new.contacts:
            counts["contact"] += 1

    return Migration(
        basis=basis,
        months_apart=months_apart,
        n=n,
        risk_band_changed=counts["risk"],
        value_band_changed=counts["value"],
        cell_changed=counts["cell"],
        segment_changed=counts["segment"],
        contact_decision_changed=counts["contact"],
        flows=flows,
        sizes_before=sizes_before,
        sizes_after=sizes_after,
    )
