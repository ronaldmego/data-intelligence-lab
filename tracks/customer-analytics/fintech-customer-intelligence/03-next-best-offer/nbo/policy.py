"""The governance layer: which offers a customer is *allowed* to receive.

This runs before any score is looked at, and it answers a different question
from the model. The model ranks; this decides who is on the list at all.

Two families of rule, kept apart on purpose because they have different owners
and different failure modes:

* **eligibility** — a property of the offer and the customer's product. Offering a
  credit-only upgrade to a prepaid line, or "upgrade to M" to somebody already
  on L, is not a compliance breach: it is a broken product rule, and it is
  embarrassing in a way that costs response rates rather than fines. Derived
  from the shared catalogue (``offers.eligible_family``,
  ``offers.upgrade_to_rank``) so every consumer reads the same definition.
* **contact policy** — consent, cool-off, frequency caps, arrears, open
  complaints. Read from the shared ``contact_policy`` table, not from constants
  here, so the rules can be audited and changed without touching this code.

Every refusal is recorded with the rule that caused it. A permission layer that
returns a boolean is unauditable: when somebody asks why a customer was left out
of a campaign, "the filter removed them" is not an answer, and the absence of an
answer is what gets the filter switched off.

**Order does not change the outcome here** — a pair is permitted only if every
rule allows it — but order *does* change attribution, which is why the cost of a
rule is reported two ways: how many pairs it blocks, and how many it is the only
rule blocking. The first double-counts, the second understates, and quoting
either one alone is how a rule gets blamed for a cost it shares.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data import Contact, ContactHistory, Offer, ProductLadder, Tables, _float, _int

# Rule identifiers, as they appear in the shared contact_policy table.
CONSENT = "require_channel_consent"
COOL_OFF = "min_days_since_last_contact"
FREQ_CAP = "max_contacts_per_365d"
ARREARS = "max_failed_invoices_6m"
OPEN_ESC = "block_if_unresolved_escalation"
ONE_OFFER = "max_offers_per_wave"

# Eligibility refusals are not in the policy table — they come from the product
# catalogue — so they carry their own identifiers.
ELIG_FAMILY = "ELIG_FAMILY"
ELIG_NOT_AN_UPGRADE = "ELIG_NOT_AN_UPGRADE"


@dataclass(frozen=True)
class Rule:
    """One declared contact-policy rule."""

    policy_id: str
    rule: str
    value: float
    unit: str
    applies_to: frozenset[str]  # campaign objectives, or {'all'}
    rationale: str

    def covers(self, objective: str) -> bool:
        return "all" in self.applies_to or objective in self.applies_to


@dataclass(frozen=True)
class ContactPolicy:
    """The contact policy as read from the data model."""

    rules: dict[str, Rule]

    @classmethod
    def load(cls, tables: Tables) -> ContactPolicy:
        rules = {}
        for row in tables["contact_policy"]:
            rules[row["rule"]] = Rule(
                policy_id=row["policy_id"],
                rule=row["rule"],
                value=_float(row["value"]),
                unit=row["unit"],
                applies_to=frozenset(part.strip() for part in row["applies_to"].split(",")),
                rationale=row["rationale"],
            )
        return cls(rules=rules)

    def get(self, rule: str) -> Rule | None:
        return self.rules.get(rule)

    def value_of(self, rule: str, default: float) -> float:
        found = self.get(rule)
        return default if found is None else found.value

    def replace(self, rule: str, value: float) -> ContactPolicy:
        """A copy with one rule's parameter changed.

        Used by the sensitivity analysis, which is the only honest way to
        present a policy: not "the policy costs X" but "this parameter costs
        this much, and here is the curve".
        """
        found = self.rules[rule]
        rules = dict(self.rules)
        rules[rule] = Rule(found.policy_id, found.rule, value, found.unit,
                           found.applies_to, found.rationale)
        return ContactPolicy(rules=rules)


@dataclass(frozen=True)
class CustomerFacts:
    """The per-customer facts the contact policy asks about.

    Computed once, strictly from facts dated on or before the cutoff — the same
    discipline case 02 applies to features. A suppression rule that reads a fact
    from after the decision is a leak too, and a quieter one, because nobody
    thinks of the exclusion list as a model.
    """

    failed_invoices_6m: dict[str, int]
    unresolved_escalations: dict[str, int]

    @classmethod
    def build(cls, tables: Tables, cutoff: str, customer_ids: list[str]) -> CustomerFacts:
        wanted = set(customer_ids)

        months = sorted({r["period_month"] for r in tables["billing"] if r["period_month"] <= cutoff})
        recent = set(months[-6:])
        failed: dict[str, int] = {cid: 0 for cid in customer_ids}
        for row in tables["billing"]:
            if row["customer_id"] in wanted and row["period_month"] in recent and row["status"] == "failed":
                failed[row["customer_id"]] += 1

        unresolved: dict[str, int] = {cid: 0 for cid in customer_ids}
        for row in tables["support_interactions"]:
            if (row["customer_id"] in wanted and row["period_month"] <= cutoff
                    and _int(row["escalated"]) == 1 and _int(row["resolved"]) == 0):
                unresolved[row["customer_id"]] += 1

        return cls(failed_invoices_6m=failed, unresolved_escalations=unresolved)


@dataclass(frozen=True)
class Permission:
    """Whether one customer may be sent one offer, and if not, why not."""

    customer_id: str
    offer_id: str
    blocked_by: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return not self.blocked_by


@dataclass
class PermissionMatrix:
    """Every (customer, offer) pair, with its refusals."""

    permissions: dict[tuple[str, str], Permission] = field(default_factory=dict)
    customer_ids: list[str] = field(default_factory=list)
    offer_ids: list[str] = field(default_factory=list)

    def allowed(self, customer_id: str, offer_id: str) -> bool:
        return self.permissions[(customer_id, offer_id)].allowed

    def allowed_offers(self, customer_id: str) -> list[str]:
        return [o for o in self.offer_ids if self.allowed(customer_id, o)]

    def reachable_customers(self) -> list[str]:
        """Customers with at least one permitted offer."""
        return [c for c in self.customer_ids if self.allowed_offers(c)]

    def blocked_pairs(self, rule: str) -> int:
        """Pairs this rule refuses — including those other rules also refuse."""
        return sum(1 for p in self.permissions.values() if rule in p.blocked_by)

    def sole_blocker_pairs(self, rule: str) -> int:
        """Pairs this rule refuses *alone*: the cost of removing it."""
        return sum(1 for p in self.permissions.values() if p.blocked_by == (rule,))

    def rules_fired(self) -> list[str]:
        seen: list[str] = []
        for permission in self.permissions.values():
            for rule in permission.blocked_by:
                if rule not in seen:
                    seen.append(rule)
        return seen


def _eligibility_refusals(offer: Offer, product_id: str, ladder: ProductLadder) -> list[str]:
    """Product-rule refusals, read off the catalogue."""
    refusals = []
    if offer.eligible_family != "any" and ladder.family[product_id] != offer.eligible_family:
        refusals.append(ELIG_FAMILY)
    if offer.upgrade_to_rank is not None and ladder.rank[product_id] >= offer.upgrade_to_rank:
        # The customer is already on that plan or a better one, so the "upgrade"
        # is a no-op or a downgrade. Nothing errors when this is skipped, which
        # is why it needs a name rather than a comment.
        refusals.append(ELIG_NOT_AN_UPGRADE)
    return refusals


def _policy_refusals(
    policy: ContactPolicy,
    offer: Offer,
    customer_id: str,
    cutoff: str,
    consent: dict[str, dict[str, bool]],
    history: ContactHistory,
    facts: CustomerFacts,
) -> list[str]:
    refusals = []

    rule = policy.get(CONSENT)
    if rule and rule.covers(offer.objective) and rule.value >= 1:
        if not consent.get(customer_id, {}).get(offer.channel, False):
            refusals.append(CONSENT)

    rule = policy.get(COOL_OFF)
    if rule and rule.covers(offer.objective):
        since = history.days_since_last(customer_id, cutoff)
        if since is not None and since < rule.value:
            refusals.append(COOL_OFF)

    rule = policy.get(FREQ_CAP)
    if rule and rule.covers(offer.objective):
        if history.count_within(customer_id, cutoff, 365) >= rule.value:
            refusals.append(FREQ_CAP)

    rule = policy.get(ARREARS)
    if rule and rule.covers(offer.objective):
        if facts.failed_invoices_6m.get(customer_id, 0) > rule.value:
            refusals.append(ARREARS)

    rule = policy.get(OPEN_ESC)
    if rule and rule.covers(offer.objective) and rule.value >= 1:
        if facts.unresolved_escalations.get(customer_id, 0) > 0:
            refusals.append(OPEN_ESC)

    return refusals


def evaluate(
    tables: Tables,
    offers: list[Offer],
    customer_ids: list[str],
    cutoff: str,
    policy: ContactPolicy,
    ladder: ProductLadder,
    consent: dict[str, dict[str, bool]],
    history: ContactHistory,
    facts: CustomerFacts,
) -> PermissionMatrix:
    """Build the full permission matrix for a wave.

    Eligibility first, then contact policy — an ordering chosen for readability
    of the refusal list, not for correctness: a pair is permitted only when
    every rule permits it, so the result is the same whichever order they run.
    """
    product_of = {r["customer_id"]: r["current_product_id"] for r in tables["customers"]}

    matrix = PermissionMatrix(customer_ids=list(customer_ids),
                              offer_ids=[o.offer_id for o in offers])
    for cid in customer_ids:
        product_id = product_of[cid]
        for offer in offers:
            refusals = _eligibility_refusals(offer, product_id, ladder)
            refusals += _policy_refusals(policy, offer, cid, cutoff, consent, history, facts)
            matrix.permissions[(cid, offer.offer_id)] = Permission(
                customer_id=cid, offer_id=offer.offer_id, blocked_by=tuple(refusals),
            )
    return matrix


# --- auditing what already happened -----------------------------------------


@dataclass(frozen=True)
class CampaignComplianceRow:
    """One campaign, judged against the policy that exists today."""

    campaign_id: str
    name: str
    channel: str
    objective: str
    offer_id: str
    exposed: int
    consented: int
    eligible: int
    compliant: int

    @property
    def consent_rate(self) -> float:
        return self.consented / self.exposed if self.exposed else 0.0

    @property
    def eligible_rate(self) -> float:
        return self.eligible / self.exposed if self.exposed else 0.0


def audit_campaigns(
    tables: Tables,
    offers: list[Offer],
    ladder: ProductLadder,
    consent: dict[str, dict[str, bool]],
) -> list[CampaignComplianceRow]:
    """How the campaigns that already ran would fare under the policy.

    Only the two rules that can be checked retrospectively are applied —
    **consent on the delivery channel** and **offer eligibility**. Cool-off and
    frequency caps are deliberately left out: judging a campaign by a contact
    history that includes contacts made *after* it is exactly the leak this
    track keeps flagging, and it would manufacture violations that could not
    have been known at the time.
    """
    product_of = {r["customer_id"]: r["current_product_id"] for r in tables["customers"]}
    offer_by_id = {o.offer_id: o for o in offers}

    audience: dict[str, list[str]] = {}
    for row in tables["campaign_exposures"]:
        if _int(row["exposed"]) == 1:
            audience.setdefault(row["campaign_id"], []).append(row["customer_id"])

    rows = []
    for campaign in tables["campaigns"]:
        exposed = audience.get(campaign["campaign_id"], [])
        if not exposed:
            continue
        offer = offer_by_id[campaign["offer_id"]]
        channel = campaign["channel"]

        consented = [c for c in exposed if consent.get(c, {}).get(channel, False)]
        eligible = [c for c in exposed if not _eligibility_refusals(offer, product_of[c], ladder)]
        compliant = [c for c in consented if not _eligibility_refusals(offer, product_of[c], ladder)]

        rows.append(CampaignComplianceRow(
            campaign_id=campaign["campaign_id"],
            name=campaign["name"],
            channel=channel,
            objective=campaign["objective"],
            offer_id=offer.offer_id,
            exposed=len(exposed),
            consented=len(consented),
            eligible=len(eligible),
            compliant=len(compliant),
        ))
    return rows


def consent_by_channel(tables: Tables, customer_ids: list[str]) -> dict[str, float]:
    """Opt-in rate per channel, over the wave population."""
    wanted = set(customer_ids)
    totals: dict[str, list[int]] = {}
    for row in tables["consent"]:
        if row["customer_id"] in wanted:
            totals.setdefault(row["channel"], []).append(_int(row["consent"]))
    return {channel: sum(v) / len(v) for channel, v in sorted(totals.items())}


def unreachable_customers(consent: dict[str, dict[str, bool]], customer_ids: list[str]) -> list[str]:
    """Customers who have opted out of every channel."""
    return [c for c in customer_ids if not any(consent.get(c, {}).values())]


def last_contacts(history: ContactHistory, customer_ids: list[str], cutoff: str) -> list[Contact]:
    """The most recent contact for each customer, for the cool-off analysis."""
    latest = []
    for cid in customer_ids:
        previous = [c for c in history.for_customer(cid) if c.when <= cutoff]
        if previous:
            latest.append(max(previous, key=lambda c: c.when))
    return latest
