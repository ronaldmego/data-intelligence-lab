# Telco Customer Intelligence

Customer-analytics evidence on a single **synthetic, causal, reproducible**
telco dataset: one data model, feeding a season of cases — segmentation, churn,
next-best-offer, ARPU and campaign incrementality.

> **Maturity: `reference`.** The data model and all five cases are built, tested
> and reproducible; two consecutive runs of any case are byte-for-byte identical.
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

A seeded generator emits 15 related tables with an explicit causal structure,
so the cases are demonstrable rather than circular. The churn label is emitted at
**two** observation cutoffs, which is what lets a case train on the past and
score the future instead of asserting that it did; the **contact policy is a
table** rather than a constant in whichever script is scoring; and one table is
an **answer key** — each customer's outcome had the campaign never run — that
exists to check estimators and is fenced off from producing any. See
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
| 01 | [Actionable segmentation](01-segmentation/) | segments carry behaviour, need, risk, eligible offer, consent and a suggested action — not just RFM clusters | **built** |
| 02 | [Churn without leakage](02-churn-prediction/) | out-of-time split, calibration, explainable drivers, prioritisation by value — accuracy alone isn't success | **built** |
| 03 | [Governed next-best-offer](03-next-best-offer/) | propensity/uplift **and** eligibility, consent, exclusions, contact policy | **built** |
| 04 | [ARPU / value decomposition](04-arpu-value/) | where revenue per user comes from, and what the four defensible definitions of a customer's worth do to the same decision | **built** |
| 05 | [Campaign incrementality](05-campaign-incrementality/) | true uplift vs the confounded naive read, and whether the experiment was big enough to tell | **built** |

**[01 · Actionable segmentation](01-segmentation/)** — computes RFM as prescribed
and then measures it: on a subscription, recency has *no variance at all* (one
distinct value across the base — everybody was invoiced last month) and
frequency correlates with tenure at 1.0000, because it is tenure. Builds the
risk-by-value grid instead, finds three of nine cells worth a contact, and then
attacks it: 45% of the base changes cell in six months and almost all of that is
the risk axis (41.3% against 6.0% for value) while segment *sizes* move 2.3%, so
the dashboard is flat while half the people underneath have swapped places. Two
of its own plays turn out to be undeliverable by the catalogue rather than by
policy — one of them contradicts the definition of the cell it was written for.
Priced against the continuous ranking on the same budget, the grid loses 9.1%,
which is the useful result: rank to choose who, segment to choose what.

**[02 · Churn without leakage](02-churn-prediction/)** — trains at one cutoff and
scores six months later, then reruns the same model two dishonest ways to show
what each shortcut would have reported: a random split, and one feature derived
from the label (AUC 1.000, nothing errors). Finds that the ranking survives the
time gap but the *calibration* does not, and that re-sorting the same
probabilities by expected value instead of risk changes the contact list by more
than half and the profit by +66% at the same budget.

**[03 · Governed next-best-offer](03-next-best-offer/)** — decides who to contact
with which offer, subject to consent, eligibility, exclusions and a contact
policy that lives in the data model rather than in the scoring script. Finds that
the gates do not remove a random slice — the groups they take out churn at
anywhere from 11.7% to 24.4% against a base of 11.8% — and that the cool-off
window is the most selective rule in the policy, removing the customers who churn
at 24.4%, because they were contacted last quarter *for being* high risk. Governance costs 20% of the plan's expected value;
applying the same rules in the wrong order costs 1.8× that again and silently
sends 199 contacts against a capacity of 437. Against the answer key, a compliant
Q1 campaign would have saved 9 customers instead of 39 — and the loss is
**reach**, not response.

