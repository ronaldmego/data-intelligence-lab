"""What the governance layer would have done to the campaigns that already ran.

The forward-looking list in this case is scored in expectation: nobody can
observe whether a customer would have accepted an offer they were never sent.
The campaigns in the data model, though, *did* run — and the data model records
what every customer would have done had they not — so one question can be
answered exactly rather than estimated:

> If those campaigns had only contacted the customers they were allowed to
> contact, how many people would still have been saved?

That is a stronger claim than anything the forward list can make, and it is the
one that decides whether a governance layer is a rounding error or a redesign.

**The answer key is quarantined, and this case does not open it.** Case 05 owns
the only module in the track that reads ``churn_potential_outcomes``; this
module imports that one. So the fence is a property of the track, not a promise
repeated per case: exactly one file touches the table, and the test suite
corrupts it and asserts that no estimate moves.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_INCREMENTALITY = Path(__file__).resolve().parents[2] / "05-campaign-incrementality"
if str(_INCREMENTALITY) not in sys.path:
    sys.path.insert(0, str(_INCREMENTALITY))

from incrementality.estimators import difference_in_proportions  # noqa: E402
from incrementality.truth import Truth, load_truth  # noqa: E402

from .data import Offer, PlanLadder, Tables, _int  # noqa: E402
from .policy import _eligibility_refusals  # noqa: E402


@dataclass(frozen=True)
class ReachDecomposition:
    """Why a compliant campaign saves fewer people, split exactly in two.

        saves(compliant) - saves(full)  =  volume  +  composition

    ``volume`` is what is lost by contacting fewer people at the same per-person
    rate; ``composition`` is what is lost (or gained) because the people who
    remain respond differently. It is an identity, not an approximation, and it
    matters because the two have different remedies: volume is a reach problem
    solved on the channel, composition is a targeting problem solved on the
    model.
    """

    campaign_id: str
    exposed: int
    permitted: int
    saves_full: int
    saves_permitted: int
    rate_full: float
    rate_permitted: float
    volume: float
    composition: float
    rate_difference_se: float

    @property
    def total(self) -> float:
        return self.volume + self.composition

    @property
    def saves_retained(self) -> float:
        return self.saves_permitted / self.saves_full if self.saves_full else 0.0

    @property
    def reach_retained(self) -> float:
        return self.permitted / self.exposed if self.exposed else 0.0

    @property
    def composition_is_resolvable(self) -> bool:
        """Is the per-person difference bigger than the noise on it?

        Two identically designed campaigns can disagree about the sign of this
        term purely through which individual draws happened to flip. Saying so
        is the difference between a finding and a story.
        """
        return abs(self.rate_permitted - self.rate_full) > 1.96 * self.rate_difference_se


@dataclass(frozen=True)
class CampaignAudit:
    """One campaign, re-read under the policy, against ground truth."""

    campaign_id: str
    name: str
    channel: str
    exposed: list[str]
    control: list[str]
    permitted_exposed: list[str]
    permitted_control: list[str]
    true_effect_full: float
    true_effect_permitted: float
    reach: ReachDecomposition


def _saves(truth: Truth, ids: list[str]) -> int:
    """Customers in this group whose outcome the campaign actually changed."""
    return sum(1 for c in ids if truth.effect.get(c, 0) != 0)


def _true_effect(truth: Truth, exposed: list[str], control: list[str]) -> float:
    """Average causal effect delivered to the exposed, net of the control's.

    Both arms carry an effect only where a customer took an offer; the control
    arm of one campaign can still have been treated by the other, which is why
    it is subtracted rather than assumed to be zero.
    """
    if not exposed or not control:
        return 0.0
    return truth.average_over(exposed) - truth.average_over(control)


def audit_retention_campaigns(
    tables: Tables,
    offers: list[Offer],
    ladder: PlanLadder,
    consent: dict[str, dict[str, bool]],
) -> list[CampaignAudit]:
    """Re-read each retention campaign as if consent and eligibility had held.

    Only those two rules are applied. Cool-off and frequency caps depend on a
    contact history that, at the time each campaign ran, did not yet include the
    later campaigns — judging a past campaign by a future it could not see would
    manufacture violations and is the same look-ahead this track keeps flagging.
    """
    plan_of = {r["customer_id"]: r["current_plan_id"] for r in tables["customers"]}
    offer_by_id = {o.offer_id: o for o in offers}
    cutoff = tables["churn_labels"][0]["observation_cutoff"]

    audience: dict[str, dict[str, list[str]]] = {}
    for row in tables["campaign_exposures"]:
        arm = "exposed" if _int(row["exposed"]) == 1 else "control"
        audience.setdefault(row["campaign_id"], {"exposed": [], "control": []})[arm].append(
            row["customer_id"]
        )

    responders = {
        r["customer_id"] for r in tables["campaign_exposures"] if _int(r["responded"]) == 1
    }
    truth = load_truth(tables, cutoff, treated=responders)

    audits = []
    for campaign in tables["campaigns"]:
        if campaign["objective"] != "retention":
            continue
        arms = audience.get(campaign["campaign_id"])
        if not arms or not arms["exposed"] or not arms["control"]:
            continue

        offer = offer_by_id[campaign["offer_id"]]
        channel = campaign["channel"]

        def permitted(ids: list[str], offer: Offer = offer, channel: str = channel) -> list[str]:
            return [
                c for c in ids
                if consent.get(c, {}).get(channel, False)
                and not _eligibility_refusals(offer, plan_of[c], ladder)
            ]

        exposed, control = arms["exposed"], arms["control"]
        permitted_exposed, permitted_control = permitted(exposed), permitted(control)

        saves_full, saves_permitted = _saves(truth, exposed), _saves(truth, permitted_exposed)
        rate_full = saves_full / len(exposed)
        rate_permitted = saves_permitted / len(permitted_exposed) if permitted_exposed else 0.0

        # An exact split of the change in saves. Written with the counterfactual
        # "same rate, fewer people" in the middle, so the two terms sum to the
        # total by construction rather than by luck of rounding.
        volume = (len(permitted_exposed) - len(exposed)) * rate_full
        composition = len(permitted_exposed) * (rate_permitted - rate_full)

        flags_full = [1 if truth.effect.get(c, 0) != 0 else 0 for c in exposed]
        flags_permitted = [1 if truth.effect.get(c, 0) != 0 else 0 for c in permitted_exposed]
        se = difference_in_proportions("rate", flags_permitted, flags_full).standard_error \
            if permitted_exposed else float("inf")

        audits.append(CampaignAudit(
            campaign_id=campaign["campaign_id"],
            name=campaign["name"],
            channel=channel,
            exposed=exposed,
            control=control,
            permitted_exposed=permitted_exposed,
            permitted_control=permitted_control,
            true_effect_full=_true_effect(truth, exposed, control),
            true_effect_permitted=_true_effect(truth, permitted_exposed, permitted_control),
            reach=ReachDecomposition(
                campaign_id=campaign["campaign_id"],
                exposed=len(exposed),
                permitted=len(permitted_exposed),
                saves_full=saves_full,
                saves_permitted=saves_permitted,
                rate_full=rate_full,
                rate_permitted=rate_permitted,
                volume=volume,
                composition=composition,
                rate_difference_se=se,
            ),
        ))
    return audits


def channel_reach(
    tables: Tables,
    consent: dict[str, dict[str, bool]],
    customer_ids: list[str],
    channels: tuple[str, ...] = ("push", "email", "sms", "call"),
) -> dict[str, float]:
    """Share of a population reachable on each channel.

    The Q1 retention campaign's problem is not that customers refused to hear
    from the company — it is that it went out by the channel with the lowest
    opt-in. Delivering the same offer on a different consented channel needs no
    new assumption about effectiveness to change *reach*, which is the term the
    decomposition above shows dominates.
    """
    del tables
    reach = {}
    for channel in channels:
        opted_in = sum(1 for c in customer_ids if consent.get(c, {}).get(channel, False))
        reach[channel] = opted_in / len(customer_ids) if customer_ids else 0.0
    return reach
