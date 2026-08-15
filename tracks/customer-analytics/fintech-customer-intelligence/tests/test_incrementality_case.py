"""Contract tests for case 05 — campaign incrementality.

Standard library only, so CI's ``uvx pytest`` runs them with nothing installed.

The tests that matter here are not "is the effect the right size". They are the
ones that would still pass if the case were quietly broken in the way it exists
to prevent:

* the answer key never reaches the estimators — an estimate that consults the
  truth is not an estimate, and the failure would look like an excellent result;
* the two arms really are the two arms that were randomised;
* the balance check reads nothing the campaign could have changed;
* the arithmetic of the estimators matches values worked out by hand.

The first is the one with teeth. A case that peeks at ``churn_potential_outcomes``
would report *better* numbers, so no assertion on an estimate can catch it — only
an assertion that corrupting the answer key leaves every estimate untouched.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

_CASE = Path(__file__).resolve().parent.parent / "05-campaign-incrementality"
_CHURN = Path(__file__).resolve().parent.parent / "02-churn-prediction"
_DATA_MODEL = Path(__file__).resolve().parent.parent / "data-model"
for path in (str(_CASE), str(_CHURN), str(_DATA_MODEL)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest  # noqa: E402
from incrementality import build_audience, load_campaigns, load_tables, run_case  # noqa: E402
from incrementality.balance import check_balance  # noqa: E402
from incrementality.economics import measured_save_rate  # noqa: E402
from incrementality.estimators import (  # noqa: E402
    Estimate,
    difference_in_proportions,
    is_weak,
    minimum_detectable_effect,
    pool,
    power_at,
    required_per_arm,
    wald,
)
from fintech import Config  # noqa: E402


@pytest.fixture(scope="module")
def tables():
    # Small enough for a fast suite, large enough that the arms are not degenerate.
    return load_tables(Config(seed=123, n_customers=800, n_months=18))


@pytest.fixture(scope="module")
def result(tables):
    return run_case(tables)


@pytest.fixture(scope="module")
def retention_audience(tables):
    campaign = next(c for c in load_campaigns(tables) if c.is_retention)
    return build_audience(tables, campaign)


# --- the fence around the answer key ---------------------------------------


def test_the_ground_truth_never_reaches_an_estimate(tables):
    """Corrupt the answer key; every estimate must be unmoved.

    This is the test the case is named after. The potential-outcomes table is
    the one thing here that no real dataset has, so a case that quietly used it
    would produce numbers nobody could reproduce — and they would look *better*,
    which is why only a mechanism test can catch it.
    """
    honest = run_case(tables)

    poisoned = dict(tables)
    poisoned["churn_potential_outcomes"] = [
        {**row, "churned_next_90d_if_no_campaign": 1 - int(row["churned_next_90d_if_no_campaign"])}
        for row in tables["churn_potential_outcomes"]
    ]
    # Deliberately run the *full* path, with the answer key loaded and available.
    # Running with `use_truth=False` would pass this test trivially, since the
    # table is never read at all — and would therefore prove nothing.
    cheated = run_case(poisoned)
    assert cheated.truth is not None

    assert [e.value for e in cheated.naive] == [e.value for e in honest.naive]
    assert cheated.pooled_itt.value == honest.pooled_itt.value
    assert cheated.pooled_compliance.value == honest.pooled_compliance.value
    assert cheated.pooled_cace.value == honest.pooled_cace.value
    assert cheated.save_rate.value == honest.save_rate.value
    assert cheated.save_rate.ci_low == honest.save_rate.ci_low
    for a, b in zip(cheated.retention + cheated.negative_controls,
                    honest.retention + honest.negative_controls, strict=True):
        assert a.itt.value == b.itt.value
        assert a.compliance.value == b.compliance.value
        assert a.cace.value == b.cace.value
        assert [c.standardised_difference for c in a.balance.covariates] == \
               [c.standardised_difference for c in b.balance.covariates]
    for a, b in zip(cheated.retention, honest.retention, strict=True):
        assert [s.estimate.value for s in a.heterogeneity.strata] == \
               [s.estimate.value for s in b.heterogeneity.strata]

    # ...and the check is live: the truth-derived commentary *did* move, so the
    # assertions above are comparing runs that genuinely differ.
    assert cheated.true_delivered != honest.true_delivered
    assert cheated.retention[0].decomposition.delivered != honest.retention[0].decomposition.delivered


def test_running_without_the_answer_key_still_produces_every_estimate(tables):
    """The case must stand up on what a real analysis would have."""
    blind = run_case(tables, use_truth=False)
    assert blind.truth is None
    assert blind.pooled_itt.standard_error > 0
    assert blind.save_rate.true_value is None
    assert blind.retention[0].decomposition is None
    # ...and the estimates are the same ones the full run reports.
    assert blind.pooled_itt.value == pytest.approx(run_case(tables).pooled_itt.value)


# --- the data model's counterfactual ---------------------------------------


def test_the_campaign_can_only_ever_reduce_churn(result):
    """A retention offer that raises churn would mean the generator is wrong."""
    assert all(v <= 0 for v in result.truth.effect.values())


def test_untreated_customers_have_no_effect(tables, result):
    """Nobody who never took an offer may differ between the two worlds.

    Guards the shared-uniform-draw trick: if the counterfactual were computed
    from a fresh random draw, untreated customers would flip too, and every
    decomposition in the report would be noise.
    """
    treated = {r["customer_id"] for r in tables["churn_potential_outcomes"]
               if int(r["treated"]) == 1}
    untouched = [c for c, v in result.truth.effect.items() if c not in treated]
    assert untouched
    assert all(result.truth.effect[c] == 0 for c in untouched)


def test_potential_outcomes_cover_both_cutoffs(tables):
    rows = tables["churn_potential_outcomes"]
    cutoffs = {r["observation_cutoff"] for r in rows}
    assert cutoffs == {tables["churn_labels"][0]["observation_cutoff"],
                       tables["churn_labels_prior"][0]["observation_cutoff"]}
    assert len(rows) == len(tables["churn_labels"]) + len(tables["churn_labels_prior"])


def test_the_decomposition_is_an_identity(result):
    """observed = delivered + imbalance, exactly — not approximately."""
    for r in result.retention + result.negative_controls:
        d = r.decomposition
        assert d.observed == pytest.approx(d.delivered + d.imbalance, abs=1e-12)
        assert d.observed == pytest.approx(r.itt.value, abs=1e-12)


# --- the randomisation ------------------------------------------------------


def test_the_arms_partition_the_audience(retention_audience):
    a = retention_audience
    assert set(a.exposed).isdisjoint(a.control)
    assert len(a.exposed) + len(a.control) == len(a)
    assert a.exposed and a.control


def test_nobody_held_back_responded_to_the_campaign_they_were_held_back_from(retention_audience):
    """One-sided non-compliance — the assumption the Wald estimator rests on."""
    assert retention_audience.responded.isdisjoint(retention_audience.control)


def test_the_control_arm_is_contaminated_only_by_the_other_campaign(result):
    """The held-back arm is not untreated, and the first stage must say so.

    If the first stage were computed against this campaign's responses alone it
    would read as the full response rate, overstating the denominator and
    deflating the complier effect it divides out.
    """
    for r in result.retention:
        treated_controls = [c for c in r.audience.control if c in r.audience.treated]
        assert treated_controls, "expected cross-campaign contamination in this data model"
        assert r.compliance.value < len(r.audience.responded) / len(r.audience.exposed)


def test_strata_partition_the_audience_without_losing_anyone(result):
    for r in result.retention:
        counted = sum(s.n_exposed + s.n_control for s in r.heterogeneity.strata)
        assert counted == len(r.audience)


# --- the balance check ------------------------------------------------------


def test_balance_reads_nothing_dated_after_the_campaign(tables, retention_audience):
    """Poison the facts with post-campaign rows; the balance table must not move."""
    clean = check_balance(tables, retention_audience)

    poisoned = dict(tables)
    for name in ("activity_monthly", "billing", "digital_monthly", "support_interactions"):
        extra = [{**row, "period_month": "2099-01-01"} for row in tables[name][:200]]
        poisoned[name] = [*tables[name], *extra]
    after = check_balance(poisoned, retention_audience)

    assert [c.name for c in after.covariates] == [c.name for c in clean.covariates]
    for a, b in zip(after.covariates, clean.covariates, strict=True):
        assert a.standardised_difference == pytest.approx(b.standardised_difference, abs=1e-12)


def test_constant_covariates_are_dropped_not_reported_as_balanced(result):
    """A column with no variance cannot be imbalanced; padding the table with
    rows that can never fail would flatter every experiment."""
    early, late = result.retention[0].balance, result.retention[1].balance
    assert len(early.covariates) < len(late.covariates)
    assert all(c.standard_error > 0 for c in early.covariates)


# --- estimator arithmetic, against values worked out by hand ----------------


def test_difference_in_proportions_matches_hand_arithmetic():
    treatment = [1, 1, 0, 0]        # 0.5
    control = [1, 0, 0, 0, 0]       # 0.2
    e = difference_in_proportions("t", treatment, control)
    assert e.value == pytest.approx(0.3)
    expected_se = math.sqrt(0.5 * 0.5 / 4 + 0.2 * 0.8 / 5)
    assert e.standard_error == pytest.approx(expected_se)
    assert e.ci_low == pytest.approx(0.3 - 1.959963984540054 * expected_se)


def test_wald_divides_the_itt_by_the_first_stage():
    itt = Estimate("itt", -0.04, 0.01, 100, 100)
    compliance = Estimate("first stage", 0.20, 0.02, 100, 100)
    cace = wald(itt, compliance)
    assert cace.value == pytest.approx(-0.20)
    # Bloom approximation: the first stage is treated as known.
    assert cace.standard_error == pytest.approx(0.05)


def test_a_weak_first_stage_is_flagged_before_the_ratio_is_believed():
    strong = Estimate("first stage", 0.20, 0.02, 100, 100)   # z = 10
    weak = Estimate("first stage", 0.004, 0.02, 100, 100)    # z = 0.2
    assert not is_weak(strong)
    assert is_weak(weak)
    # ...and the ratio it produces is exactly the nonsense the guard exists for.
    assert abs(wald(Estimate("itt", 0.02, 0.01, 100, 100), weak).value) > 1.0


def test_pooling_weights_by_precision():
    precise = Estimate("a", -0.10, 0.01, 100, 100)
    vague = Estimate("b", 0.10, 0.02, 100, 100)
    pooled = pool([precise, vague], "pooled")
    # Weights 1/1e-4 and 1/4e-4 -> 4:1 in favour of the precise estimate.
    assert pooled.value == pytest.approx((-0.10 * 10000 + 0.10 * 2500) / 12500)
    assert pooled.standard_error == pytest.approx(math.sqrt(1 / 12500))
    assert pooled.standard_error < precise.standard_error


def test_power_and_sample_size_are_inverses():
    base, n = 0.30, 900
    mde = minimum_detectable_effect(n, n, base)
    assert power_at(mde, math.sqrt(2 * base * (1 - base) / n)) == pytest.approx(0.80, abs=1e-3)
    assert required_per_arm(mde, base) == pytest.approx(n, rel=0.01)


def test_the_case_power_model_matches_its_own_requirement(result):
    """The curve, the marker and the printed requirement come from one function."""
    assert result.power_at_control(result.required_control) >= 0.80
    assert result.power_at_control(result.required_control - 1) < 0.80
    actual = len(result.retention[0].audience.control)
    assert result.power_at_control(actual) == pytest.approx(result.realised_power, rel=0.10)


# --- the translation back into case 02's units ------------------------------


def test_save_rate_is_the_itt_over_control_churn_with_the_interval_flipped():
    itt = Estimate("itt", -0.04, 0.01, 100, 100)
    save = measured_save_rate(itt, control_churn=0.32, assumed=0.25)
    assert save.value == pytest.approx(0.04 / 0.32)
    # Negating flips the ends: the most negative ITT is the highest save rate.
    assert save.ci_low == pytest.approx(-itt.ci_high / 0.32)
    assert save.ci_high == pytest.approx(-itt.ci_low / 0.32)
    assert save.ci_low < save.value < save.ci_high


def test_save_rate_reports_whether_it_can_rule_anything_out():
    wide = measured_save_rate(Estimate("itt", -0.04, 0.03, 100, 100), 0.32, assumed=0.25)
    assert wide.covers_zero and wide.covers_assumption
    tight = measured_save_rate(Estimate("itt", -0.04, 0.002, 100, 100), 0.32, assumed=0.25)
    assert not tight.covers_zero and not tight.covers_assumption


# --- the falsification test itself ------------------------------------------


def test_campaigns_with_no_mechanism_return_nothing(result):
    """The negative control has to come back empty, or the pipeline is broken."""
    assert result.negative_controls
    for r in result.negative_controls:
        assert r.itt.ci_low <= 0 <= r.itt.ci_high, f"{r.audience.campaign.campaign_id} invented an effect"
        assert r.weak_first_stage, "an upsell should not deliver retention offers"
