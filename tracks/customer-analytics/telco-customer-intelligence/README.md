# Telco Customer Intelligence

Customer-analytics evidence on a single **synthetic, causal, reproducible**
telco dataset: one data model, feeding a season of cases — segmentation, churn,
next-best-offer, ARPU and campaign incrementality.

> **Maturity: `work in progress`.** The data model (below) is built, tested and
> reproducible. The five cases are being added on top of it, one at a time.
> Everything here is synthetic — no employer or customer data. See
> [`data-model/DATA_CARD.md`](data-model/DATA_CARD.md).

## Why this track

The public brand lists **Customer & Digital Analytics** as a pillar; this track
is its open reference implementation. The hard part in customer intelligence
isn't the algorithm — it's the *data model and the governance around the
decision*: churn without leakage, next-best-offer with consent and eligibility,
uplift that isn't confounded by who you targeted. So the foundation is a dataset
built to make those problems real.

## The foundation: [`data-model/`](data-model/)

A seeded generator emits 14 related tables with an explicit causal structure,
so the cases are demonstrable rather than circular. The churn label is emitted at
**two** observation cutoffs, which is what lets a case train on the past and
score the future instead of asserting that it did, and one table is an **answer
key** — each customer's outcome had the campaign never run — that exists to check
estimators and is fenced off from producing any. See
[`data-model/README.md`](data-model/README.md) for the schema, the causal design
and the no-leakage guarantee.

```bash
cd data-model && uv run generate.py    # reproducible CSVs, byte-for-byte by seed
```

Tested on every push (schema, referential integrity, no-leakage, causal signal).

## Cases

Each case produces a reproducible pipeline, a visible result, and a permanent
write-up — the reusable evidence. (Distribution posts/video are a separate,
downstream concern.)

| # | Case | The real problem it shows | Status |
|---|---|---|---|
| 01 | Actionable segmentation | segments carry behaviour, need, risk, eligible offer, consent and a suggested action — not just RFM clusters | planned |
| 02 | [Churn without leakage](02-churn-prediction/) | out-of-time split, calibration, explainable drivers, prioritisation by value — accuracy alone isn't success | **built** |
| 03 | Governed next-best-offer | propensity/uplift **and** eligibility, consent, exclusions, contact policy | planned |
| 04 | ARPU / value decomposition | where revenue per user comes from and moves | planned |
| 05 | [Campaign incrementality](05-campaign-incrementality/) | true uplift vs the confounded naive read, and whether the experiment was big enough to tell | **built** |

**[02 · Churn without leakage](02-churn-prediction/)** — trains at one cutoff and
scores six months later, then reruns the same model two dishonest ways to show
what each shortcut would have reported: a random split, and one feature derived
from the label (AUC 1.000, nothing errors). Finds that the ranking survives the
time gap but the *calibration* does not, and that re-sorting the same
probabilities by expected value instead of risk changes the contact list by more
than half and the profit by +66% at the same budget.

**[05 · Campaign incrementality](05-campaign-incrementality/)** — reads the
retention campaigns against the control group they held back, four ways: three
comparisons that were never randomised and disagree about even the *sign*, then
the one the control was bought for. Two identically designed campaigns report
"nothing" and "a large, significant save"; the data model's answer key shows both
are the same true effect plus a coin-flip imbalance larger than the effect
itself. Settles the save rate case 02 had to assume — measured 12.4%, interval
−4.0% to 28.9%, truth 11.1%, assumed 25% — and finds that the experiment as
designed cannot distinguish any of those from each other, or from zero.

### The two cases talk to each other

Case 02 declared a debt: its profit figures applied an *assumed* save rate,
because whether a contact **caused** a save is unknowable without a control
group. Case 05 measures it, re-prices case 02's contact list from its own scored
population, and reports what survives — the targeting decision does, the business
case does not. Case 05 also imports case 02's feature builder, logistic
regression and `Economics` rather than restating them, so the two cannot drift
apart silently.

Tracked in [`ronaldmego/site-ronaldmego#64`](https://github.com/ronaldmego/site-ronaldmego/issues/64).
