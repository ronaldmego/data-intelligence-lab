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


def test_consent_covers_every_customer_and_channel(tables):
    _, t = tables
    n_customers = len(t["customers"])
    assert len(t["consent"]) == n_customers * 4
    for r in t["consent"]:
        assert r["consent"] in (0, 1)
        assert r["channel"] in ("email", "sms", "push", "call")


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
