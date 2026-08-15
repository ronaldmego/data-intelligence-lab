"""Contract tests for case 04 — ARPU and value decomposition.

Standard library only, so CI's ``uvx pytest`` runs them with nothing installed.

The tests worth having here are the ones that would still pass if the case were
quietly broken in the way it exists to prevent:

* the answer key reaches **nothing**. Cases 03, 05 and 01 each keep a fence
  around ``churn_potential_outcomes`` and assert that only the audit responds to
  it; this case has no audit, so the assertion is stronger — corrupt the table
  and not one number in the whole result may move;
* the revenue figure is case 02's, to the last decimal, so the two cases cannot
  drift into disagreeing about what a customer pays;
* the cost model comes from the CSV, so changing a row changes the answer — a
  cost model that is really a dict in the scoring script passes every other test;
* the break-even costs are *solved*, not read off a sweep grid, so the report can
  quote them to the cent;
* the bridge identity reconciles, and a movement is called readable only when it
  actually clears its own band;
* the collection verdict is derived from the data rather than hardcoded. This is
  the claim the case retracted, and a retraction that cannot flip back when the
  data says otherwise is an opinion;
* whether a tariff straddles a band threshold is **counted**, not inferred from
  its distance to one — a distribution with a hard floor sits close to a cut and
  never crosses it, and the distance-based version of this got that wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TRACK = Path(__file__).resolve().parent.parent
for _name in ("04-arpu-value", "03-next-best-offer", "02-churn-prediction", "01-segmentation",
              "05-campaign-incrementality", "data-model"):
    _path = str(_TRACK / _name)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest  # noqa: E402
from arpu import load_tables, run_case  # noqa: E402
from arpu.collection import measure_collection  # noqa: E402
from arpu.costs import contributions, load_cost_model, plan_contributions  # noqa: E402
from arpu.horizon import expected_remaining_months, monthly_hazard  # noqa: E402
from arpu.stability import measure_axis  # noqa: E402
from fintech import Config  # noqa: E402

SEED = Config(seed=123, n_customers=800, n_months=18)
COST_MODEL = _TRACK / "04-arpu-value" / "cost_model.csv"


@pytest.fixture(scope="module")
def tables():
    return load_tables(SEED)


@pytest.fixture(scope="module")
def result(tables):
    return run_case(tables)


# --- the fence: this case never reads the answer key ------------------------


def test_answer_key_moves_absolutely_nothing(tables, result):
    """Corrupt the counterfactuals: every figure in the case must be unmoved.

    The other cases assert that the answer key moves their audit and nothing
    else. This one has no audit — the question it cannot settle (what a *saved*
    customer does after the data ends) is not in that table either — so the
    correct assertion is that the table is inert end to end. A case that
    consulted it would report a better number, not an error, which is why the
    test asserts on non-response rather than on a value.
    """
    poisoned = {name: [dict(row) for row in rows] for name, rows in tables.items()}
    for row in poisoned["churn_potential_outcomes"]:
        row["churned_next_90d_if_no_campaign"] = "0"
        row["treated"] = "0"
    dirty = run_case(poisoned)

    assert dirty.contribution == result.contribution
    assert dirty.value_chain == result.value_chain
    assert dirty.base == result.base
    assert dirty.collection.risk_correlation == result.collection.risk_correlation
    assert dirty.horizons.hazard.months == result.horizons.hazard.months
    assert dirty.axis.moved == result.axis.moved
    for left, right in zip(dirty.bakeoff.lists, result.bakeoff.lists, strict=True):
        assert left.selected == right.selected


# --- the revenue figure is case 02's ----------------------------------------


def test_revenue_matches_case_02_exactly(result):
    """The level this case decomposes is the one case 02 priced its list with.

    Re-deriving it here — even with the same window and the same field — is how
    two cases end up quoting different ARPUs for the same customer in the same
    meeting.
    """
    assert len(result.profiles) == len(result.churn.monthly_revenue)
    for profile, revenue in zip(result.profiles, result.churn.monthly_revenue, strict=True):
        assert profile.billed == pytest.approx(revenue, abs=1e-9)


def test_measured_arpu_never_falls_below_the_tariff(result):
    """The non-fee part of an invoice is non-negative, so measured ARPU has a
    hard floor at the fee. The value-axis section's central claim depends on it."""
    for profile in result.profiles:
        assert profile.billed >= result.products[profile.product_id].monthly_fee - 1e-9


