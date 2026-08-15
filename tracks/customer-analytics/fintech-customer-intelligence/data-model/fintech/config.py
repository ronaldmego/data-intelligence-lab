"""Generation parameters for the synthetic fintech data model.

Everything the generator needs to be *reproducible* lives here: a single seed,
the size of the population, the length of history, and the base rates that shape
the causal structure. Change the seed and you get a different-but-consistent
world; keep it and the output is byte-for-byte identical on any machine.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """All knobs for one generation run.

    The defaults produce a mid-sized, analytically interesting dataset
    (~5k customers over 24 months). Tests override ``n_customers`` and
    ``n_months`` down to keep CI fast.
    """

    seed: int = 42
    n_customers: int = 5000
    n_months: int = 24  # months of history, all <= the churn observation cutoff

    # A *second*, earlier observation cutoff, this many months before the final
    # one. Same 90-day label, observed earlier — which is what makes honest
    # out-of-time validation possible: train on the world as it looked at the
    # prior cutoff, then score the final cutoff, exactly as a model deployed in
    # production is judged. With a single cutoff, "temporal validation" can only
    # ever be asserted, never demonstrated. Must exceed the ~3-month label
    # window so the two outcome periods do not overlap.
    prior_cutoff_offset: int = 6

    # Calendar anchor for month 0. Kept fixed so dates are reproducible without
    # depending on the machine clock.
    start_year: int = 2024
    start_month_of_year: int = 1  # January

    # --- Base rates that drive the causal structure -----------------------
    # These are the levers the downstream cases are meant to *recover*, so they
    # live in one place and are documented in data-model/README.md.

    # Fraction of customers on prepaid (vs credit) products.
    prepaid_share: float = 0.55

    # Baseline probability a billed invoice is paid late / fails, before the
    # per-customer price-sensitivity adjustment.
    base_late_rate: float = 0.08
    base_fail_rate: float = 0.03

    # Support: expected tickets per active year, and the chance a ticket ends
    # escalated-and-unresolved (the strongest churn driver).
    tickets_per_year: float = 1.4
    unresolved_escalation_rate: float = 0.12

    # Churn: the intercept sets the overall base rate; the weights set how much
    # each observed driver moves the log-odds. Downstream churn models should be
    # able to recover the *sign and rough magnitude* of these — not the exact
    # value, because latent satisfaction and noise are deliberately unobserved.
    churn_intercept: float = -3.6  # tuned to a ~13% 90-day base rate
    w_usage_decline: float = 1.6
    w_payment_problems: float = 1.1
    w_unresolved_support: float = 1.4
    w_low_engagement: float = 0.9
    w_early_life: float = 0.8
    w_plan_misfit: float = 0.7
    w_retention_response: float = 1.5  # subtracted: a real retention uplift
    churn_noise_sd: float = 0.6

    # Campaigns: size of the true retention uplift (reduction in churn log-odds
    # for a genuine responder) and the selection bias that makes the naive
    # estimate wrong — retention campaigns preferentially target high-risk
    # customers, so a naive "responders churn less" read is confounded.
    retention_selection_bias: float = 1.8  # how strongly targeting favours risk
    control_share: float = 0.30  # held-out control per campaign (for uplift)

    def output_tables(self) -> tuple[str, ...]:
        """Canonical table order — also the order they are written and tested."""
        return (
            "products",
            "offers",
            "campaigns",
            "contact_policy",
            "customers",
            "subscriptions",
            "activity_monthly",
            "billing",
            "digital_monthly",
            "support_interactions",
            "consent",
            "campaign_exposures",
            "churn_labels",
            "churn_labels_prior",
            "churn_potential_outcomes",
        )
