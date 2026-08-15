"""Contract tests for case 01 — actionable segmentation.

Standard library only, so CI's ``uvx pytest`` runs them with nothing installed.

The tests worth having here are the ones that would still pass if the case were
quietly broken in the way it exists to prevent:

* the answer key reaches the causal audit and **nothing else** — the same fence
  cases 03 and 05 keep, now that a third case consumes it;
* the playbook comes from the CSV, so changing a row changes the contact list —
  a playbook that is really a hardcoded dict passes every other test;
* whether a cell is contacted is a declared column, not a substring of its
  action text. A play reading *"no contact this wave"* contains the word, and
  the keyword version of this scored it as an outbound contact — a real defect,
  caught here, kept as a regression;
* the stability claim is measured out-of-sample, and the in-sample version is
  the more flattering of the two, which is the direction the report asserts;
* a dimension with no variance reports **no** churn spread, because sorting a
  constant produces quintiles that differ only by row order;
* segment profiles are computed from the features, so a cell cannot be labelled
  with a trait it does not have.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

_TRACK = Path(__file__).resolve().parent.parent
for _name in ("01-segmentation", "02-churn-prediction", "03-next-best-offer",
              "05-campaign-incrementality", "data-model"):
    _path = str(_TRACK / _name)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest  # noqa: E402
from segmentation import load_tables, run_case  # noqa: E402
from segmentation.grid import Cuts, band_of, build_segments, load_playbook, quantile_cuts  # noqa: E402
from segmentation.rfm import classic_rfm, correlation, tenure_of  # noqa: E402
from fintech import Config  # noqa: E402

SEED = Config(seed=123, n_customers=800, n_months=18)
PLAYBOOK = _TRACK / "01-segmentation" / "playbook.csv"


@pytest.fixture(scope="module")
def tables():
    return load_tables(SEED)


@pytest.fixture(scope="module")
def result(tables):
    return run_case(tables)


# --- the fence around the answer key ---------------------------------------


def test_answer_key_moves_the_audit_and_nothing_else(tables):
    """Corrupt the counterfactuals: every decision must be unmoved.

    The failure this guards against does not raise. A case that consulted the
    answer key to *produce* a decision would report a better result, so no
    assertion on a number could catch it — only an assertion that the numbers do
    not respond to the table at all.
    """
    clean = run_case(tables)

    poisoned = {name: [dict(row) for row in rows] for name, rows in tables.items()}
    for row in poisoned["churn_potential_outcomes"]:
        row["churned_next_90d_if_no_campaign"] = "0"
    dirty = run_case(poisoned)

    assert [len(s) for s in dirty.segments] == [len(s) for s in clean.segments]
    assert [s.name for s in dirty.segments] == [s.name for s in clean.segments]
    assert dirty.decision.by_expected_value.rows == clean.decision.by_expected_value.rows
    assert dirty.decision.by_segment.rows == clean.decision.by_segment.rows
    assert [d.reachable for d in dirty.deliverability] == [d.reachable for d in clean.deliverability]
    assert dirty.honest_migration.cell_changed == clean.honest_migration.cell_changed

    # …and the audit, which is the only consumer, must actually respond.
    assert dirty.causal.total_outcomes_changed != clean.causal.total_outcomes_changed


# --- the playbook is data ---------------------------------------------------


def test_playbook_row_changes_the_contact_list(tables, tmp_path):
    """Flip one cell from contacting to not, and the plan must change.

    The only test a playbook hardcoded in Python would fail.
    """
    rows = list(csv.DictReader(PLAYBOOK.open(newline="", encoding="utf-8")))
    for row in rows:
        if row["segment"] == "Rescue":
            row["contact"] = "no"
            row["offer_type"] = "none"

    altered = tmp_path / "playbook.csv"
    with altered.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    baseline = run_case(tables)
    changed = run_case(tables, playbook_path=altered)

    assert changed.decision.by_segment.rows != baseline.decision.by_segment.rows
    assert changed.decision.contacting_segments < baseline.decision.contacting_segments
    assert "Rescue" not in [d.segment for d in changed.deliverability]
    # The continuous ranking knows nothing about the playbook and must not move.
    assert changed.decision.by_expected_value.rows == baseline.decision.by_expected_value.rows


def test_contact_is_a_column_not_a_substring():
    """A play whose action says "no contact" is not an outbound contact.

    The regression: inferring this from the action text scored *"no contact this
    wave; re-score next month"* as contacting, because the string is in there.
    """
    playbook = load_playbook(PLAYBOOK)
    saying_no = [play for play in playbook.values()
                 if play.action.lower().startswith(("no contact", "no outbound"))]
    assert saying_no, "the playbook should still contain plays that decline to contact"
    assert all(not play.contacts for play in saying_no)
    assert all(not play.has_offer for play in saying_no)


def test_every_grid_cell_has_a_play(result):
    """No customer may land in a cell the playbook does not describe."""
    assert len(result.segments) == len(result.playbook)
    assert sum(len(s) for s in result.segments) == len(result.after)


# --- RFM diagnostics --------------------------------------------------------


def test_a_constant_dimension_reports_no_spread(tables, result):
    """Recency is constant here, and a constant must not produce a finding."""
    months = sorted({r["period_month"] for r in tables["activity_monthly"]})
    labels = {c: result.test.labels[c] for c in result.test.customer_ids}
    letters = classic_rfm(tables, result.test.cutoff, result.test.customer_ids, labels, months)
    recency = next(letter for letter in letters if letter.symbol == "R")

    assert recency.distinct == 1
    assert recency.degenerate
    assert not recency.quintiles_separate
    assert recency.readable_spread == 0.0
    # The raw spread is non-zero — that is the trap. It must simply not be the
    # number the report is allowed to quote.
    assert recency.spread >= 0.0


def test_frequency_is_tenure(tables, result):
    """Invoice count is months-as-a-customer, not a behavioural measure."""
    months = sorted({r["period_month"] for r in tables["activity_monthly"]})
    labels = {c: result.test.labels[c] for c in result.test.customer_ids}
    letters = classic_rfm(tables, result.test.cutoff, result.test.customer_ids, labels, months)
    frequency = next(letter for letter in letters if letter.symbol == "F")

    assert correlation(frequency.values, tenure_of(tables, result.test.customer_ids)) > 0.999


def test_engagement_recency_recovers_variation(result):
    """The repaired dimension must separate where the original could not."""
    repaired = result.repaired_recency
    monetary = next(letter for letter in result.letters if letter.symbol == "M")

    assert repaired.quintiles_separate
    assert repaired.readable_spread > monetary.readable_spread


# --- stability --------------------------------------------------------------


def test_in_sample_migration_understates(result):
    """The flattering measurement must be the flattering one.

    The report claims the cross-fitted figure is a ceiling on optimism, so if
    this ever inverted the claim would be backwards rather than merely noisy.
    """
    honest, naive = result.honest_migration, result.in_sample_migration
    assert honest.basis == "cross-fitted"
    assert honest.share(honest.cell_changed) >= naive.share(naive.cell_changed)


def test_risk_axis_moves_more_than_the_value_axis(result):
    """The structural finding, asserted rather than admired."""
    migration = result.honest_migration
    assert migration.share(migration.risk_band_changed) > migration.share(migration.value_band_changed)
    # And the aggregate hides it: sizes barely move while individuals do.
    assert migration.size_drift < migration.share(migration.cell_changed)


def test_migration_counts_are_bounded_by_the_population(result):
    for migration in result.migrations:
        assert 0 < migration.n <= len(result.after)
        assert migration.cell_changed <= migration.n
        assert migration.risk_band_changed + migration.value_band_changed >= migration.cell_changed


# --- the grid ---------------------------------------------------------------


def test_bands_are_equal_thirds(result):
    """Quantile cuts must actually split the population evenly."""
    sizes = [len(s) for s in result.segments]
    expected = len(result.after) / len(sizes)
    assert max(sizes) < expected * 1.6
    assert min(sizes) > expected * 0.4


def test_profiles_are_computed_from_the_features(result):
    """A cell's traits must be a property of its members, not a label."""
    rescue = next(s for s in result.segments if s.name == "Rescue")
    calm = next(s for s in result.segments if s.name == "Self-serve")

    assert rescue.traits and calm.traits
    assert rescue.mean_risk > calm.mean_risk
    # The high-risk cell must not claim the low-risk cell's profile.
    assert {t.feature for t in rescue.traits} != {t.feature for t in calm.traits}
    for segment in result.segments:
        assert all(abs(trait.z) >= abs(segment.traits[-1].z) - 1e-9 for trait in segment.traits)


