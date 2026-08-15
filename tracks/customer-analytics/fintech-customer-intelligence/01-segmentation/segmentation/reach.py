"""Can the action actually be delivered to the people it was written for?

A segmentation ends in a sentence like *"contact this cell with a retention
offer"*. Whether that sentence can be executed is a separate question from
whether it is a good idea, it is answered by rules the analyst does not own, and
it is normally discovered by the campaign team a week before the send.

The rules are not re-implemented here. Case 03 built the permission layer out of
the shared ``contact_policy`` table, and this case imports it — so a segment's
deliverability is judged against the same rules that price an offer next door,
and the two cannot drift.

The measurement is per segment and per *offer type*, not "does this customer
have any consented channel". A cell told to send an upgrade is not reachable
because it could have received a discount.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_TRACK = Path(__file__).resolve().parents[2]
_NBO = str(_TRACK / "03-next-best-offer")
if _NBO not in sys.path:
    sys.path.insert(0, _NBO)

from nbo.data import ContactHistory, ProductLadder, load_consent, load_offers  # noqa: E402
from nbo.policy import ELIG_FAMILY, ELIG_NOT_AN_UPGRADE, ContactPolicy, CustomerFacts, evaluate  # noqa: E402

from .data import Snapshot  # noqa: E402
from .grid import Segment  # noqa: E402

_ELIGIBILITY = frozenset({ELIG_FAMILY, ELIG_NOT_AN_UPGRADE})


@dataclass(frozen=True)
class Deliverability:
    """One segment's action, and how much of the segment can receive it.

    The two refusal families are kept apart because they are different problems
    with different owners. **Contact policy** says the customer may not be
    contacted right now — consent, cool-off, arrears — and the remedy is timing
    or channel. **Eligibility** says the offer does not apply to this customer at
    all, and the remedy is that the play was written for a segment the catalogue
    cannot serve. The second is the analyst's own mistake; the first is not.
    """

    segment: str
    offer_type: str
    members: int
    reachable: int
    blocked_by_eligibility: int
    blocked_by_policy: int
    unreachable_churn: float   # what the unreachable members went on to do
    reachable_churn: float
    eligibility_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def reach(self) -> float:
        return self.reachable / self.members if self.members else 0.0

    @property
    def unreachable(self) -> int:
        return self.members - self.reachable

    @property
    def play_does_not_apply(self) -> bool:
        """Is the action mostly refused because it was never applicable?"""
        return self.blocked_by_eligibility > self.blocked_by_policy

    @property
    def dominant_reason(self) -> str | None:
        """Which product rule refuses this play most often.

        ``ELIG_NOT_AN_UPGRADE`` and ``ELIG_FAMILY`` are different mistakes.
        The first means the play contradicts the cell it was written for — the
        customers are already above the offer. The second means the catalogue
        does not sell to them at all, which is usually a sign the play wanted an
        offer that does not exist.
        """
        if not self.eligibility_reasons:
            return None
        return max(sorted(self.eligibility_reasons), key=lambda r: self.eligibility_reasons[r])


@dataclass(frozen=True)
class PermissionView:
    """The permission matrix, indexed the way this case asks about it."""

    allowed_types: dict[str, set[str]]                  # customer_id -> types they may receive
    eligibility_blocked: dict[str, dict[str, str]]      # customer_id -> {type: the product rule}

    def can_receive(self, customer_id: str, offer_type: str) -> bool:
        return offer_type in self.allowed_types.get(customer_id, set())

    def refused_as_ineligible(self, customer_id: str, offer_type: str) -> str | None:
        """The product rule refusing every offer of this type, if that is the case."""
        return self.eligibility_blocked.get(customer_id, {}).get(offer_type)


def build_permissions(tables, snapshot: Snapshot) -> PermissionView:
    """Evaluate case 03's rules over this snapshot's population."""
    offers = load_offers(tables)
    matrix = evaluate(
        tables,
        offers,
        snapshot.customer_ids,
        snapshot.cutoff,
        ContactPolicy.load(tables),
        ProductLadder.build(tables),
        load_consent(tables),
        ContactHistory.build(tables),
        CustomerFacts.build(tables, snapshot.cutoff, snapshot.customer_ids),
    )
    type_of = {offer.offer_id: offer.type for offer in offers}
    types = sorted(set(type_of.values()))

    allowed: dict[str, set[str]] = {}
    ineligible: dict[str, dict[str, str]] = {}
    for cid in snapshot.customer_ids:
        allowed[cid] = {type_of[offer_id] for offer_id in matrix.allowed_offers(cid)}
        refused: dict[str, str] = {}
        for offer_type in types:
            if offer_type in allowed[cid]:
                continue
            # Ineligible only when *every* offer of the type is refused by a
            # product rule. If one of them is merely out of policy, the play
            # applies and the obstacle is timing.
            candidates = [o for o in offers if o.type == offer_type]
            reasons = [_ELIGIBILITY & set(matrix.permissions[(cid, o.offer_id)].blocked_by)
                       for o in candidates]
            if all(reasons):
                # Attribute to the rule refusing the most offers of the type;
                # ties break alphabetically so the report is deterministic.
                counts: dict[str, int] = {}
                for hit in reasons:
                    for rule in hit:
                        counts[rule] = counts.get(rule, 0) + 1
                refused[offer_type] = max(sorted(counts), key=lambda r: counts[r])
        ineligible[cid] = refused
    return PermissionView(allowed_types=allowed, eligibility_blocked=ineligible)


@dataclass(frozen=True)
class PolicyReach:
    """Whether a segment can be contacted **at all**, ignoring which offer.

    Separated from :class:`Deliverability` because they answer different
    questions and mixing them hides both. This one isolates the contact policy:
    a customer counts as reachable if any offer in the catalogue is permitted to
    them. It is the only version in which the segments are comparable, since a
    play's own reach also depends on which channel its offer ships on and how
    many offers of that type exist.
    """

    segment: str
    mean_risk: float
    members: int
    reachable: int

    @property
    def reach(self) -> float:
        return self.reachable / self.members if self.members else 0.0


def policy_reach(
    snapshot: Snapshot,
    segments: list[Segment],
    permissions: PermissionView,
) -> list[PolicyReach]:
    """Reach under the contact policy alone, for every cell."""
    return [
        PolicyReach(
            segment=segment.name,
            mean_risk=segment.mean_risk,
            members=len(segment.members),
            reachable=sum(1 for i in segment.members
                          if permissions.allowed_types.get(snapshot.customer_ids[i])),
        )
        for segment in segments
    ]


def falls_with_risk(rows: list[PolicyReach]) -> bool:
    """Does reach decrease monotonically as risk rises, cell by cell?

    Asked rather than assumed, and on the default run the answer is **no** — so
    the report never claims it. The mechanism behind the idea is real (arrears,
    an open escalation and a recent contact are simultaneously suppression rules
    and churn drivers), but a monotone ordering of nine cells is a much stronger
    statement than the mechanism supports, and nine cells of ~500 customers do
    not deliver one.
    """
    ordered = sorted(rows, key=lambda r: r.mean_risk)
    return all(a.reach >= b.reach for a, b in zip(ordered, ordered[1:], strict=False))


def risk_band_gap(rows: list[PolicyReach], bands: int = 3) -> tuple[float, float]:
    """Reach of the lowest-risk third and of the highest-risk third.

    The comparison that does survive. Cell-level ordering is noise at this
    scale; the two ends of the risk axis are a third of the base each, and their
    difference is stable in direction across seeds even though its size is not.
    """
    ordered = sorted(rows, key=lambda r: r.mean_risk)
    per_band = max(1, len(ordered) // bands)
    low, high = ordered[:per_band], ordered[-per_band:]

    def _pooled(group: list[PolicyReach]) -> float:
        members = sum(r.members for r in group)
        return sum(r.reachable for r in group) / members if members else 0.0

    return _pooled(low), _pooled(high)


def deliverability(
    snapshot: Snapshot,
    segments: list[Segment],
    permissions: PermissionView,
) -> list[Deliverability]:
    """For each segment that wants to contact somebody, how many it can reach."""
    rows = []
    for segment in segments:
        if not segment.play.has_offer:
            continue
        offer_type = segment.play.offer_type
        reachable, unreachable = [], []
        reasons: dict[str, int] = {}
        for i in segment.members:
            cid = snapshot.customer_ids[i]
            if permissions.can_receive(cid, offer_type):
                reachable.append(i)
                continue
            unreachable.append(i)
            rule = permissions.refused_as_ineligible(cid, offer_type)
            if rule:
                reasons[rule] = reasons.get(rule, 0) + 1
        rows.append(Deliverability(
            segment=segment.name,
            offer_type=offer_type,
            members=len(segment.members),
            reachable=len(reachable),
            blocked_by_eligibility=sum(reasons.values()),
            blocked_by_policy=len(unreachable) - sum(reasons.values()),
            reachable_churn=_rate(snapshot, reachable),
            unreachable_churn=_rate(snapshot, unreachable),
            eligibility_reasons=reasons,
        ))
    return rows


def _rate(snapshot: Snapshot, rows: list[int]) -> float:
    return sum(snapshot.labels[i] for i in rows) / len(rows) if rows else 0.0
