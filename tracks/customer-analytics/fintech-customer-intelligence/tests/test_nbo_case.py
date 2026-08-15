"""Contract tests for case 03 — governed next-best-offer.

Standard library only, so CI's ``uvx pytest`` runs them with nothing installed.

The tests worth having here are the ones that would still pass if the case were
quietly broken in the way it exists to prevent:

* the answer key reaches the retrospective audit and **nothing else** — the same
  fence case 05 built, now that a second case consumes it;
* the governed list contains no pair the policy refuses, whatever the ranking
  says;
* the rules come from the data model, so changing a row changes the outcome —
  a policy that is really a hardcoded constant would pass every other test;
* the suppression rules read nothing dated after the decision, because an
  exclusion list is a model too and leaks the same way;
* the reach decomposition is an identity, not an approximation.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CASE = Path(__file__).resolve().parent.parent / "03-next-best-offer"
_CHURN = Path(__file__).resolve().parent.parent / "02-churn-prediction"
_INCREMENTALITY = Path(__file__).resolve().parent.parent / "05-campaign-incrementality"
_DATA_MODEL = Path(__file__).resolve().parent.parent / "data-model"
for path in (str(_CASE), str(_CHURN), str(_INCREMENTALITY), str(_DATA_MODEL)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest  # noqa: E402
from nbo import load_consent, load_offers, load_tables, run_case  # noqa: E402
from nbo.data import ContactHistory, ProductLadder, month_calendar, priced_offers  # noqa: E402
from nbo.policy import (  # noqa: E402
    CONSENT,
    COOL_OFF,
    ELIG_NOT_AN_UPGRADE,
    ContactPolicy,
    CustomerFacts,
    evaluate,
)
from nbo.value import _campaign_training_rows  # noqa: E402
from fintech import Config  # noqa: E402

SEED = Config(seed=123, n_customers=800, n_months=18)


@pytest.fixture(scope="module")
def tables():
    return load_tables(SEED)


@pytest.fixture(scope="module")
def result(tables):
    return run_case(tables, sensitivity_windows=(0, 270))


# --- the fence around the answer key ---------------------------------------


def test_the_answer_key_reaches_the_audit_and_nothing_else(tables):
    """Corrupt the counterfactual; every *decision* must be unmoved.

    Case 05 built this fence for one case. A second consumer is exactly when a
    fence stops being a convention and starts needing a test of its own: the
    plan, the offer values and the rule costs must not shift by a single unit,
    while the retrospective audit — whose whole job is to read the answer key —
    must shift, or the test is comparing two identical runs and proves nothing.
    """
    honest = run_case(tables, sensitivity_windows=(270,))

    poisoned = dict(tables)
    poisoned["churn_potential_outcomes"] = [
        {**row, "churned_next_90d_if_no_campaign": 1 - int(row["churned_next_90d_if_no_campaign"])}
        for row in tables["churn_potential_outcomes"]
    ]
    cheated = run_case(poisoned, sensitivity_windows=(270,))

    for plan_a, plan_b in zip(cheated.plans, honest.plans, strict=True):
        assert plan_a.expected_value == plan_b.expected_value
        assert [a.customer_id for a in plan_a.assignments] == [b.customer_id for b in plan_b.assignments]
        assert [a.offer_id for a in plan_a.assignments] == [b.offer_id for b in plan_b.assignments]
    assert [c.customers_removed for c in cheated.rule_costs] == \
           [c.customers_removed for c in honest.rule_costs]
    assert [v.expected_value for v in cheated.values.values()] == \
           [v.expected_value for v in honest.values.values()]
    assert [p.plan_expected_value for p in cheated.sensitivity] == \
           [p.plan_expected_value for p in honest.sensitivity]

    # ...and the check is live: the truth-derived section genuinely moved.
    assert [a.reach.saves_full for a in cheated.audits] != [a.reach.saves_full for a in honest.audits]


# --- the permission layer ---------------------------------------------------


def test_the_governed_list_contains_nothing_the_policy_refuses(result):
    for assignment in result.comparison.governed.assignments:
        assert result.matrix.allowed(assignment.customer_id, assignment.offer_id)


def test_suppressing_after_ranking_underfills_and_stays_legal(result):
    """The wrong order is still *compliant* — that is what makes it survive."""
    suppressed = result.comparison.suppressed
    for assignment in suppressed.assignments:
        assert result.matrix.allowed(assignment.customer_id, assignment.offer_id)
    assert len(suppressed) <= suppressed.capacity
    assert suppressed.suppressed_after_ranking == suppressed.capacity - len(suppressed)


def test_filtering_first_is_never_worse_than_filtering_last(result):
    """Both lists obey the same rules; only one of them fills the capacity."""
    assert result.comparison.governed.expected_value >= result.comparison.suppressed.expected_value
    assert len(result.comparison.governed) >= len(result.comparison.suppressed)


def test_one_offer_per_customer(result):
    for plan in result.plans:
        customers = [a.customer_id for a in plan.assignments]
        assert len(customers) == len(set(customers))


def test_no_offer_with_a_negative_expected_value_is_ever_sent(result):
    for plan in result.plans:
        assert all(a.expected_value > 0 for a in plan.assignments)


def test_consent_blocks_exactly_the_customers_who_did_not_opt_in(tables, result):
    consent = load_consent(tables)
    offer = result.priced[0]
    for cid in result.wave.customer_ids[:200]:
        blocked = CONSENT in result.matrix.permissions[(cid, offer.offer_id)].blocked_by
        assert blocked == (not consent[cid][offer.channel])


def test_an_upgrade_offer_is_refused_to_customers_already_above_it(tables, result):
    """The rule that a quarter of a real base fails, expressed as an assertion."""
    ladder = ProductLadder.build(tables)
    product_of = {r["customer_id"]: r["current_product_id"] for r in tables["customers"]}
    upgrades = [o for o in result.catalogue if o.upgrade_to_rank is not None]
    assert upgrades, "the catalogue should contain at least one upgrade offer"

    for offer in upgrades:
        for cid in result.wave.customer_ids[:200]:
            refused = ELIG_NOT_AN_UPGRADE in result.matrix.permissions[(cid, offer.offer_id)].blocked_by
            assert refused == (ladder.rank[product_of[cid]] >= offer.upgrade_to_rank)


# --- the policy really is data ----------------------------------------------


def test_changing_a_policy_row_changes_the_decision(tables, result):
    """A rule read from the data model, not a constant with a docstring.

    If the contact policy were hardcoded, every other test in this file would
    still pass. This is the one that would not.
    """
    ladder = ProductLadder.build(tables)
    consent = load_consent(tables)
    history = ContactHistory.build(tables)
    facts = CustomerFacts.build(tables, result.wave.cutoff, result.wave.customer_ids)

    strict = ContactPolicy.load(tables)
    relaxed = strict.replace(COOL_OFF, 0.0)

    def reachable(policy):
        matrix = evaluate(tables, result.catalogue, result.wave.customer_ids,
                          result.wave.cutoff, policy, ladder, consent, history, facts)
        return len(matrix.reachable_customers())

    assert reachable(relaxed) > reachable(strict)


def test_every_declared_rule_is_implemented(tables, result):
    """A rule in the table that no code reads is worse than no rule at all."""
    declared = {r["rule"] for r in tables["contact_policy"]}
    fired = set(result.matrix.rules_fired())
    # POL_ONE_OFFER constrains the assignment, not the pair, so it is enforced
    # in allocation and never appears as a refusal.
    unimplemented = declared - fired - {"max_offers_per_wave"}
    assert not unimplemented, f"declared but never enforced: {sorted(unimplemented)}"


# --- suppression reads nothing from after the decision ----------------------


def test_the_exclusion_facts_read_nothing_dated_after_the_cutoff(tables, result):
    """Poison the facts with post-cutoff rows; the exclusions must not move.

    An exclusion list is a model. Case 02 makes this guarantee for features;
    nobody makes it for suppression rules, which is why they leak.
    """
    clean = CustomerFacts.build(tables, result.wave.cutoff, result.wave.customer_ids)

    poisoned = dict(tables)
    for name in ("billing", "support_interactions"):
        extra = [{**row, "period_month": "2099-01-01"} for row in tables[name][:200]]
        poisoned[name] = [*tables[name], *extra]
    after = CustomerFacts.build(poisoned, result.wave.cutoff, result.wave.customer_ids)

    assert after.failed_invoices_6m == clean.failed_invoices_6m
    assert after.unresolved_escalations == clean.unresolved_escalations


def test_contact_history_counts_only_customers_who_were_actually_contacted(tables):
    """A held-back control was selected, not contacted — no frequency burden.

    Counting them would suppress, in the next wave, precisely the customers a
    previous experiment went out of its way to leave alone.
    """
    history = ContactHistory.build(tables)
    contacted = {c.customer_id for contacts in history.by_customer.values() for c in contacts}
    control_only = {
        r["customer_id"] for r in tables["campaign_exposures"] if int(r["exposed"]) == 0
    } - {r["customer_id"] for r in tables["campaign_exposures"] if int(r["exposed"]) == 1}
    assert control_only, "expected some customers who were only ever held back"
    assert not (control_only & contacted)


def test_acceptance_training_features_predate_the_campaign_they_model(tables):
    """Build features at the campaign's own month and the model is handed the
    response it is predicting, through ``retention_offer_taken``. The training
    cutoff must be strictly earlier."""
    calendar = month_calendar(tables)
    consent = load_consent(tables)
    for objective in ("retention", "upsell", "crosssell"):
        # The invariant is per campaign, not across them: an objective can have
        # several campaigns, and the later one's cutoff is naturally after the
        # earlier one's month.
        expected = set()
        for row in tables["campaigns"]:
            if row["objective"] != objective:
                continue
            month = min(int(row["month_index"]), len(calendar) - 1)
            assert calendar[max(0, month - 1)] < calendar[month]
            expected.add(calendar[max(0, month - 1)])

        cutoffs = {cutoff for _, cutoff, _ in _campaign_training_rows(tables, objective, False, consent)}
        assert cutoffs
        assert cutoffs <= expected


# --- the catalogue ----------------------------------------------------------


def test_offers_that_never_ran_are_kept_out_of_the_plan(result):
    assert result.unpriced, "expected at least one offer with no campaign history"
    unpriced = {o.offer_id for o in result.unpriced}
    for plan in result.plans:
        assert not (set(plan.offer_mix()) & unpriced)
    # ...and pricing them anyway is what the report shows, so it must differ.
    assert result.speculative is not None
    assert set(result.speculative.offer_mix()) & unpriced


def test_priced_offers_are_exactly_those_with_a_campaign(tables):
    offers = load_offers(tables)
    used = {r["offer_id"] for r in tables["campaigns"]}
    assert {o.offer_id for o in priced_offers(offers)} == used


# --- the reach decomposition ------------------------------------------------


def test_the_reach_decomposition_is_an_identity(result):
    """volume + composition = the change in saves, exactly."""
    for audit in result.audits:
        reach = audit.reach
        assert reach.volume + reach.composition == pytest.approx(
            reach.saves_permitted - reach.saves_full, abs=1e-9,
        )


def test_the_permitted_audience_is_a_subset_of_the_one_contacted(result):
    for audit in result.audits:
        assert set(audit.permitted_exposed) <= set(audit.exposed)
        assert set(audit.permitted_control) <= set(audit.control)
        assert audit.reach.permitted <= audit.reach.exposed


def test_the_audit_applies_no_rule_that_needs_the_future(tables, result):
    """Cool-off and frequency caps are excluded from the retrospective audit.

    A campaign judged by a contact history that includes campaigns run *after*
    it would fail rules that did not exist when it ran. The audit must depend
    only on consent and eligibility, so removing later campaigns from the
    exposure table cannot change its verdict on the first one.
    """
    first = min(int(r["month_index"]) for r in tables["campaigns"])
    early = {r["campaign_id"] for r in tables["campaigns"] if int(r["month_index"]) == first}

    trimmed = dict(tables)
    trimmed["campaign_exposures"] = [
        r for r in tables["campaign_exposures"] if r["campaign_id"] in early
    ]
    from nbo.audit import audit_retention_campaigns  # noqa: PLC0415

    consent = load_consent(tables)
    ladder = ProductLadder.build(tables)
    before = {a.campaign_id: a.reach.permitted
              for a in audit_retention_campaigns(tables, result.catalogue, ladder, consent)}
    after = {a.campaign_id: a.reach.permitted
             for a in audit_retention_campaigns(trimmed, result.catalogue, ladder, consent)}

    shared = set(before) & set(after)
    assert shared
    for campaign_id in shared:
        assert before[campaign_id] == after[campaign_id]


# --- the economics ----------------------------------------------------------


def test_growth_offers_are_discounted_by_churn_risk(tables, result):
    """An upgrade is only worth its margin if the customer is still there.

    Without this join an engine upsells the customer the retention team is
    trying to save, and the two systems never find out about each other.
    """
    from nbo.value import offer_value  # noqa: PLC0415

    ladder = ProductLadder.build(tables)
    offer = next(o for o in result.catalogue if not o.is_retention)
    product_id = next(r["current_product_id"] for r in tables["customers"])

    def value(risk: float) -> float:
        return offer_value(offer, "C000000", product_id, risk, 0.2, 30.0,
                           ladder, result.economics).expected_value

    assert value(0.5) < value(0.05)


def test_the_contact_cost_follows_the_channel(result):
    costs = result.economics.channel_cost
    assert costs["call"] > costs["sms"] > costs["email"] > costs["push"]
