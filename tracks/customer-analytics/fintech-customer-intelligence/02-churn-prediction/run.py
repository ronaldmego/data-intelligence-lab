#!/usr/bin/env python3
"""Run the churn case end to end and write the report and charts.

    uv run run.py                      # defaults, writes to outputs/
    uv run run.py --customers 1000     # a smaller world, for a quick look
    uv run run.py --data-dir ../data-model/data   # read CSVs instead of generating
    python run.py                      # stdlib only — no dependencies to install

Deterministic: the same seed produces the same report, byte for byte.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-model"))

from churn import load_tables, run_case  # noqa: E402
from churn.charts import calibration_chart, gains_chart, profit_chart  # noqa: E402
from churn.economics import Economics  # noqa: E402
from churn.report import render  # noqa: E402
from fintech import Config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=Config.n_customers)
    ap.add_argument("--months", type=int, default=Config.n_months)
    ap.add_argument("--seed", type=int, default=Config.seed)
    ap.add_argument("--data-dir", type=Path, default=None, help="read generated CSVs instead of generating")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "outputs")
    ap.add_argument("--l2", type=float, default=1.0, help="ridge penalty on the standardised slopes")
    ap.add_argument("--capacity", type=float, default=0.10, help="contact budget, as a share of the base")
    ap.add_argument("--save-rate", type=float, default=Economics.save_rate)
    ap.add_argument("--contact-cost", type=float, default=Economics.contact_cost)
    args = ap.parse_args()

    cfg = Config(seed=args.seed, n_customers=args.customers, n_months=args.months)
    tables = load_tables(cfg, data_dir=args.data_dir)
    economics = Economics(save_rate=args.save_rate, contact_cost=args.contact_cost)

    print(f"Training at the earlier cutoff, scoring the final one "
          f"({cfg.n_customers:,} customers, {cfg.n_months} months, seed {cfg.seed})...")
    result = run_case(tables, economics=economics, l2=args.l2, capacity_share=args.capacity)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "report.md": render(result),
        "calibration.svg": calibration_chart(result.out_of_time.reliability, result.out_of_time.base_rate),
        "gains.svg": gains_chart(result.out_of_time.deciles, result.out_of_time.n, result.out_of_time.n_events),
        "profit.svg": profit_chart(result.comparison.by_risk, result.comparison.by_value,
                                   result.comparison.capacity),
    }
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")

    oot, comparison = result.out_of_time, result.comparison
    print(f"\n  train {result.train.cutoff}  n={len(result.train):,}  churn={result.train.base_rate:.1%}")
    print(f"  score {result.test.cutoff}  n={len(result.test):,}  churn={result.test.base_rate:.1%}")
    print(f"\n  out-of-time AUC   {oot.auc:.3f}   (in-time split would say {result.in_time.auc:.3f}, "
          f"with a leaked feature {result.with_leakage.auc:.3f})")
    print(f"  top-decile lift   {oot.top_decile_lift:.2f}x, capturing {oot.top_decile_capture:.1%} of churn")
    print(f"  calibration       slope {oot.calibration_slope:.2f}, ECE {oot.expected_calibration_error:.4f}")
    print(f"  targeting         {comparison.uplift_at_capacity:+,.0f} profit from ranking by expected value "
          f"instead of risk, at {comparison.capacity:,} contacts")
    print(f"\nWrote {len(written)} files to {out}/")


if __name__ == "__main__":
    main()