**[04 · ARPU / value decomposition](04-arpu-value/)** — takes apart the single
number every other case used for customer value. Finds that 98.03% of the
variance in what customers are billed is between tariffs, so *"do heavy users
generate more revenue?"* answers **+0.30** across the base and **−0.02** inside
any single plan — the aggregate is the plan mix, and nothing errors. Then the
part that changes a decision: case 02 credited every saved customer with twelve
months of margin, and the *number* barely mattered (any other constant keeps
95–98% of its target list) while its *flatness* mattered enormously. Reading each
customer's own churn probability as a hazard implies lives from 1.7 months up,
moves half the list, and makes `p` and `1/h` cancel — so the expected value of a
retention contact stops depending on churn risk and the list becomes 79% the same
as ranking by revenue with no model at all. Which reading is right turns on
whether a save *changes* a hazard or *postpones one draw* of it, and neither the
data nor the answer key contains that.

**[05 · Campaign incrementality](05-campaign-incrementality/)** — reads the
retention campaigns against the control group they held back, four ways: three
comparisons that were never randomised and disagree about even the *sign*, then
the one the control was bought for. Two identically designed campaigns report
"nothing" and "a large, significant save"; the data model's answer key shows both
are the same true effect plus a coin-flip imbalance larger than the effect
itself. Settles the save rate case 02 had to assume — measured 12.4%, interval
−4.0% to 28.9%, truth 11.1%, assumed 25% — and finds that the experiment as
designed cannot distinguish any of those from each other, or from zero.

### The cases talk to each other

Each case pays a debt the previous one wrote down, and imports its predecessors
rather than restating them, so they cannot drift apart silently.

- **02 → 05.** Case 02's profit figures applied an *assumed* save rate, because
  whether a contact **caused** a save is unknowable without a control group.
  Case 05 measures it, re-prices case 02's contact list from its own scored
  population, and reports what survives — the targeting decision does, the
  business case does not. It imports case 02's feature builder, logistic
  regression and `Economics`.
- **02 and 05 → 03.** Both took their audiences exactly as the campaign built
  them, enforcing neither consent nor eligibility. Case 03 confronts who was
  *allowed* to be contacted, prices its offers with the save rate case 05
  measured rather than the one case 02 assumed, and reads the answer key through
  case 05's quarantined module — so exactly one file in the track ever touches
  the counterfactual table.
- **02, 03 and 05 → 01.** Segmentation is built last on purpose: it consumes all
  three. Risk and the profit accounting come from case 02, the permission layer
  that decides whether a segment's action can be delivered comes from case 03,
  and the measured save rate and the fenced answer key come from case 05. It is
  also the case that judges the others' output rather than extending it — the
  grid is priced *against* case 02's ranking on the same budget, and loses.
- **01, 02 and 05 → 04.** Value is priced last because it needs the others to
  price. It imports case 02's churn model, feature builder and commercial
  constants — and a test asserts its revenue figure equals case 02's to the last
  decimal, so the two cannot drift into disagreeing about what a customer pays —
  prices with case 05's *measured* save rate, and audits case 01's value axis
  with case 01's own band machinery, finding that the axis case 01 called stable
  is a constant for six tariffs and a coin flip for the seventh. It also pays the
  last debt in the track, the one nobody had written down: every earlier case
  multiplied revenue by a flat twelve months, and this is where that stops being
  free. Its fence around the answer key is the strictest in the track and
  consists of never opening it — corrupt the table and not one number in the
  result moves — because the question it cannot settle lies past the end of the
  world the answer key describes.

Case 03 also extends the shared data model with the contact policy itself, which
is what lets a case report the cost of an individual rule instead of asserting
that governance is expensive. Cases 01 and 04 follow the same principle without
touching the schema: case 01's playbook — what to *do* with each segment — and
case 04's unit costs are CSVs in the case rather than dicts in the scoring
script, because both are decisions somebody else owns and both change without the
analysis changing. Case 04 makes the sharper version of the argument: a contact
rule that is wrong gets argued about by the people it blocks, while a marginal
cost that is wrong silently re-orders a customer list and the list looks
identical.

Tracked in [`ronaldmego/site-ronaldmego#64`](https://github.com/ronaldmego/site-ronaldmego/issues/64).