# --- the cost model is data -------------------------------------------------


def test_cost_model_row_changes_the_contribution(result, tmp_path):
    """Edit one row of the CSV and every contribution must move.

    Nothing else in the suite would notice a cost model that had quietly become
    a constant inside ``costs.py``.
    """
    original = load_cost_model(COST_MODEL)
    baseline = contributions(result.profiles, original)

    text = COST_MODEL.read_text(encoding="utf-8").replace("0.12,currency", "0.40,currency")
    assert "0.40,currency" in text, "the per-1k-of-balance row moved; update this test with it"
    edited = tmp_path / "cost_model.csv"
    edited.write_text(text, encoding="utf-8")

    changed = contributions(result.profiles, load_cost_model(edited))
    assert changed != baseline
    assert all(new < old for new, old in zip(changed, baseline, strict=True))


def test_break_even_costs_are_solved_not_sampled(result):
    """At the reported inversion, the two tariffs must actually be equal.

    The sweep grid is 2 cents wide; the report quotes these to the cent. If they
    were being read off the grid this would fail, and the failure would be a
    number that looks right.
    """
    sensitivity = result.sensitivity
    assert sensitivity.inversion_per_balance is not None

    model = result.cost_model.with_per_balance(sensitivity.inversion_per_balance)
    rows = {p.product_id: p for p in plan_contributions(result.profiles, result.products, model)}
    assert rows[sensitivity.top_product].contribution == pytest.approx(
        rows[sensitivity.cheapest_plan].contribution, abs=1e-6
    )

    # …and it is a genuine crossing: the order is opposite either side of it.
    below = result.cost_model.with_per_balance(sensitivity.inversion_per_balance - 0.02)
    above = result.cost_model.with_per_balance(sensitivity.inversion_per_balance + 0.02)
    lower = {p.product_id: p.contribution for p in plan_contributions(result.profiles, result.products, below)}
    upper = {p.product_id: p.contribution for p in plan_contributions(result.profiles, result.products, above)}
    assert lower[sensitivity.top_product] > lower[sensitivity.cheapest_plan]
    assert upper[sensitivity.top_product] < upper[sensitivity.cheapest_plan]


# --- the bridge -------------------------------------------------------------


def test_bridge_identity_reconciles(result):
    """within + entry − exit must equal the movement, with nothing left over."""
    assert result.bridge.steps
    for step in result.bridge.steps:
        assert step.residual == pytest.approx(0.0, abs=1e-9)


def test_bridge_calls_a_movement_readable_only_when_it_clears_its_band(result):
    for step in result.bridge.steps:
        assert step.readable("total") == (abs(step.total) > 2.0 * step.total_se)
        assert step.readable("within") == (abs(step.within) > 2.0 * step.within_se)


def test_bridge_exit_term_is_structurally_empty(result):
    """Nobody stops being invoiced in this data model. The report says so; if the
    generator ever changes, this fails rather than the claim going stale."""
    assert result.bridge.exit_is_structural_zero
    assert all(step.exit_ == 0.0 for step in result.bridge.steps)


# --- the retracted claim ----------------------------------------------------


def test_collection_verdict_follows_the_data(tables, result):
    """Hand the measurement a risk score aligned with the shortfall by
    construction, and the verdict must flip.

    Deliberately *not* asserted here: which way the flag falls in this fixture
    world. It falls the other way at this size and seed than it does at the
    default, which is the instability the case reports rather than a bug — and a
    test that pinned the verdict would be pinning one world's noise.
    """
    ids = result.population.customer_ids
    honest = measure_collection(tables, ids, result.churn.probabilities, result.cutoff)
    assert honest.risk_correlation == pytest.approx(result.collection.risk_correlation)
    assert abs(honest.risk_correlation) < 0.25, "an effect this size would change the conclusion"

    # Rank customers by their own shortfall and feed that back as "risk".
    rate = {}
    for row in tables["billing"]:
        if row["period_month"] > result.cutoff:
            continue
        billed, paid = rate.get(row["customer_id"], (0.0, 0.0))
        rate[row["customer_id"]] = (billed + float(row["amount_billed"]),
                                    paid + float(row["amount_paid"]))
    rigged = [-(rate[c][1] / rate[c][0]) if rate.get(c, (0, 0))[0] else 0.0 for c in ids]

    planted = measure_collection(tables, ids, rigged, result.cutoff)
    assert planted.concentrates_in_risk
    assert planted.risk_correlation < -0.5
    assert all(fold.r < -0.3 for fold in planted.folds), "a real effect survives the fold split"


