#!/usr/bin/env python3
"""Run the governed next-best-offer case and write the report and charts.

    uv run run.py                      # defaults, writes to outputs/
    uv run run.py --customers 1000     # a smaller world, for a quick look
    uv run run.py --data-dir ../data-model/data   # read CSVs instead of generating
    python run.py                      # stdlib only — no dependencies to install

Takes about half a minute: it refits case 02's churn model, because the risk
score is an input to every offer's value here and quoting case 02's published
numbers by hand would let the two drift apart.

Deterministic: the same seed produces the same report, byte for byte.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-model"))

from nbo import load_tables, run_case  # noqa: E402
from nbo.charts import GATES_TEXT_ES, cooloff_chart, gates_chart, plans_chart, reach_chart  # noqa: E402
from nbo.report import RULE_LABELS, RULE_LABELS_ES, render  # noqa: E402
from nbo.value import MEASURED_SAVE_RATE  # noqa: E402
from fintech import Config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=Config.n_customers)
    ap.add_argument("--months", type=int, default=Config.n_months)
    ap.add_argument("--seed", type=int, default=Config.seed)
    ap.add_argument("--data-dir", type=Path, default=None, help="read generated CSVs instead of generating")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "outputs")
    ap.add_argument("--capacity-share", type=float, default=0.10,
                    help="contacts available, as a share of the wave")
    ap.add_argument("--save-rate", type=float, default=MEASURED_SAVE_RATE,
                    help="the rate case 05 measured; case 02 assumed 0.25")
    args = ap.parse_args()

    cfg = Config(seed=args.seed, n_customers=args.customers, n_months=args.months)
    tables = load_tables(cfg, data_dir=args.data_dir)

    print("Refitting case 02's churn model — the risk score every offer is priced against...")
    result = run_case(tables, capacity_share=args.capacity_share, save_rate=args.save_rate)

    comparison = result.comparison
    assert comparison is not None
    base_rate = result.realised_churn_of(result.wave.customer_ids)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "report.md": render(result),
        "gates.svg": gates_chart(result.rule_costs, base_rate, RULE_LABELS),
        # Same figure, same numbers, Spanish furniture. It is the one chart of
        # the case that gets embedded in a Spanish-language page, and a figure
        # whose caption is in one language and whose labels are in another asks
        # the reader to trust what they cannot read.
        "gates.es.svg": gates_chart(result.rule_costs, base_rate, RULE_LABELS_ES, GATES_TEXT_ES),
        "plans.svg": plans_chart(
            steps=[("removed by\nthe rules", -comparison.governance_cost),
                   ("lost to filtering\nin the wrong order", -comparison.ordering_cost)],
            totals=[(plan.name.split(" (")[0], plan.expected_value, len(plan), plan.capacity)
                    for plan in (comparison.ungoverned, comparison.governed, comparison.suppressed)],
        ),
        "reach.svg": reach_chart(
            [a.reach for a in result.audits],
            {a.campaign_id: a.name for a in result.audits},
        ),
        "cooloff.svg": cooloff_chart(
            result.sensitivity,
            result.policy.value_of("min_days_since_last_contact", 0.0),
        ),
    }
    for name, content in written.items():
        (out / name).write_text(content, encoding="utf-8")

    print(f"\n  wave              {len(result.wave):,} customers, capacity {result.wave.capacity:,}, "
          f"{result.reachable:,} reachable under the policy")
    for plan in (comparison.ungoverned, comparison.governed, comparison.suppressed):
        print(f"  {plan.name:38s} {len(plan):>4,} contacts  EV {plan.expected_value:>9,.0f}  "
              f"churn {plan.realised_churn_rate(result.labels):.1%}")
    print(f"\n  governance costs  {comparison.governance_cost:,.0f}")
    print(f"  wrong order costs {comparison.ordering_cost:,.0f}  "
          f"({comparison.ordering_cost / comparison.governance_cost:.1f}x the rules), "
          f"leaving {comparison.unfilled_capacity:,} slots unfilled")
    for audit in result.audits:
        reach = audit.reach
        print(f"  {audit.campaign_id}  contacted {reach.exposed:,}, allowed {reach.permitted:,} "
              f"({reach.reach_retained:.0%})  saved {reach.saves_full} -> {reach.saves_permitted}")
    print(f"\nWrote {len(written)} files to {out}/")


if __name__ == "__main__":
    main()
