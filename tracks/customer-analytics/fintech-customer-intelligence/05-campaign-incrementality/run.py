#!/usr/bin/env python3
"""Run the incrementality case end to end and write the report and charts.

    uv run run.py                      # defaults, writes to outputs/
    uv run run.py --customers 1000     # a smaller world, for a quick look
    uv run run.py --data-dir ../data-model/data   # read CSVs instead of generating
    python run.py                      # stdlib only — no dependencies to install

Takes about half a minute: it refits case 02's churn model so the save rate
measured here can be fed back through case 02's own targeting comparison,
rather than re-implementing it or quoting its published figures by hand.

Deterministic: the same seed produces the same report, byte for byte.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-model"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "02-churn-prediction"))

from churn import run_case as run_churn_case  # noqa: E402
from churn.economics import Economics  # noqa: E402
from incrementality import load_tables, run_case  # noqa: E402
from incrementality.charts import decomposition_chart, power_chart, readings_chart  # noqa: E402
from incrementality.report import render  # noqa: E402
from fintech import Config  # noqa: E402


def _power_curve(result, points: int = 80) -> tuple[list[int], list[float]]:
    """Power against the real effect, as the held-back group grows.

    Delegates to the case's own power model, so the curve, the marker on it and
    the required size printed beside it are guaranteed to be the same function.
    """
    top = max(result.required_control * 1.45, len(result.retention[0].audience.control) * 2)
    sizes = [max(20, round(top * i / points)) for i in range(1, points + 1)]
    return sizes, [result.power_at_control(n) for n in sizes]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=Config.n_customers)
    ap.add_argument("--months", type=int, default=Config.n_months)
    ap.add_argument("--seed", type=int, default=Config.seed)
    ap.add_argument("--data-dir", type=Path, default=None, help="read generated CSVs instead of generating")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "outputs")
    ap.add_argument("--save-rate", type=float, default=Economics.save_rate,
                    help="the assumption under test — case 02's planning figure")
    ap.add_argument("--skip-repricing", action="store_true",
                    help="skip refitting case 02's model (faster; drops one report section)")
    args = ap.parse_args()

    cfg = Config(seed=args.seed, n_customers=args.customers, n_months=args.months)
    tables = load_tables(cfg, data_dir=args.data_dir)
    economics = Economics(save_rate=args.save_rate)

    churn_result = None
    if not args.skip_repricing:
        print("Refitting case 02 so its targeting economics can be re-priced...")
        churn_result = run_churn_case(tables, economics=economics)

    print(f"Reading the retention campaigns against their held-out controls "
          f"({cfg.n_customers:,} customers, {cfg.n_months} months, seed {cfg.seed})...")
    result = run_case(tables, churn_result=churn_result, economics=economics)

    readings = [(e.name, e.value, e.ci_low, e.ci_high) for e in result.naive]
    readings.append(("Exposed vs held back (ITT)", result.pooled_itt.value,
                     result.pooled_itt.ci_low, result.pooled_itt.ci_high))
    sizes, power = _power_curve(result)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "report.md": render(result),
        "readings.svg": readings_chart(readings, result.true_delivered),
        "decomposition.svg": decomposition_chart(
            [r.decomposition for r in result.retention],
            {r.audience.campaign.campaign_id: r.audience.campaign.name for r in result.retention},
        ),
        "power.svg": power_chart(
            sizes, power,
            actual=len(result.retention[0].audience.control),
            actual_power=result.realised_power,
            required=result.required_control,
            effect=result.target_effect,
        ),
    }
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")

    pooled, save = result.pooled_itt, result.save_rate
    print()
    for r in result.retention:
        print(f"  {r.audience.campaign.campaign_id}  ITT {r.itt.value * 100:+.2f} pp "
              f"[{r.itt.ci_low * 100:+.2f}, {r.itt.ci_high * 100:+.2f}]  "
              f"{'significant' if r.itt.significant else 'not significant'}"
              f"   (really delivered {r.decomposition.delivered * 100:+.2f} pp)")
    print(f"\n  pooled ITT        {pooled.value * 100:+.2f} pp "
          f"[{pooled.ci_low * 100:+.2f}, {pooled.ci_high * 100:+.2f}]   "
          f"true {result.true_delivered * 100:+.2f} pp")
    print(f"  save rate         {save.value:.1%} [{save.ci_low:.1%}, {save.ci_high:.1%}]   "
          f"case 02 assumed {save.assumed:.0%}, truth is {save.true_value:.1%}")
    print(f"  power             {result.realised_power:.0%} against the real effect; "
          f"{result.required_control:,} per arm needed for 80%")
    print(f"\nWrote {len(written)} files to {out}/")


if __name__ == "__main__":
    main()