def test_quantile_cuts_and_bands_agree():
    values = [float(i) for i in range(9)]
    cuts = quantile_cuts(values, 3)
    assert [band_of(v, cuts) for v in values] == [0, 0, 0, 1, 1, 1, 2, 2, 2]


def test_cuts_reused_across_snapshots_are_the_same_rule(result):
    """A cell lookup must depend only on the cuts, not on which snapshot it came from."""
    cuts = Cuts(risk=[0.1, 0.2], value=[10.0, 20.0])
    assert cuts.cell_of(0.05, 5.0) == (0, 0)
    assert cuts.cell_of(0.25, 25.0) == (2, 2)
    assert cuts.cell_of(0.15, 5.0) == (1, 0)


# --- deliverability and the decision test -----------------------------------


def test_only_cells_with_an_offer_are_judged_on_delivery(result):
    """A cell with no offer has nothing to deliver and must not be scored."""
    with_offers = {s.name for s in result.segments if s.play.has_offer}
    assert {d.segment for d in result.deliverability} == with_offers
    for row in result.deliverability:
        assert row.reachable + row.blocked_by_policy + row.blocked_by_eligibility == row.members


def test_the_high_risk_third_is_less_reachable(result):
    """The direction the report claims — and only the direction.

    This started as an assertion that reachability falls monotonically with
    risk, cell by cell, which is what the first draft of the report said. It
    failed on this seed, and the report was corrected rather than the test: the
    monotone version is not true at 800 customers, is not true at 5,000 either,
    and nine cells of a few hundred cannot support a nine-step ordering. What
    survives across seeds is the gap between the extreme thirds.
    """
    low, high = result.reach_low_risk_third, result.reach_high_risk_third
    assert low > high


