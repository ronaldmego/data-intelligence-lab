#!/usr/bin/env python3
"""Run the actionable-segmentation case and write the report and charts.

    uv run run.py                      # defaults, writes to outputs/
    uv run run.py --customers 1000     # a smaller world, for a quick look
    uv run run.py --data-dir ../data-model/data   # read CSVs instead of generating
    python run.py                      # stdlib only — no dependencies to install

Fits case 02's churn model twice: once as that case does, and once cross-fitted,
because measuring whether a segment survives six months with a score that had
memorised the earlier cutoff would understate the answer.

Deterministic: the same seed produces the same report, byte for byte.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-model"))

from segmentation import load_tables, run_case  # noqa: E402
from segmentation.charts import axes_chart, drift_chart, grid_chart, reach_chart  # noqa: E402
from segmentation.pipeline import MEASURED_SAVE_RATE  # noqa: E402
from segmentation.report import render  # noqa: E402
from telco import Config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=Config.n_customers)
    ap.add_argument("--months", type=int, default=Config.n_months)
    ap.add_argument("--seed", type=int, default=Config.seed)
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="read generated CSVs instead of generating")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "outputs")
    ap.add_argument("--bands", type=int, default=3, help="bands per axis (3 = thirds)")
    ap.add_argument("--capacity-share", type=float, default=0.10,
                    help="contacts available, as a share of the base")
    ap.add_argument("--save-rate", type=float, default=MEASURED_SAVE_RATE,
                    help="the rate case 05 measured; case 02 assumed 0.25")
    ap.add_argument("--playbook", type=Path, default=None,
                    help="an alternative playbook CSV")
    args = ap.parse_args()

    cfg = Config(seed=args.seed, n_customers=args.customers, n_months=args.months)
    tables = load_tables(cfg, data_dir=args.data_dir)

    print("Refitting case 02's churn model — twice, so the stability claim is not in-sample...")
    result = run_case(
        tables,
        bands=args.bands,
        capacity_share=args.capacity_share,
        save_rate=args.save_rate,
        playbook_path=args.playbook,
    )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "report.md": render(result),
        "grid.svg": grid_chart(result.segments, bands=args.bands),
        "axes.svg": axes_chart(result.letters, result.repaired_recency),
        "drift.svg": drift_chart(result.honest_migration),
        "reach.svg": reach_chart(result.deliverability),
    }
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")

    migration = result.honest_migration
    decision = result.decision
    assert decision is not None

    print(f"\n  base              {len(result.after):,} customers at {result.after.cutoff}, "
          f"{args.bands}x{args.bands} grid")
    degenerate = [letter.symbol for letter in result.letters if letter.degenerate]
    print(f"  RFM               {len(degenerate)} of 3 dimensions degenerate ({', '.join(degenerate)}); "
          f"F~tenure correlation {result.frequency_tenure_correlation:.4f}")
    print(f"  profitable cells  {len(result.profitable_segments)} of {len(result.segments)} — "
          f"{sum(len(s) for s in result.profitable_segments):,} customers worth contacting")
    print(f"  stability         {migration.share(migration.cell_changed):.1%} changed cell in "
          f"{migration.months_apart} months "
          f"(risk {migration.share(migration.risk_band_changed):.1%}, "
          f"value {migration.share(migration.value_band_changed):.1%}); "
          f"segment sizes moved {migration.size_drift:.1%}")
    for row in result.deliverability:
        print(f"  reach             {row.segment:18s} {row.reach:>5.0%} of {row.members:,} "
              f"({row.blocked_by_eligibility:,} ineligible, {row.blocked_by_policy:,} out of policy)")
    print(f"  decision test     ranking {decision.by_expected_value.realised_profit:,.0f} vs "
          f"playbook {decision.by_segment.realised_profit:,.0f} "
          f"({decision.profit_gap_share:.1%} gap, {decision.overlap:.1%} overlap)")
    causal = result.causal
    assert causal is not None
    print(f"  causal audit      {causal.total_outcomes_changed} outcomes changed base-wide, "
          f"{causal.readable_segments} of {len(causal.effects)} segments readable")
    print(f"\nWrote {len(written)} files to {out}/")


if __name__ == "__main__":
    main()
