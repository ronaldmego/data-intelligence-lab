# 01 · Actionable segmentation

**The decision this serves:** the base has to be split into segments, and each
segment has to carry an action for next quarter. Who is in each one, what do we
do with them, and does any of it change what would have happened anyway?

The brief for this case was *not RFM clusters — every segment carries behaviour,
need, risk, an eligible offer, consent and a suggested action*. Building that
turned out to be the easy half. The other half is whether the result survives
four questions a segmentation is not usually asked.

```bash
uv run run.py          # generates the data, segments, writes outputs/
python run.py          # identical — standard library only, no dependencies
```

Full numbers, charts and reasoning: **[`outputs/report.md`](outputs/report.md)**.

## First: two thirds of RFM does not exist here

RFM is what a segmentation request usually means. Computed as prescribed, on the
fintech's own transaction table:

![What each dimension is worth](outputs/axes.svg)

| | Dimension | Distinct values | Largest single value covers | Churn gap, top vs bottom fifth |
|---|---|---:|---:|---|
| `R` | months since the most recent invoice | **1** | 100% | **no variation to read** |
| `F` | invoices issued | 23 | 71% | 1.8% |
| `M` | average amount billed | 4,178 | <1% | 2.3% |
| `R*` | months since the app was last opened | 23 | 81% | **7.2%** |

**Recency has no variance at all** — one distinct value across the entire base,
because every customer was invoiced last month, because that is what a billing
run does. **Frequency correlates with tenure at 1.0000**: not strongly related,
the *same variable*, since the invoice count is the number of months somebody
has been a customer.

The mechanism is a property of the business model, not of this dataset. RFM
reads a customer's decision to come back. A subscription has no such decision —
the company decides when to bill. Two of the three dimensions are measuring the
company's own schedule, and the third is ARPU.

Sorting a constant still produces five tidy quintiles with different churn rates
in them, entirely from the order the rows arrived in. Nothing errors. The repair
is not a better formula but a different *event*: recency rebuilt on app logins —
something the customer chooses to do — separates churn three times as well as
the best of the original three.

## The grid, and the cells that are worth a contact

![The grid](outputs/grid.svg)

Risk from case 02's model, value from the same monthly revenue that case prices,
each cut into thirds. **Three of the nine cells clear the cost of contacting
their average member** — 1,463 of 4,376 customers. The deliverable is mostly a
list of people *not* to contact, which is the part of a segmentation that
survives meeting a budget.

The cell that justifies two axes instead of one is **Let go**: the same modelled
risk as the rescue cells, and a negative expected value, because what it is
worth saving is less than what saving it costs. A risk model alone puts those
500 customers at the top of the list.

**Every segment profile in the report is measured, not written.** Each cell
reports the features on which it departs furthest from the base, in units of the
base's own spread. What comes back is the data model's own causal design —
unresolved escalations and falling usage in the high-risk cells, app logins in
the low-risk ones — recovered rather than asserted. Naming a cell *disengaged
high-value customers* because it sounds right is how a segmentation becomes a
story, and a story cannot be wrong.

## The finding: one axis is a photograph, the other is a film

![Migration between the cutoffs](outputs/drift.svg)

The data model labels two observation cutoffs six months apart, so the same rule
can be applied twice and the answer counted.

| | |
|---|---:|
| changed cell in six months | **45.0%** |
| … because their risk band moved | 41.3% |
| … because their value band moved | 6.0% |
| whose contact decision flipped | 25.7% |
| largest change in any segment's **size** | 2.3% |

ARPU is the product the customer is on: a commercial fact that moves when somebody
signs something. Risk is behaviour, which is what the model exists to detect
moving. Crossing them produces a grid with the refresh rate of its faster axis,
and a quarterly plan built on it is acting, for a quarter of the base, on a
contact decision that has since reversed.

**Meanwhile the report looks fine.** Re-cutting the axes at each refresh holds
every cell the same size by construction, so a segment-size dashboard is flat
while nearly half the people inside the segments have swapped places. No
aggregate view can show this.

That 45% is a *floor*, and the floor is checked rather than asserted: scoring
the earlier cutoff with the model fitted on it is in-sample and reports 40.2%.
The comfortable method understates the problem, which is the direction that
matters.

## Can the action be delivered?

![Deliverability](outputs/reach.svg)

Judged against case 03's permission layer — imported, not reimplemented — asked
per offer type rather than per customer:

| Segment | Action | Reachable | Refused by policy | Refused by the catalogue |
|---|---|---:|---:|---:|
| Rescue | send a discount | **54%** | 229 | 0 |
| Rescue (economy) | send a discount | 56% | 202 | 0 |
| Grow (limit) | send a limit increase | 47% | 269 | 0 |
| Reprice | send an upgrade | 23% | 160 | **230** |
| Grow | send an upgrade | 20% | 103 | **294** |

The contact policy leans against the cells that need it: measured on whether a
customer can receive *any* offer — the only version in which nine cells are
comparable, since a play's own reach also depends on its channel — the
lowest-risk third is reachable at 78.5% and the highest-risk third at 64.4%.
That is not a coincidence: arrears, an unresolved complaint and a recent contact
are simultaneously the rules that suppress a contact and the facts the risk
model reads as danger.