def test_the_monotone_version_is_not_asserted_by_the_report(result):
    """The stronger claim must be measured, not assumed, wherever it appears.

    ``reach_falls_with_risk`` exists so the report can only make the monotone
    claim when the run supports it. This asserts the flag is derived from the
    rows rather than hardcoded — a flag that always returned ``True`` would let
    the false version of the sentence back in.
    """
    from segmentation.reach import PolicyReach, falls_with_risk

    rising = [PolicyReach("a", 0.1, 100, 90), PolicyReach("b", 0.2, 100, 80)]
    broken = [PolicyReach("a", 0.1, 100, 70), PolicyReach("b", 0.2, 100, 80)]
    assert falls_with_risk(rising)
    assert not falls_with_risk(broken)
    assert result.reach_falls_with_risk == falls_with_risk(result.policy_reach)


def test_upgrade_plays_are_refused_by_the_catalogue(result):
    """The robust deliverability finding: two plays do not apply at all.

    Unlike the reachability gradient, this holds by construction rather than by
    luck — the grow cell is *defined* as the top third by value, and the top
    third by value is the customers already at the top of the product ladder.
    """
    upgrades = [d for d in result.deliverability if d.offer_type == "upgrade"]
    assert upgrades, "the playbook should still contain an upgrade play"
    assert all(d.blocked_by_eligibility > 0 for d in upgrades)
    assert any(d.play_does_not_apply for d in upgrades)
    # And the discount plays, which the catalogue does serve, must not be.
    for row in result.deliverability:
        if row.offer_type == "discount":
            assert row.blocked_by_eligibility == 0


def test_both_lists_spend_the_same_budget(result):
    test = result.decision
    assert len(test.by_expected_value) == test.capacity
    assert len(test.by_segment) == test.capacity
    assert 0.0 <= test.overlap <= 1.0


def test_the_playbook_list_only_contains_contacting_cells(result):
    """The plan must not contact a cell the playbook told it not to."""
    forbidden = {i for s in result.segments if not s.play.contacts for i in s.members}
    assert not (set(result.decision.by_segment.rows) & forbidden)


# --- determinism ------------------------------------------------------------


def test_two_runs_are_identical(tables):
    """Same seed, same tables, byte-identical result."""
    from segmentation.report import render

    first, second = run_case(tables), run_case(tables)
    assert render(first) == render(second)


def test_case_runs_without_the_committed_data(tables):
    """Everything is generated in memory from the seed; no setup step."""
    result = run_case(tables)
    assert len(result.after) > 0
    assert result.decision is not None
    assert result.causal is not None
    assert result.segments


def test_segments_are_built_from_the_snapshot_not_the_labels(result):
    """Cell assignment must not consult the outcome.

    Rebuild the grid with every label flipped: membership must be identical,
    because the label is evaluation-only. It moves the *realised churn* column
    and nothing else.
    """
    snapshot = result.after
    flipped = type(snapshot)(
        cutoff=snapshot.cutoff,
        customer_ids=snapshot.customer_ids,
        risk=snapshot.risk,
        value=snapshot.value,
        labels=[1 - y for y in snapshot.labels],
        features=snapshot.features,
    )
    rebuilt = build_segments(flipped, result.cuts, result.playbook, result.economics)

    assert [s.members for s in rebuilt] == [s.members for s in result.segments]
    assert [s.mean_risk for s in rebuilt] == [s.mean_risk for s in result.segments]
    assert [s.realised_churn for s in rebuilt] != [s.realised_churn for s in result.segments]
