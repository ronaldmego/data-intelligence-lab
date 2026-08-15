"""The test a segmentation has to pass: does it change what anyone does?

This is the part that usually goes unasked. A segmentation is judged on whether
the clusters look tidy, whether the names are evocative, whether the slide lands
— never against the decision that would have been taken without it.

So the same budget is spent twice on the same customers. Once by the continuous
ranking cases 02 and 03 already publish, and once by the playbook: contact the
cells the playbook says to contact, best customers first. Then both lists are
priced with **case 02's own profit accounting**, imported rather than restated,
so the comparison cannot be won by a different definition of value.

The expected result is that the ranking wins, and it does. That is not an
argument against segmenting — it is an argument against segmenting *for this*.
A ranking answers "who", in one number, better than a nine-cell grid can. It has
nothing at all to say about the customers it does not rank into the budget,
which is most of them, and nothing about what to send the ones it does.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_CHURN_CASE = str(Path(__file__).resolve().parents[2] / "02-churn-prediction")
if _CHURN_CASE not in sys.path:
    sys.path.insert(0, _CHURN_CASE)

from churn.economics import Economics, build_targeting  # noqa: E402

from .data import Snapshot  # noqa: E402
from .grid import Segment  # noqa: E402

# Large enough to dominate the within-segment tiebreak, so the composite
# priority sorts by segment first and by customer value inside it.
_SEGMENT_STRIDE = 1e6
_NEVER = -1e12


@dataclass(frozen=True)
class ContactList:
    """One way of spending the budget, and what it returned."""

    name: str
    rows: list[int]
    realised_profit: float
    realised_churn: float

    def __len__(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class DecisionTest:
    """Two lists for the same budget, and what the grid adds beyond them."""

    capacity: int
    by_expected_value: ContactList
    by_segment: ContactList
    overlap: float
    contacting_segments: int
    non_contacting_customers: int
    distinct_offer_types: int

    @property
    def profit_gap(self) -> float:
        """What the grid costs when used as the selector."""
        return self.by_expected_value.realised_profit - self.by_segment.realised_profit

    @property
    def profit_gap_share(self) -> float:
        best = self.by_expected_value.realised_profit
        return self.profit_gap / best if best else 0.0


def _list_from(name: str, priority: list[float], snapshot: Snapshot,
               economics: Economics, capacity: int) -> ContactList:
    """Rank by ``priority`` and price the top ``capacity`` with case 02's accounting."""
    targeting = build_targeting(
        name, priority, snapshot.risk, snapshot.value, snapshot.labels, economics,
        steps=max(20, capacity),
    )
    rows = targeting.order[:capacity]
    return ContactList(
        name=name,
        rows=rows,
        realised_profit=targeting.profit_at(capacity),
        realised_churn=sum(snapshot.labels[i] for i in rows) / len(rows) if rows else 0.0,
    )


def run(
    snapshot: Snapshot,
    segments: list[Segment],
    economics: Economics,
    capacity_share: float = 0.10,
) -> DecisionTest:
    """Spend the same budget both ways and compare."""
    capacity = max(1, int(len(snapshot) * capacity_share))

    continuous = [economics.expected_value(r, v)
                  for r, v in zip(snapshot.risk, snapshot.value, strict=True)]

    # The playbook's own ordering: cells that contact, richest cell first, and
    # customers ranked by value inside their cell. A campaign team with a
    # segmentation and a budget does exactly this.
    contacting = [s for s in segments if s.play.contacts]
    ranked = sorted(contacting, key=lambda s: -s.expected_value_per_customer)
    by_segment = [_NEVER] * len(snapshot)
    for position, segment in enumerate(ranked):
        tier = (len(ranked) - position) * _SEGMENT_STRIDE
        for i in segment.members:
            by_segment[i] = tier + snapshot.value[i]

    value_list = _list_from("by expected value", continuous, snapshot, economics, capacity)
    segment_list = _list_from("by segment playbook", by_segment, snapshot, economics, capacity)

    overlap = len(set(value_list.rows) & set(segment_list.rows)) / capacity
    return DecisionTest(
        capacity=capacity,
        by_expected_value=value_list,
        by_segment=segment_list,
        overlap=overlap,
        contacting_segments=len(contacting),
        non_contacting_customers=sum(len(s) for s in segments if not s.play.contacts),
        distinct_offer_types=len({s.play.offer_type for s in segments if s.play.has_offer}),
    )
