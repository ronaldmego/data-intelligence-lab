#!/usr/bin/env python3
"""Generate the synthetic telco customer-intelligence dataset.

Reproducible: same seed -> byte-for-byte identical CSVs on any machine.

    uv run generate.py                      # defaults: 5000 customers, 24 months
    uv run generate.py --customers 2000 --seed 7 --out data/
    python generate.py --customers 300 --months 12   # stdlib only, no deps needed
"""

from __future__ import annotations

import argparse
from pathlib import Path

from telco import Config, generate, write_tables


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=Config.n_customers, help="population size")
    ap.add_argument("--months", type=int, default=Config.n_months, help="months of history before the cutoff")
    ap.add_argument("--seed", type=int, default=Config.seed, help="RNG seed (determinism)")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data", help="output directory")
    args = ap.parse_args()

    cfg = Config(seed=args.seed, n_customers=args.customers, n_months=args.months)
    tables = generate(cfg)
    counts = write_tables(tables, args.out)

    churn = tables["churn_labels"]
    churn_rate = sum(r["churned_next_90d"] for r in churn) / max(1, len(churn))
    print(f"Wrote {len(counts)} tables to {args.out}/ (seed={cfg.seed}, "
          f"{cfg.n_customers} customers, {cfg.n_months} months)")
    width = max(len(n) for n in counts)
    for name, n in counts.items():
        print(f"  {name:<{width}}  {n:>9,} rows")
    print(f"90-day churn base rate: {churn_rate:.1%}")


if __name__ == "__main__":
    main()
