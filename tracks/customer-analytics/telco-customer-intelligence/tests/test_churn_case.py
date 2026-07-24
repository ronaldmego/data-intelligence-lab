"""Contract tests for case 02 — churn without leakage.

Standard library only, so CI's ``uvx pytest`` runs them with nothing installed.

The tests that matter here are not "does the model score well". They are the
ones that would still pass if the pipeline were quietly broken in the way this
case exists to prevent:

* the feature builder never touches a fact dated after its cutoff;
* the transforms are fitted on training data and *only* on training data;
* the out-of-time split is genuinely out of time;
* the metrics are right, checked against values worked out by hand.

A leaky pipeline produces better numbers, so no assertion on a metric can catch
one. Only assertions on the *mechanism* can.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CASE = Path(__file__).resolve().parent.parent / "02-churn-prediction"
_DATA_MODEL = Path(__file__).resolve().parent.parent / "data-model"
for path in (str(_CASE), str(_DATA_MODEL)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest  # noqa: E402
from churn import build_features, load_tables, run_case, scoreable_population  # noqa: E402
from churn.features import FEATURE_NAMES, _before  # noqa: E402
from churn.metrics import brier_score, evaluate, ks_statistic, log_loss, roc_auc  # noqa: E402
from churn.model import CollinearityFilter, LogisticRegression, Standardiser  # noqa: E402
from telco import Config  # noqa: E402


@pytest.fixture(scope="module")
def tables():
    # Small enough for a fast suite, large enough for the base rates to hold.
    return load_tables(Config(seed=123, n_customers=700, n_months=18))


@pytest.fixture(scope="module")
def result(tables):
    return run_case(tables)


# --- the no-leakage guarantee ---------------------------------------------


def test_feature_builder_ignores_every_fact_after_the_cutoff(tables):
    """The guarantee this whole case is named after.

    Corrupt the tables with facts dated *after* the cutoff and rebuild: if the
    features move at all, something is reading the future.
    """
    population = scoreable_population(tables, "churn_labels_prior")
    ids = population.customer_ids[:120]
    clean = build_features(tables, population.cutoff, ids)

    poisoned = {name: list(rows) for name, rows in tables.items()}
    for name in ("usage_monthly", "billing", "digital_monthly", "support_interactions"):
        future = []
        for row in tables[name]:
            if row["customer_id"] in set(ids):
                copy = dict(row)
                copy["period_month"] = "2099-01-01"
                future.append(copy)
        poisoned[name] = poisoned[name] + future

    assert build_features(poisoned, population.cutoff, ids) == clean


def test_before_is_inclusive_of_the_cutoff_itself():
    """The cutoff month is history, not the future — an off-by-one here silently
    drops the most predictive month in the whole feature set."""
    rows = [{"period_month": "2025-05-01"}, {"period_month": "2025-06-01"}, {"period_month": "2025-07-01"}]
    kept = _before(rows, "2025-06-01")
    assert [r["period_month"] for r in kept] == ["2025-05-01", "2025-06-01"]


def test_populations_are_out_of_time_and_disjoint_in_outcome(result):
    assert result.train.cutoff < result.test.cutoff
    assert len(result.train) > 0 and len(result.test) > 0


def test_scoring_population_drops_customers_who_already_left(tables, result):
    """Anyone who churned in the earlier window must not be scored again."""
    gone = {r["customer_id"] for r in tables["churn_labels_prior"] if int(r["churned_next_90d"]) == 1}
    assert gone, "fixture produced no churn in the earlier window"
    assert not (gone & set(result.test.customer_ids))
    assert result.test.excluded_already_churned == len(gone)


def test_leaky_feature_is_detectable_and_is_not_in_the_real_model(result):
    """The poisoned run must reach a giveaway AUC, and the honest one must not."""
    assert result.with_leakage.auc > 0.97, "the leakage demo failed to leak — it no longer demonstrates anything"
    assert result.out_of_time.auc < 0.90, "the honest model scores implausibly well: check for leakage"


# --- transforms are fitted on training data only ---------------------------


def test_standardiser_uses_only_the_data_it_was_fitted_on():
    standardiser = Standardiser().fit([[0.0], [1.0], [2.0]])  # mean 1.0, sample sd 1.0
    assert standardiser.means == [1.0]
    assert standardiser.sds == [1.0]
    # A wildly out-of-range scoring row must not shift the transform.
    assert standardiser.transform([[100.0]]) == [[99.0]]
    assert standardiser.means == [1.0]


def test_standardiser_survives_a_constant_column():
    standardiser = Standardiser().fit([[5.0, 1.0], [5.0, 3.0]])
    assert standardiser.transform([[5.0, 2.0]])[0][0] == 0.0  # no division by zero


def test_collinearity_filter_drops_duplicates_and_keeps_the_earlier_feature():
    x = [[1.0, 2.0, 9.0], [2.0, 4.0, 1.0], [3.0, 6.0, 4.0], [4.0, 8.0, 7.0]]
    pruner = CollinearityFilter(threshold=0.9).fit(x)
    assert pruner.keep == [0, 2]  # column 1 is a perfect multiple of column 0
    assert pruner.transform([[1.0, 2.0, 3.0]]) == [[1.0, 3.0]]


def test_collinearity_filter_is_applied_to_scoring_data_unchanged(result):
    """Whatever the filter dropped in training must stay dropped at scoring."""
    dropped = {name for name, _, _ in result.dropped_features}
    kept = {d.name for d in result.drivers}
    assert dropped, "the filter dropped nothing — the collinearity check is not running"
    assert not (dropped & kept)
    assert kept | dropped == set(FEATURE_NAMES)


# --- the estimator ---------------------------------------------------------


def test_logistic_regression_recovers_a_known_relationship():
    """A separable-ish signal must produce a large positive coefficient."""
    x = [[float(i)] for i in range(-40, 40)]
    y = [1 if row[0] > 0 else 0 for row in x]
    fitted = LogisticRegression(l2=0.01).fit(x, y)
    assert fitted.converged
    assert fitted.coefficients[0] > 1.0
    assert fitted.predict_proba([[20.0]])[0] > 0.9
    assert fitted.predict_proba([[-20.0]])[0] < 0.1


def test_unpenalised_fit_reproduces_the_base_rate_on_average():
    """A defining property of logistic MLE with an intercept: the mean fitted
    probability equals the observed rate. If it does not, the intercept is being
    shrunk — which is exactly why the L2 penalty here skips it."""
    x = [[float(i % 5)] for i in range(200)]
    y = [1 if i % 10 < 3 else 0 for i in range(200)]
    fitted = LogisticRegression(l2=0.0).fit(x, y)
    mean_predicted = sum(fitted.predict_proba(x)) / len(y)
    assert mean_predicted == pytest.approx(sum(y) / len(y), abs=1e-6)


def test_standard_errors_are_positive_and_shrink_with_sample_size():
    x_small = [[float(i % 7)] for i in range(120)]
    y_small = [i % 2 for i in range(120)]
    small = LogisticRegression(l2=0.0).fit(x_small, y_small)
    large = LogisticRegression(l2=0.0).fit(x_small * 9, y_small * 9)
    assert small.standard_errors[0] > 0
    assert large.standard_errors[0] < small.standard_errors[0]


# --- metrics, against hand-computed values ---------------------------------


def test_roc_auc_on_a_worked_example():
    # Perfect separation, then perfect inversion, then a coin flip.
    assert roc_auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert roc_auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == pytest.approx(0.0)
    assert roc_auc([0.5, 0.5, 0.5, 0.5], [0, 0, 1, 1]) == pytest.approx(0.5)
    # One positive ranked above one of two negatives: 1 of 2 pairs correct.
    assert roc_auc([0.3, 0.7, 0.5], [0, 0, 1]) == pytest.approx(0.5)


def test_roc_auc_handles_ties_as_half_credit():
    """A tie between a churner and a stayer is half a correctly ordered pair,
    not a whole one — otherwise a constant model would score above chance."""
    assert roc_auc([0.5, 0.5], [0, 1]) == pytest.approx(0.5)
    assert roc_auc([0.9, 0.5, 0.5], [1, 0, 1]) == pytest.approx(0.75)


def test_brier_and_log_loss_on_a_worked_example():
    assert brier_score([0.0, 1.0], [0, 1]) == pytest.approx(0.0)
    assert brier_score([0.5, 0.5], [0, 1]) == pytest.approx(0.25)
    assert log_loss([0.5, 0.5], [0, 1]) == pytest.approx(0.6931471805599453)


def test_ks_is_one_for_perfect_separation_and_zero_for_none():
    assert ks_statistic([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == pytest.approx(1.0)
    assert ks_statistic([0.5, 0.5, 0.5, 0.5], [1, 1, 0, 0]) == pytest.approx(0.0)


def test_a_perfectly_calibrated_constant_model_has_zero_calibration_error():
    """1000 customers all scored 30%, of whom exactly 300 churn.

    The labels arrive sorted, which is the trap: cutting a tied group across bin
    boundaries would put all the churners in the first bin and report a wildly
    miscalibrated model. Tied predictions must stay in one bin.
    """
    probabilities = [0.3] * 1000
    y = [1] * 300 + [0] * 700
    evaluation = evaluate(probabilities, y, n_bins=5)
    assert len(evaluation.reliability) == 1, "tied predictions were split across bins"
    assert evaluation.expected_calibration_error == pytest.approx(0.0, abs=1e-9)
    assert evaluation.base_rate == pytest.approx(0.3)


def test_calibration_error_is_reported_when_the_model_is_genuinely_wrong():
    """The complement of the test above: the metric must still fire.

    Two bins of 500. The 0.1 bin is entirely churners (gap 0.9); the 0.9 bin is
    entirely stayers (gap 0.9). Weighted mean: 0.9.
    """
    probabilities = [0.9] * 500 + [0.1] * 500
    y = [0] * 500 + [1] * 500  # exactly backwards
    evaluation = evaluate(probabilities, y, n_bins=2)
    assert len(evaluation.reliability) == 2
    assert evaluation.expected_calibration_error == pytest.approx(0.9, abs=1e-9)
    assert evaluation.auc == pytest.approx(0.0)  # perfectly inverted ranking


def test_deciles_are_ordered_by_risk_and_reliability_is_not(result):
    deciles = result.out_of_time.deciles
    assert deciles[0].mean_predicted > deciles[-1].mean_predicted, "deciles must run riskiest first"
    reliability = result.out_of_time.reliability
    assert reliability[0].mean_predicted < reliability[-1].mean_predicted, "reliability bins must run ascending"


# --- economics -------------------------------------------------------------


def test_expected_value_turns_negative_for_a_worthless_customer(result):
    economics = result.economics
    assert economics.expected_value(churn_probability=0.9, monthly_revenue=0.5) < 0
    assert economics.expected_value(churn_probability=0.9, monthly_revenue=60.0) > 0


def test_break_even_probability_is_where_expected_value_crosses_zero(result):
    economics = result.economics
    revenue = 30.0
    threshold = economics.break_even_probability(revenue)
    assert economics.expected_value(threshold, revenue) == pytest.approx(0.0, abs=1e-9)


def test_value_ranking_beats_risk_ranking_at_the_same_budget(result):
    """The case's commercial claim. If this ever fails, the claim is wrong and
    the write-up has to change — not the assertion."""
    comparison = result.comparison
    assert comparison.uplift_at_capacity > 0
    assert 0.0 < comparison.overlap_at_capacity < 1.0, "the two policies should differ but not entirely"


# --- end to end ------------------------------------------------------------


def test_the_pipeline_is_deterministic(tables):
    first, second = run_case(tables), run_case(tables)
    assert first.out_of_time.auc == second.out_of_time.auc
    assert [d.coefficient for d in first.drivers] == [d.coefficient for d in second.drivers]


def test_the_model_is_better_than_guessing_but_not_suspiciously_good(result):
    """A floor and a ceiling. The ceiling matters more: on this data, an AUC in
    the nineties means something is leaking, not that the model is excellent."""
    assert 0.60 < result.out_of_time.auc < 0.85
    assert result.out_of_time.top_decile_lift > 1.5
    assert result.converged


def test_the_designed_drivers_are_recovered_and_none_are_contradicted(result):
    """The check a real dataset cannot offer: the true signs are known."""
    designed = [d for d in result.drivers if d.designed_sign is not None]
    assert designed, "no designed driver survived pruning"
    assert not [d.name for d in designed if d.recovered is False], "a designed driver came back with the wrong sign"
    assert sum(1 for d in designed if d.recovered is True) >= 3


def test_the_three_readings_are_computed_on_the_populations_they_claim(result):
    """The case compares an out-of-time evaluation against two shortcuts, so the
    thing to pin down is that they really are different evaluations.

    Note what is deliberately *not* asserted: that the in-time AUC comes out
    higher. It usually does, and it does at the default scale — but on a small
    fixture the difference is well inside sampling noise, and a test that
    demanded the sign would be asserting a claim the data does not support. The
    report says the same thing in words.
    """
    assert result.in_time.n < result.out_of_time.n, "the in-time reading must use a held-out slice of training"
    assert result.with_leakage.n == result.in_time.n, "the leakage demo must be the same split, plus one feature"
    assert result.with_leakage.auc > result.in_time.auc, "the leaked feature must dominate the honest ones"
    assert result.out_of_time.n == len(result.test)


def test_auc_standard_error_bounds_the_optimism_gap_honestly(result):
    """The gap must be reported against its own noise, not on its own."""
    assert result.out_of_time.auc_standard_error > 0
    assert result.out_of_time.auc_standard_error < 0.2  # sane magnitude