**What this case does *not* claim** is that reachability falls monotonically
with risk. An earlier draft said exactly that, a test contradicted it, and the
claim was withdrawn rather than the test: cell by cell the ordering breaks, at
5,000 customers and at 800. The direction of the gap between the extreme thirds
survives across seeds; its size does not — on a smaller world with less contact
history it shrinks to a couple of points. The mechanism is worth designing
around; the number is not worth quoting as a constant.

**Two of the plays are not a delivery problem — they are wrong**, and that one
*is* structural rather than lucky. Separating the two refusal families is the
only reason it is visible:

- **Grow** is told to offer the next product up, and 294 of its 494 customers are
  already on that product or better. The cell is *defined* as the highest-value
  third of the base, and the highest-value third is mechanically the customers
  at the top of the product ladder. The action contradicts the definition of the
  segment it was written for.
- **Reprice** wants to move a low-usage customer onto a plan that fits — a move
  *down* — and every offer of that type moves up. It got coded to the nearest
  available type. A play cannot be more executable than the catalogue it draws
  on.

Both are left in and reported rather than quietly fixed. Nothing errors when a
play does not apply: the campaign under-delivers, and the segmentation is not
suspected.

## Does the grid change what anyone does?

The same budget, spent twice on the same customers, priced with case 02's own
profit accounting:

| List | Contacts | Realised profit | Actual churn of those contacted |
|---|---:|---:|---:|
| ranked by expected value | 437 | **1,920** | 24.9% |
| chosen by the playbook | 437 | 1,746 | 21.1% |

The lists agree on 75.7% of their names and the ranking wins by 9.1% of the
profit at identical capacity — discretising a score into thirds throws away the
ordering inside each third, and the budget stops inside one of them.

**That is not an argument against segmenting.** Both methods were pointed at one
question — *who gets the next contact* — and a single number answers it better
than a grid, which should surprise nobody. What the ranking never produces is
everything else: no action for the 1,401 customers it does not reach, and no
opinion on what to send the ones it does.

So: **rank to choose who, segment to choose what.** Using the grid as the
selector costs 9.1% for nothing, because the ranking was already there.

## What it takes from the other cases

- **Case 02** supplies the churn model, its feature builder, the population
  definition and the `Economics` that price every cell — refitted here, so the
  risk behind a segment cannot drift from the case that published it.
- **Case 03** supplies the permission layer, so a play's deliverability is
  judged by the same rules that price an offer next door.
- **Case 05** supplies the measured save rate (12.4%, not the assumed 25%) and
  the quarantined module that reads the answer key. This case never opens
  `churn_potential_outcomes` itself.

It adds one thing to the shared model's *method* rather than its schema: the
playbook lives in [`playbook.csv`](playbook.csv), for the reason case 03 moved
the contact policy into a table. What to do with a segment is a marketing
decision that changes without the analysis changing, and a decision buried in
whichever script is scoring cannot be reviewed by the people who own it. A test
changes one row and asserts the output moves.

## Limitations

- **Equal thirds are a choice, not a finding.** A different cut moves every cell
  count. What does not move is the shape: two axes with different refresh rates,
  deliverability inversely related to risk, and a ranking that beats a grid at
  ranking.
- **One migration measurement, at one gap.** Six months is what the data model
  labels; a quarterly plan is the common case and is not observable here.
- **Value is current ARPU, not lifetime value** — undiscounted, with no
  expectation of what a customer grows into. That flatters the low-tenure,
  high-usage customers in the grow cells.
- **There is no per-segment causal read, and the report says so with the answer
  key open.** The campaign changed 52 outcomes base-wide; split nine ways that
  is 5.8 per segment and no segment reaches ten. Every ordering of those rows is
  decided by a handful of customers who sat near their own threshold. Case 05
  showed the pooled experiment could not distinguish 25% from 11% or from zero;
  slicing it further does not create evidence.

## Layout

```
01-segmentation/
├── run.py                  # CLI: segment, write outputs/
├── playbook.csv            # what to do with each cell — data, not code
├── segmentation/
│   ├── data.py             # the shared model, the risk axis, one snapshot per cutoff
│   ├── rfm.py              # the three letters, computed as prescribed and then measured
│   ├── grid.py             # cells, the playbook, and the measured profile of each cell
│   ├── stability.py        # migration between the cutoffs, in-sample and cross-fitted
│   ├── reach.py            # deliverability, through case 03's permission layer
│   ├── decision.py         # the grid against the continuous ranking, same budget
│   ├── audit.py            # the per-segment causal read, through case 05's answer key
│   ├── charts.py           # SVG, hand-written, deterministic, height fitted to content
│   ├── report.py           # the markdown in outputs/
│   └── pipeline.py         # the case end to end
└── outputs/                # committed, so the result is visible without running it
```

Tests live in [`../tests/test_segmentation_case.py`](../tests/test_segmentation_case.py).
Three carry their weight: one corrupts the answer key and asserts **every
decision is unmoved while the audit moves**; one rewrites a row of the playbook
and asserts the contact list changes, which is the only test a hardcoded
playbook would fail; and one asserts that a play whose action text says *"no
contact"* is not counted as contacting — the substring test that produced a real
defect here before the column was made explicit.
