# Telco customer-intelligence — data model

A **synthetic, causal, reproducible** dataset that the five customer-analytics
cases (segmentation, churn, next-best-offer, ARPU, incrementality) all read
from. One data model, many cases — not a fresh dataset per notebook.

Standard library only, no numpy/pandas: the generator stays auditable and CI can
validate it without installing anything. Output is plain CSV.

## Generate

```bash
# from this directory
uv run generate.py                       # defaults: 5000 customers, 24 months, seed 42
uv run generate.py --customers 2000 --seed 7 --out data/
python generate.py --customers 300 --months 12   # stdlib only — no deps required
```

Same seed → **byte-for-byte identical** CSVs on any machine. The `data/` output
is git-ignored; reproduce it from the generator rather than committing it.

## Why monthly, not daily

`#64` sketched `usage_daily`. This model aggregates usage, billing and digital
engagement to **customer × month**. Churn, ARPU and RFM are modelled at monthly
grain in practice; daily rows would multiply the dataset ~30× and bloat the CSVs
without adding analytical value. The grain is a deliberate modelling decision,
documented here rather than hidden.

## Tables

Reference dimensions are tiny and fixed; facts scale with the population.

| Table | Grain | Key | Notes |
|---|---|---|---|
| `plans` | one row per plan | `plan_id` | prepaid/postpaid, fee, data/voice caps, tier |
| `offers` | one row per offer | `offer_id` | discount / data_bundle / upgrade |
| `campaigns` | one row per campaign | `campaign_id` | objective (retention/upsell/crosssell) → `offer_id` |
| `customers` | one row per customer | `customer_id` | signup, region, channel, age band, current plan, tenure |
| `subscriptions` | one spell per customer | `subscription_id` | active at cutoff (churn is modelled as future) |
| `usage_monthly` | customer × month | (`customer_id`,`period_month`) | data_gb, voice, sms, active_days |
| `billing` | customer × month | `invoice_id` | billed/paid, paid_date, days_late, status (paid/late/failed) |
| `digital_monthly` | customer × month | (`customer_id`,`period_month`) | app_logins, self_service, occasional NPS |
| `support_interactions` | one ticket | `ticket_id` | reason, channel, escalated, resolved, csat |
| `consent` | customer × channel | (`customer_id`,`channel`) | opt-in per email/sms/push/call |
| `campaign_exposures` | customer × campaign | `exposure_id` | **exposed vs control**, responded |
| `churn_labels` | one row per customer | `customer_id` | `churned_next_90d`, `observation_cutoff`, `churn_date` |

## The causal structure (what makes the cases real)

The label is **generated from observable trajectories** plus unobserved
satisfaction and noise — not sprinkled at random. That is what lets a churn
model recover signal, never fit perfectly, and never leak:

- **usage decline** — a downward usage trend raises churn odds;
- **payment problems** — failed/late invoices raise churn odds;
- **unresolved escalations** — the strongest single driver;
- **weak digital engagement** — low app logins raise churn odds;
- **early life** — short-tenure customers churn more;
- **plan misfit** — paying for a plan that doesn't fit;
- **retention response** — a genuine responder to a retention campaign churns
  *less* (a real, negative uplift);
- **latent satisfaction + gaussian noise** — deliberately unobserved, so the
  achievable model performance is bounded (no leakage, no perfect fit).

**No leakage by construction:** every fact stops at the observation cutoff (the
last month of history); the churn outcome lives in the *next 90 days*. There is
no post-outcome fact to leak — features are strictly pre-cutoff. The test suite
enforces this.

**Incrementality has real confounding:** retention campaigns are *targeted at
high-risk customers* (selection bias), so a naive "responders churn less" read
is wrong — responders and the held-out **control** both sit above the base rate
because both were selected for risk. The control group is what lets the
incrementality case recover the true uplift instead of the confounded one.

Reference signals from the default run (seed 42, 5000 customers) — **re-derive,
don't quote**; they move with the seed:

- 90-day churn base rate ≈ 13%
- churn with an unresolved escalation ≈ 28% vs ≈ 10% without
- retention responders ≈ 20% vs held-out control ≈ 31% (both > base → confounding)

## Layout

```
data-model/
├── generate.py          # CLI entrypoint
├── telco/
│   ├── config.py        # seed, scale, base rates (every knob, documented)
│   ├── model.py         # the causal generator, table by table
│   └── writer.py        # dict-of-tables → CSV
├── README.md            # this file
└── DATA_CARD.md         # synthetic-data disclosure
```

Tests live one level up in `../tests/` and run on the standard library, so CI
validates schema, referential integrity, the no-leakage property and the
presence of causal signal on every push.
