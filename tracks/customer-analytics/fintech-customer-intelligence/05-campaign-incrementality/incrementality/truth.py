"""The answer key — the one thing a synthetic world can offer that no real one can.

The data model records, for every customer, what would have happened if the
campaign had never run (``churn_potential_outcomes``). Both outcomes come from
the *same* uniform draw, so subtracting them gives the individual causal effect
rather than a difference between two noisy worlds.

That makes a question answerable that is otherwise permanently closed: **was the
estimate right?** Not "is it plausible", not "is it significant" — right. And it
splits an observed difference into the two things that produce it:

    observed ITT  =  effect the campaign actually delivered
                  +  imbalance the coin flip happened to hand us

Only the first is the campaign. The second is luck, it has no reason to be small
when the arms are small, and it is invisible in any real readout — where the two
terms arrive fused into a single number that gets presented as the first one.

**This module is quarantined on purpose.** It is imported by the reporting layer
to *check* the estimators, never by the estimators themselves. An estimate that
consults the answer key has stopped being an estimate, and a test in the suite
asserts that the estimation path never touches this table.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Truth:
    """Ground truth for one cutoff: the effect on every customer."""

    cutoff: str
    effect: dict[str, int]        # customer_id -> Y(exposed) - Y(no campaign), always <= 0
    untreated: dict[str, int]     # customer_id -> Y(no campaign)
    treated: set[str]             # customers the generator actually treated

    @property
    def n_affected(self) -> int:
        """Customers whose outcome the campaign actually changed.

        Far smaller than the number treated: an offer only matters to a customer
        whose churn draw sat between the treated and untreated probabilities.
        Most treated customers would have stayed either way, and this is why an
        effect of a few points takes thousands of people to see.
        """
        return sum(1 for v in self.effect.values() if v != 0)

    def average_over(self, ids: list[str]) -> float:
        rows = [self.effect[c] for c in ids if c in self.effect]
        return sum(rows) / len(rows) if rows else 0.0

    def untreated_rate(self, ids: list[str]) -> float:
        rows = [self.untreated[c] for c in ids if c in self.untreated]
        return sum(rows) / len(rows) if rows else 0.0

    @property
    def cace(self) -> float:
        """The true effect among customers who took an offer.

        The quantity the Wald estimator is aiming at, known exactly.
        """
        return self.average_over(sorted(self.treated))


@dataclass(frozen=True)
class Decomposition:
    """What an observed difference was really made of."""

    campaign_id: str
    observed: float
    delivered: float
    imbalance: float

    @property
    def imbalance_dominates(self) -> bool:
        """Did luck contribute more than the campaign did?"""
        return abs(self.imbalance) > abs(self.delivered)

    @property
    def sign_flipped(self) -> bool:
        """Did the imbalance push the headline to the wrong side of zero?"""
        return self.delivered != 0 and (self.observed > 0) != (self.delivered > 0)


def load_truth(tables, cutoff: str, treated: set[str]) -> Truth:
    """Read the potential outcomes for one observation cutoff."""
    observed = {r["customer_id"]: int(r["churned_next_90d"])
                for r in tables["churn_labels"] if r["observation_cutoff"] == cutoff}
    if not observed:
        observed = {r["customer_id"]: int(r["churned_next_90d"])
                    for r in tables["churn_labels_prior"] if r["observation_cutoff"] == cutoff}

    untreated = {r["customer_id"]: int(r["churned_next_90d_if_no_campaign"])
                 for r in tables["churn_potential_outcomes"] if r["observation_cutoff"] == cutoff}

    effect = {c: observed[c] - untreated[c] for c in observed if c in untreated}
    return Truth(cutoff=cutoff, effect=effect, untreated=untreated, treated=treated)


def decompose(audience, truth: Truth) -> Decomposition:
    """Split the observed ITT into the campaign's work and the flip's luck.

    ``observed = delivered + imbalance`` is an identity, not an approximation:
    the exposed arm's realised outcome is its untreated outcome plus its effect,
    so the difference between arms is the difference in effects plus the
    difference in untreated outcomes.
    """
    delivered = truth.average_over(audience.exposed) - truth.average_over(audience.control)
    imbalance = truth.untreated_rate(audience.exposed) - truth.untreated_rate(audience.control)
    observed = (
        sum(audience.outcomes(audience.exposed)) / len(audience.exposed)
        - sum(audience.outcomes(audience.control)) / len(audience.control)
    )
    return Decomposition(
        campaign_id=audience.campaign.campaign_id,
        observed=observed,
        delivered=delivered,
        imbalance=imbalance,
    )
