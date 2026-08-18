"""Turning scores and permissions into a contact list, under a capacity limit.

The arithmetic here is small. What it is for is a question that sounds like an
implementation detail and is not:

> Do you rank first and then remove who you are not allowed to contact, or
> remove first and then rank?

Both are described as "we respect consent". They produce different lists, and
one of them quietly under-delivers: taking the top *K* by value and then
suppressing leaves fewer than *K* contacts, and the capacity freed by the
suppressed customers is never refilled. The gap is not a rounding error when
permission correlates with rank — and it does, because the customers most worth
contacting are systematically the ones the rules protect.

The third list is the one nobody is allowed to send: value-ranked with the
governance layer switched off. It exists to price the constraint honestly. A
governance layer whose cost is never measured gets argued about with anecdotes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .data import Offer
from .policy import PermissionMatrix
from .value import OfferEconomics, OfferValue


@dataclass(frozen=True)
class Assignment:
    """One customer, the offer chosen for them, and what it is worth."""

    customer_id: str
    offer_id: str
    objective: str
    channel: str
    expected_value: float
    churn_probability: float


@dataclass(frozen=True)
class Plan:
    """A contact list: who gets contacted, with what, in what order."""

    name: str
    assignments: tuple[Assignment, ...]
    capacity: int
    suppressed_after_ranking: int = 0   # only non-zero for rank-then-filter

    def __len__(self) -> int:
        return len(self.assignments)

    @property
    def expected_value(self) -> float:
        return sum(a.expected_value for a in self.assignments)

    @property
    def fill_rate(self) -> float:
        return len(self.assignments) / self.capacity if self.capacity else 0.0

    @property
    def customers(self) -> set[str]:
        return {a.customer_id for a in self.assignments}

    @property
    def mean_churn_probability(self) -> float:
        if not self.assignments:
            return 0.0
        return sum(a.churn_probability for a in self.assignments) / len(self.assignments)

    def offer_mix(self) -> dict[str, int]:
        mix: dict[str, int] = {}
        for a in self.assignments:
            mix[a.offer_id] = mix.get(a.offer_id, 0) + 1
        return dict(sorted(mix.items()))

    def objective_mix(self) -> dict[str, int]:
        mix: dict[str, int] = {}
        for a in self.assignments:
            mix[a.objective] = mix.get(a.objective, 0) + 1
        return dict(sorted(mix.items()))

    def realised_churn_rate(self, labels: dict[str, int]) -> float:
        contacted = [labels[a.customer_id] for a in self.assignments if a.customer_id in labels]
        return sum(contacted) / len(contacted) if contacted else 0.0

    def overlap_with(self, other: Plan) -> float:
        if not self.assignments:
            return 0.0
        return len(self.customers & other.customers) / len(self.assignments)


def _best_offer(
    customer_id: str,
    offers: list[Offer],
    values: dict[tuple[str, str], OfferValue],
    permitted: list[str] | None,
) -> Assignment | None:
    """The single best offer for one customer.

    ``permitted`` restricts the choice; ``None`` means the governance layer is
    not consulted. One offer per customer is itself a policy rule
    (``POL_ONE_OFFER``) — it is enforced here rather than in the permission
    matrix because it is a constraint on the *assignment*, not on whether an
    individual offer is allowed.
    """
    allowed = set(permitted) if permitted is not None else None
    best: Assignment | None = None
    for offer in offers:
        if allowed is not None and offer.offer_id not in allowed:
            continue
        value = values[(customer_id, offer.offer_id)]
        # A negative expected value is not an offer, it is a donation.
        if value.expected_value <= 0:
            continue
        if best is None or value.expected_value > best.expected_value:
            best = Assignment(
                customer_id=customer_id,
                offer_id=offer.offer_id,
                objective=offer.objective,
                channel=offer.channel,
                expected_value=value.expected_value,
                churn_probability=value.churn_probability,
            )
    return best


def _rank(assignments: list[Assignment]) -> list[Assignment]:
    """Best first; ties broken on customer_id so the output is deterministic."""
    return sorted(assignments, key=lambda a: (-a.expected_value, a.customer_id))


def best_unconstrained_offers(
    customer_ids: list[str],
    offers: list[Offer],
    values: dict[tuple[str, str], OfferValue],
) -> dict[str, str]:
    """The offer each customer would get if no rule applied.

    This is what makes "which rule removed this customer?" answerable. A rule
    that refuses an offer nobody would have sent has not removed anybody, and
    counting those refusals as its cost inflates every rule that touches a large
    catalogue.
    """
    best = {}
    for cid in customer_ids:
        assignment = _best_offer(cid, offers, values, None)
        if assignment is not None:
            best[cid] = assignment.offer_id
    return best


def filter_then_rank(
    customer_ids: list[str],
    offers: list[Offer],
    values: dict[tuple[str, str], OfferValue],
    matrix: PermissionMatrix,
    capacity: int,
    name: str = "governed (filter, then rank)",
) -> Plan:
    """The correct construction: choose among permitted offers, then rank."""
    chosen = []
    for cid in customer_ids:
        assignment = _best_offer(cid, offers, values, matrix.allowed_offers(cid))
        if assignment is not None:
            chosen.append(assignment)
    return Plan(name=name, assignments=tuple(_rank(chosen)[:capacity]), capacity=capacity)


def rank_then_filter(
    customer_ids: list[str],
    offers: list[Offer],
    values: dict[tuple[str, str], OfferValue],
    matrix: PermissionMatrix,
    capacity: int,
    name: str = "rank, then suppress",
) -> Plan:
    """The common construction: rank on the unconstrained best offer, take the
    top *K*, then drop whoever turns out not to be contactable.

    Nothing about this looks wrong in a pipeline diagram, and the suppression
    step is usually owned by a different team from the scoring step. The result
    is a campaign that reports "we contacted the top 500" and contacted 300.
    """
    chosen = []
    for cid in customer_ids:
        assignment = _best_offer(cid, offers, values, None)
        if assignment is not None:
            chosen.append(assignment)

    top = _rank(chosen)[:capacity]
    survivors = tuple(a for a in top if matrix.allowed(a.customer_id, a.offer_id))
    return Plan(name=name, assignments=survivors, capacity=capacity,
                suppressed_after_ranking=len(top) - len(survivors))


def ungoverned(
    customer_ids: list[str],
    offers: list[Offer],
    values: dict[tuple[str, str], OfferValue],
    capacity: int,
    name: str = "ungoverned (what the plan promised)",
) -> Plan:
    """The list the business would send with no governance layer at all."""
    chosen = []
    for cid in customer_ids:
        assignment = _best_offer(cid, offers, values, None)
        if assignment is not None:
            chosen.append(assignment)
    return Plan(name=name, assignments=tuple(_rank(chosen)[:capacity]), capacity=capacity)


# --- what the retention slice actually produced -----------------------------


def realised_retention_profit(
    plan: Plan,
    labels: dict[str, int],
    revenue: dict[str, float],
    offers: list[Offer],
    economics: OfferEconomics,
) -> tuple[float, int]:
    """Profit booked on the plan's retention contacts, against what happened.

    Only the retention slice can be scored this way. Whether a customer churned
    is observed; whether they would have accepted an upgrade they were never
    sent is not, so the growth offers stay in expectation and this number is
    reported beside the expected value rather than instead of it.

    As in case 02, the save rate is applied as an expectation over the customers
    who did churn — the individual counterfactual is unknowable. Case 05
    measured that rate; this uses the measured one.
    """
    offer_by_id = {o.offer_id: o for o in offers}
    total, n = 0.0, 0
    for a in plan.assignments:
        offer = offer_by_id[a.offer_id]
        if not offer.is_retention or a.customer_id not in labels:
            continue
        n += 1
        priced = replace(
            economics.base,
            contact_cost=economics.contact_cost(offer.channel),
            offer_cost=economics.offer_cost(offer, revenue[a.customer_id]),
        )
        if labels[a.customer_id]:
            total += priced.save_rate * (
                priced.value_at_risk(revenue[a.customer_id]) - priced.offer_cost
            ) - priced.contact_cost
        else:
            total -= priced.contact_cost
    return total, n


@dataclass(frozen=True)
class PlanComparison:
    """The three lists, side by side."""

    governed: Plan
    suppressed: Plan
    ungoverned: Plan

    @property
    def governance_cost(self) -> float:
        """Expected value the governance layer costs, done correctly."""
        return self.ungoverned.expected_value - self.governed.expected_value

    @property
    def ordering_cost(self) -> float:
        """Expected value lost purely to doing the filtering in the wrong order."""
        return self.governed.expected_value - self.suppressed.expected_value

    @property
    def unfilled_capacity(self) -> int:
        return self.suppressed.capacity - len(self.suppressed)
