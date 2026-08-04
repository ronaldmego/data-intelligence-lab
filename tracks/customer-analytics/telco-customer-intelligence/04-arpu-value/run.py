#!/usr/bin/env python3
"""Run the ARPU / value-decomposition case and write the report and charts.

    uv run run.py                          # defaults, writes to outputs/
    uv run run.py --customers 1000         # a smaller world, for a quick look
    uv run run.py --seed 7                 # a different world
    uv run run.py --per-gb 0.32            # re-price at the inversion point
    uv run run.py --cap-months 12          # case 02's ceiling, as a ceiling on life
    uv run run.py --data-dir ../data-model/data   # read CSVs instead of generating
    python run.py                          # stdlib only — no dependencies to install

Refits case 02's churn model, because the risk score is an input here rather than
a deliverable. Deterministic: the same seed produces the same report, byte for
byte.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-model"))

from arpu import load_tables, run_case  # noqa: E402
from arpu.charts import axis_chart, bridge_chart, chain_chart, horizon_chart, usage_chart  # noqa: E402
from arpu.costs import load_cost_model  # noqa: E402
from arpu.pipeline import DEFAULT_CAP_MONTHS, MEASURED_SAVE_RATE  # noqa: E402
from arpu.report import render  # noqa: E402
from telco import Config  # noqa: E402

CHAIN_NOTES = {
    "plan fee": "what the customer signed",
    "billed ARPU": "plus the non-fee part of the invoice",
    "collected ARPU": "minus what was never paid",
    "contribution": "minus the cost of serving them",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=Config.n_customers)
    ap.add_argument("--months", type=int, default=Config.n_months)
    ap.add_argument("--seed", type=int, default=Config.seed)
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="read generated CSVs instead of generating")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "outputs")
    ap.add_argument("--cost-model", type=Path, default=None,
                    help="an alternative cost model CSV")
    ap.add_argument("--per-gb", type=float, default=None,
                    help="override the marginal cost per gigabyte from the cost model")
    ap.add_argument("--cap-months", type=float, default=DEFAULT_CAP_MONTHS,
                    help="ceiling on the hazard-implied customer life")
    ap.add_argument("--capacity-share", type=float, default=0.10,
                    help="contacts available, as a share of the base")
    ap.add_argument("--save-rate", type=float, default=MEASURED_SAVE_RATE,
                    help="the rate case 05 measured; case 02 assumed 0.25")
    args = ap.parse_args()

    cfg = Config(seed=args.seed, n_customers=args.customers, n_months=args.months)
    tables = load_tables(cfg, data_dir=args.data_dir)

    cost_model = load_cost_model(args.cost_model) if args.cost_model else load_cost_model()
    if args.per_gb is not None:
        cost_model = cost_model.with_per_gb(args.per_gb)

    print("Refitting case 02's churn model — the risk score is an input here...")
    result = run_case(
        tables,
        cost_model=cost_model,
        save_rate=args.save_rate,
        cap_months=args.cap_months,
        capacity_share=args.capacity_share,
    )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "report.md": render(result),
        "chain.svg": chain_chart(result.value_chain, CHAIN_NOTES),
        "usage.svg": usage_chart(result.usage),
        "bridge.svg": bridge_chart(result.bridge),
        "horizon.svg": horizon_chart(result.horizons, result.cap_sweep, "case 02's list"),
        "axis.svg": axis_chart(result.axis),
    }
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")

    base, split, variance = result.base, result.split, result.variance
    usage, bridge, collection = result.usage, result.bridge, result.collection
    sensitivity, horizons, bakeoff, axis = result.sensitivity, result.horizons, result.bakeoff, result.axis
    flat = next(t for t in bakeoff.lists if "flat" in t.name)
    hazard = next(t for t in bakeoff.lists if "hazard" in t.name)
    revenue_only = next(t for t in bakeoff.lists if t.name == "by revenue alone")

    print(f"\n  base              {len(result.population):,} customers at {result.cutoff}")
    print(f"  revenue base      {base.phantom_share:.1%} of billed revenue belongs to customers who "
          f"already left; ARPU moves {abs(base.arpu_live_only / base.arpu_with_departed - 1):.2%}")
    print(f"  level             {variance.between_share:.2%} of invoice variance is between tariffs; "
          f"overage is {split.overage_share:.1%} of revenue")
    print(f"  usage link        r={usage.overall.r:+.4f} aggregated, {usage.largest_within.r:+.4f} at most "
          f"within a plan ({usage.ratio:.0f}x)")
    print(f"  bridge            {len(bridge.readable_steps)} of {len(bridge.steps)} transitions clear "
          f"±2 se; base grew {bridge.base_growth:+.0%}, ARPU range {bridge.level_range:.2f}")
    print(f"  collection        {collection.loss_rate:.2%} never paid; risk correlation "
          f"{collection.risk_correlation:+.4f} ± {2 * collection.risk_correlation_se:.4f} "
          f"({'concentrates' if collection.concentrates_in_risk else 'does not concentrate'})")
    print(f"  contribution      mean {result.mean_contribution:,.2f} at {result.cost_model.per_gb:.2f}/GB; "
          f"{sensitivity.top_plan} falls below {sensitivity.cheapest_plan} at "
          f"{sensitivity.inversion_per_gb:.2f}/GB")
    print(f"  horizon           implied life {horizons.hazard.quantile(0.5):.0f} months median, "
          f"{horizons.below_flat_share:.1%} below case 02's flat {horizons.flat_months:.0f}; "
          f"p/h mean {result.cancellation.mean_ratio:.3f}")
    print(f"  target list       flat vs hazard {flat.overlap(hazard):.1%} overlap; "
          f"hazard vs revenue-only {hazard.overlap(revenue_only):.1%}; "
          f"each accounting crowns its own list: {bakeoff.every_list_wins_under_its_own}")
    print(f"  value axis        {axis.share_moved:.1%} changed band; "
          f"{len(axis.still_plans)} of {len(axis.by_plan)} tariffs moved nobody; "
          f"{axis.concentration:.0%} of movers are {axis.worst_plan.plan_id}")
    print(f"\nWrote {len(written)} files to {out}/")


if __name__ == "__main__":
    main()