def test_fold_split_covers_the_base_exactly(result):
    """The stability check must be a partition, not a sample: five folds, every
    customer in exactly one, or the spread it reports is about the split."""
    collection = result.collection
    assert len(collection.folds) == 5
    assert sum(fold.n for fold in collection.folds) == collection.n_customers


# --- the horizon ------------------------------------------------------------


@pytest.mark.parametrize("p", [0.01, 0.05, 0.118, 0.3, 0.6, 0.9])
def test_hazard_inverts_the_label_window(p):
    """`(1 − h)³ = 1 − p`, exactly. The cancellation the case reports is a
    consequence of this identity, not an empirical coincidence."""
    h = monthly_hazard(p)
    assert (1.0 - h) ** 3 == pytest.approx(1.0 - p, abs=1e-9)


def test_expected_life_respects_its_ceiling():
    assert expected_remaining_months(0.001, cap=36.0) == 36.0
    assert expected_remaining_months(0.9, cap=36.0) < 3.0
    assert expected_remaining_months(0.118, cap=1000.0) > expected_remaining_months(0.5, cap=1000.0)


def test_flat_horizon_barely_reorders_and_the_varying_one_does(result):
    """The case's framing rests on this contrast: the *constant* was nearly
    inert, the *flatness* was not. If a flat sweep ever moved the list as much as
    the hazard horizon does, the section would be about the number 12 instead."""
    flat = next(t for t in result.bakeoff.lists if "flat" in t.name)
    hazard = next(t for t in result.bakeoff.lists if "hazard" in t.name)
    assert result.flat_sweep
    assert min(p.overlap_with_flat for p in result.flat_sweep) > 0.85
    assert flat.overlap(hazard) < min(p.overlap_with_flat for p in result.flat_sweep)


def test_the_bakeoff_is_circular_by_construction(result):
    """Each accounting's own list maximises *expected* profit under it.

    This is the claim that the profit table is arithmetic rather than evidence.
    Realised profit can disagree — sampling noise and miscalibration both move it
    — so the assertion is made on the expectation, which is where the identity
    actually lives.
    """
    probabilities = result.churn.probabilities
    revenue = result.churn.monthly_revenue
    for accounting in result.bakeoff.accountings:
        own = next(t for t in result.bakeoff.lists if t.name.endswith(accounting.name))

        def expected(target, a=accounting):
            return sum(a.expected_value(i, probabilities[i], revenue[i]) for i in target.selected)

        assert all(expected(own) >= expected(other) - 1e-9 for other in result.bakeoff.lists)


# --- the value axis ---------------------------------------------------------


def test_straddling_is_counted_not_inferred_from_distance(result):
    """A tariff can sit close to a threshold and never cross it.

    Measured ARPU is the fee plus a non-negative term, so a cut landing at the
    fee is a wall. The distance-based version of this classified such a tariff as
    exposed; it moved nobody. Kept as a regression.
    """
    for product in result.axis.by_product:
        if not product.straddles:
            assert product.moved == 0
        assert (product.below_cut > 0 and product.above_cut > 0) == product.straddles
        assert product.below_cut + product.above_cut == product.customers


def test_axis_movement_is_concentrated_in_the_straddling_tariffs(result):
    assert result.axis.moved > 0
    assert result.axis.concentration == pytest.approx(1.0)
    assert len(result.axis.still_plans) >= len(result.axis.by_product) - 2


def test_axis_uses_case_01_band_machinery_on_both_cutoffs():
    """Re-cutting at each cutoff is what keeps the bands the same size — the
    reason the aggregate looks calm. A version that froze the earlier cuts would
    report more movement and a different story."""
    before = {f"C{i}": float(i % 9) for i in range(90)}
    after = dict(before)
    after["C1"] = 100.0  # one customer leaps to the top band
    axis = measure_axis(
        before=before, after=after,
        product_of={c: "P" for c in before}, fees={"P": 1.0},
        months_apart=6, months_averaged=3,
    )
    assert axis.n == 90
    assert axis.moved >= 1
