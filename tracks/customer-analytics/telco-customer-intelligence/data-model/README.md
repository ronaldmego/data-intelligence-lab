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
| `offers` | one row per offer | `offer_id` | discount / data_bundle / upgrade; `eligible_family` and `upgrade_to_rank` say who it applies to |
| `campaigns` | one row per campaign | `campaign_id` | objective (retention/upsell/crosssell) → `offer_id` |
| `contact_policy` | one row per rule | `policy_id` | consent, cool-off, frequency cap, arrears, open complaints — see below |
| `customers` | one row per customer | `customer_id` | signup, region, channel, age band, current plan, tenure |
| `subscriptions` | one spell per customer | `subscription_id` | active at cutoff (churn is modelled as future) |
| `usage_monthly` | customer × month | (`customer_id`,`period_month`) | data_gb, voice, sms, active_days |
| `billing` | customer × month | `invoice_id` | billed/paid, paid_date, days_late, status (paid/late/failed) |
| `digital_monthly` | customer × month | (`customer_id`,`period_month`) | app_logins, self_service, occasional NPS |
| `support_interactions` | one ticket | `ticket_id` | reason, channel, escalated, resolved, csat |
| `consent` | customer × channel | (`customer_id`,`channel`) | opt-in per email/sms/push/call |
| `campaign_exposures` | customer × campaign | `exposure_id` | **exposed vs control**, responded |
| `churn_labels` | one row per customer | `customer_id` | `churned_next_90d`, `observation_cutoff`, `churn_date` |
| `churn_labels_prior` | one row per customer alive at the earlier cutoff | `customer_id` | same label, observed `prior_cutoff_offset` months earlier — see below |
| `churn_potential_outcomes` | customer × cutoff | (`customer_id`,`observation_cutoff`) | **the answer key** — `churned_next_90d_if_no_campaign`, `treated`. See below |

## The rules live in the data, not in the scoring script

`contact_policy` holds the rules that decide who may be contacted at all — a
consent requirement per channel, a cool-off window, a yearly frequency cap, an
arrears rule and an open-complaint rule — each as a row with an identifier, a
scope, a parameter, a unit and a rationale. `offers` carries the two eligibility
facts alongside them: which plan family an offer is sold to, and, for upgrades,
`upgrade_to_rank` — the position *within the customer's own family* of the plan
the offer moves them to, so "is this actually an upgrade?" has one answer rather
than one per consumer.

This is a modelling opinion and worth stating. A policy that lives in whichever
script is scoring today is not a policy, it is a preference: it cannot be audited
without reading code, it drifts the moment a second team runs a campaign, and
nobody can answer *"what were we allowed to do last quarter?"* six months later.
As data, it is versioned, diffable, and a case can report the cost of each
individual rule — which is the only way the trade-off gets discussed instead of
assumed.

**The campaigns in this dataset were not generated under these rules**, on
purpose. A world where the policy had already been enforced could not show what
enforcing it costs; case 03 measures exactly that gap.

`contact_policy` is a new reference table and `upgrade_to_rank` is a new column
on `offers`; neither consumes randomness, so adding them left **thirteen of the
fourteen pre-existing tables byte-for-byte identical** (verified by sha256
against a previous seed-42 run). The fourteenth is `offers` itself, which gained
that one declarative column.

## The answer key, and the fence around it

`churn_potential_outcomes` records what each customer would have done **had the
retention campaign never run**. Subtracting it from `churn_labels` gives the
individual causal effect — the quantity that is permanently unobservable in
reality, because a customer is either contacted or not and never both.

It is computed from the *same uniform draw* as the observed label, with the
retention term added back to the log-odds. That matters more than it sounds:
re-running the generator with `w_retention_response = 0` would **not** produce
this. The first customer whose outcome flips stops drawing a churn date, the RNG
stream desynchronises, and every customer after them differs for reasons that
have nothing to do with the campaign. Sharing the draw also means the table
consumes no randomness of its own, so the fourteen tables above are byte-for-byte
identical to a run without it.

**No real dataset has this column.** It exists so an estimator can be checked
against the answer — which is the one thing a synthetic world is uniquely good
for — and it is ground truth, never an input. A case that reads it to *produce*
an estimate has stopped measuring anything, and the failure would look like an
unusually good result rather than an error. Case 05 quarantines it in a single
module and [tests the fence](../tests/test_incrementality_case.py) by corrupting
the table and asserting that no estimate moves.

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

## Two cutoffs, so temporal validation can be *demonstrated*

The label is emitted at **two** observation cutoffs: the final month of history
(`churn_labels`) and one `prior_cutoff_offset` months earlier
(`churn_labels_prior`, default 6 → cutoffs 6 months apart, outcome windows
disjoint because the label window is ~3 months).

The second cutoff is not decoration. With a single cutoff, "temporal validation"
can only be *asserted*: the train/test split is across customers, and the model
is never asked to generalise **forward in time**, which is the only thing that
matters once it is deployed. With two, a case can train on the world as it
looked at the prior cutoff and score the final cutoff — an honest out-of-time
backtest, where degradation and calibration drift show up instead of hiding.

The earlier label is generated by re-deriving the risk proxy from **only the
events that had happened by that cutoff** (payment problems, unresolved
escalations, campaign responses are all time-stamped internally); latent traits
are time-invariant. It is emitted *after* every other table so the generator's
random stream is untouched — the twelve tables above are byte-for-byte identical
to a run without it.

Two consequences worth knowing before you use it:

- Customers who signed up **after** the prior cutoff are absent from
  `churn_labels_prior` (they did not exist to be scored) — so it has slightly
  fewer rows than `churn_labels`.
- A customer labelled churned at the prior cutoff **still appears** in
  `churn_labels`. In reality they would have left. This is a deliberate
  simplification: the population at the final cutoff is the *case's* job to
  define, and doing so is part of the exercise. See `DATA_CARD.md`.

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
