"""Contract tests for the synthetic telco data model.

These run on the standard library alone (no numpy/pandas), so CI's ``uvx pytest``
executes them without installing project dependencies. They assert three things:

1. **Schema & referential integrity** — keys are unique, foreign keys resolve,
   required fields are populated.
2. **No leakage** — every fact is dated on-or-before the churn observation
   cutoff, so a churn model built from these tables cannot see the future.
3. **Causal signal is present** — churn actually rises with the drivers, and a
   held-out control exists for the retention campaigns. A dataset that passed
   the schema checks but had a flat, signal-free label would make the downstream
   cases meaningless, so it is a test failure here.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# Make the data-model package importable regardless of pytest's rootdir.
_DM = Path(__file__).resolve().parent.parent / "data-model"
sys.path.insert(0, str(_DM))

import pytest  # noqa: E402
from telco import Config, generate  # noqa: E402


@pytest.fixture(scope="module")
def tables():
    # Small but non-trivial: enough customers for base rates to be stable.
    cfg = Config(seed=123, n_customers=800, n_months=18)
    return cfg, generate(cfg)


def test_all_expected_tables_present(tables):
    cfg, t = tables
    assert set(t.keys()) == set(cfg.output_tables())
    for name in cfg.output_tables():
        assert t[name], f"table {name} is empty"


def test_primary_keys_unique(tables):
    _, t = tables
    pks = {
        "plans": "plan_id",
        "offers": "offer_id",
        "campaigns": "campaign_id",
        "customers": "customer_id",
        "subscriptions": "subscription_id",
        "invoice": None,
        "campaign_exposures": "exposure_id",
        "churn_labels": "customer_id",
    }
    for table, key in pks.items():
        if key is None:
            continue
        ids = [r[key] for r in t[table]]
        assert len(ids) == len(set(ids)), f"{table}.{key} has duplicates"
    inv = [r["invoice_id"] for r in t["billing"]]
    assert len(inv) == len(set(inv)), "billing.invoice_id has duplicates"


def test_foreign_keys_resolve(tables):
    _, t = tables
    customer_ids = {r["customer_id"] for r in t["customers"]}
    plan_ids = {r["plan_id"] for r in t["plans"]}
    offer_ids = {r["offer_id"] for r in t["offers"]}

    for r in t["subscriptions"]:
        assert r["customer_id"] in customer_ids
        assert r["plan_id"] in plan_ids
    for r in t["campaigns"]:
        assert r["offer_id"] in offer_ids
    # Every fact table's customer_id must be a known customer.
    for name in ("usage_monthly", "billing", "digital_monthly",
                 "support_interactions", "consent", "campaign_exposures", "churn_labels"):
        for r in t[name]:
            assert r["customer_id"] in customer_ids, f"{name} references unknown customer"


def test_every_customer_has_churn_label(tables):
    _, t = tables
    labeled = {r["customer_id"] for r in t["churn_labels"]}
    all_customers = {r["customer_id"] for r in t["customers"]}
    assert labeled == all_customers


def test_no_leakage_facts_are_pre_cutoff(tables):
    """No fact may be dated after the observation cutoff — otherwise a churn
    model would be trained on the future it is meant to predict."""
    _, t = tables
    cutoff = date.fromisoformat(t["churn_labels"][0]["observation_cutoff"])
    for name in ("usage_monthly", "billing", "digital_monthly", "support_interactions"):
        for r in t[name]:
            period = date.fromisoformat(r["period_month"])
            assert period <= cutoff, f"{name} has a fact dated after the cutoff"
    # Churn events, by contrast, must all be in the future (after the cutoff).
    for r in t["churn_labels"]:
        if r["churned_next_90d"] == 1:
            assert date.fromisoformat(r["churn_date"]) > cutoff


def test_prior_cutoff_is_earlier_and_its_outcome_window_is_disjoint(tables):
    """The two cutoffs must be far enough apart that the 90-day outcome windows
    do not overlap — otherwise training on one and scoring the other is not
    out-of-time validation, it is the same period twice."""
    _, t = tables
    prior_cutoff = date.fromisoformat(t["churn_labels_prior"][0]["observation_cutoff"])
    final_cutoff = date.fromisoformat(t["churn_labels"][0]["observation_cutoff"])
    assert prior_cutoff < final_cutoff

    prior_dates = [date.fromisoformat(r["churn_date"])
                   for r in t["churn_labels_prior"] if r["churned_next_90d"] == 1]
    assert prior_dates, "prior cutoff produced no churn events at all"
    assert all(d > prior_cutoff for d in prior_dates), "a prior churn event predates its own cutoff"
    assert max(prior_dates) < final_cutoff, "the two outcome windows overlap"


def test_prior_labels_only_cover_customers_alive_at_that_cutoff(tables):
    """A customer who had not signed up yet cannot be scored. They must be
    absent from the earlier label — not present with a fabricated zero."""
    cfg, t = tables
    prior_cutoff = date.fromisoformat(t["churn_labels_prior"][0]["observation_cutoff"])
    signup = {r["customer_id"]: date.fromisoformat(r["signup_date"]) for r in t["customers"]}
    labelled = {r["customer_id"] for r in t["churn_labels_prior"]}

    assert labelled, "prior label table is empty"
    assert labelled <= set(signup), "prior label references an unknown customer"
    for cid in labelled:
        assert signup[cid] <= prior_cutoff, f"{cid} is labelled before it signed up"
    for cid, when in signup.items():
        if when > prior_cutoff:
            assert cid not in labelled, f"{cid} signed up after the cutoff yet has a label"


def test_prior_label_is_a_fresh_draw_not_a_copy(tables):
    """The earlier label is re-derived from the state of the world at that
    cutoff, with its own noise. If it were a copy of the final label, an
    out-of-time backtest built on it would be circular and flatter itself."""
    _, t = tables
    final = {r["customer_id"]: r["churned_next_90d"] for r in t["churn_labels"]}
    prior = {r["customer_id"]: r["churned_next_90d"] for r in t["churn_labels_prior"]}
    shared = set(prior) & set(final)
    agreement = sum(1 for c in shared if prior[c] == final[c]) / len(shared)
    # Correlated (same customers, same latent traits) but far from identical.
    assert 0.60 < agreement < 0.98, f"prior/final label agreement {agreement:.1%} looks like a copy"

    rate = sum(prior.values()) / len(prior)
    assert 0.05 < rate < 0.25, f"implausible prior churn base rate {rate:.1%}"


def test_consent_covers_every_customer_and_channel(tables):
    _, t = tables
    n_customers = len(t["customers"])
    assert len(t["consent"]) == n_customers * 4
    for r in t["consent"]:
        assert r["consent"] in (0, 1)
        assert r["channel"] in ("email", "sms", "push", "call")


def test_contact_policy_is_declared_as_data(tables):
    """The contact policy is a table, not a constant in whichever script scores.

    Each row has to be machine-readable — an identifier, a scope, a parameter
    and a unit — or it is documentation pretending to be governance.
    """
    _, t = tables
    rows = t["contact_policy"]
    assert rows

    ids = [r["policy_id"] for r in rows]
    assert len(ids) == len(set(ids)), "contact_policy.policy_id has duplicates"

    objectives = {r["objective"] for r in t["campaigns"]} | {"all"}
    for row in rows:
        assert row["rule"] and row["rationale"], f"{row['policy_id']} is not self-describing"
        assert row["unit"] in ("flag", "days", "contacts", "invoices", "offers")
        assert float(row["value"]) >= 0
        scope = {part.strip() for part in row["applies_to"].split(",")}
        assert scope <= objectives, f"{row['policy_id']} scoped to an unknown objective"


def test_upgrade_offers_declare_the_plan_they_upgrade_to(tables):
    """"Upgrade to M" is a string until something says which rank M is.

    Every consumer that re-derives it from the offer name derives it slightly
    differently, and the customer already on L gets offered a downgrade.
    """
    _, t = tables
    ranks = {}
    for row in t["plans"]:
        ranks.setdefault(row["family"], []).append(int(row["tier"]))
    depth = max(len(tiers) for tiers in ranks.values())

    upgrades = [r for r in t["offers"] if r["type"] == "upgrade"]
    assert upgrades
    for row in t["offers"]:
        target = row["upgrade_to_rank"]
        if row["type"] == "upgrade":
            assert target != "", f"{row['offer_id']} is an upgrade with no target rank"
            assert 1 < int(target) <= depth
        else:
            assert target == "", f"{row['offer_id']} is not an upgrade but declares a target"


def test_churn_base_rate_is_plausible(tables):
    _, t = tables
    churn = [r["churned_next_90d"] for r in t["churn_labels"]]
    rate = sum(churn) / len(churn)
    # Realistic telco 90-day window; wide bounds so it is robust to the seed.
    assert 0.05 < rate < 0.25, f"implausible churn base rate {rate:.1%}"


def test_causal_signal_unresolved_support_raises_churn(tables):
    """The strongest designed driver must show up: customers with an unresolved
    escalation churn materially more than those without."""
    _, t = tables
    churn = {r["customer_id"]: r["churned_next_90d"] for r in t["churn_labels"]}
    unresolved = defaultdict(int)
    for r in t["support_interactions"]:
        if r["escalated"] == 1 and r["resolved"] == 0:
            unresolved[r["customer_id"]] += 1
    with_esc = [churn[c] for c in churn if unresolved[c] > 0]
    without = [churn[c] for c in churn if unresolved[c] == 0]
    assert with_esc and without
    rate_with = sum(with_esc) / len(with_esc)
    rate_without = sum(without) / len(without)
    assert rate_with > rate_without + 0.05, (
        f"unresolved-support signal too weak: {rate_with:.1%} vs {rate_without:.1%}"
    )


def test_retention_campaigns_have_a_held_out_control(tables):
    """Incrementality is only recoverable if a control group exists — assert
    the retention campaigns actually withhold exposure from some targets."""
    _, t = tables
    exposed = control = 0
    for r in t["campaign_exposures"]:
        if r["campaign_id"].startswith("CMP_RET"):
            if r["exposed"] == 1:
                exposed += 1
            else:
                control += 1
    assert exposed > 0 and control > 0, "retention campaign lacks exposed/control split"


def test_generation_is_deterministic(tables):
    cfg, t = tables
    again = generate(cfg)
    # Same seed -> identical churn labels and identical row counts everywhere.
    assert {k: len(v) for k, v in t.items()} == {k: len(v) for k, v in again.items()}
    assert [r["churned_next_90d"] for r in t["churn_labels"]] == \
           [r["churned_next_90d"] for r in again["churn_labels"]]
