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

A seeded generator emits ~12 related tables with an explicit causal structure,
so the cases are demonstrable rather than circular. See
[`data-model/README.md`](data-model/README.md) for the schema, the causal design
and the no-leakage guarantee.

```bash
cd data-model && uv run generate.py    # reproducible CSVs, byte-for-byte by seed
```

Tested on every push (schema, referential integrity, no-leakage, causal signal).

## Cases (roadmap)

Each case will produce a reproducible notebook/pipeline, a visible result, and a
permanent write-up — the reusable evidence. (Distribution posts/video are a
separate, downstream concern.)

| # | Case | The real problem it shows |
|---|---|---|
| 01 | Actionable segmentation | segments carry behaviour, need, risk, eligible offer, consent and a suggested action — not just RFM clusters |
| 02 | Churn without leakage | temporal split, calibration, explainable drivers, prioritisation by value — accuracy alone isn't success |
| 03 | Governed next-best-offer | propensity/uplift **and** eligibility, consent, exclusions, contact policy |
| 04 | ARPU / value decomposition | where revenue per user comes from and moves |
| 05 | Campaign incrementality | true uplift vs the confounded naive read (targeting was not random) |

Tracked in [`ronaldmego/site-ronaldmego#64`](https://github.com/ronaldmego/site-ronaldmego/issues/64).
