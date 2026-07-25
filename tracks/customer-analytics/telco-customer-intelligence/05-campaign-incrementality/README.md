# 05 · Campaign incrementality

**The decision this serves:** the retention campaign reports that customers who
took the offer churned less. Should we spend more on it next quarter?

Not "did churn go down". That question is answerable from the campaign report and
the answer is always yes, because retention campaigns are aimed at people who
were already leaving and offers are accepted by the people most inclined to
accept them. This case is built around the two places incrementality work
actually fails: **comparisons that were never randomised**, and **a randomised
comparison too small to answer the question it was asked.**

```bash
uv run run.py          # generates the data, estimates, writes outputs/
python run.py          # identical — standard library only, no dependencies
```

Full numbers, charts and reasoning: **[`outputs/report.md`](outputs/report.md)**.

## What it does

Finds the control group the retention campaigns were run with, and reads the
same data four ways.

![Four readings](outputs/readings.svg)

| Reading | Estimate | What it measures |
|---|---:|---|
| Responders vs the whole base | **+5.34 pp** | Who was targeted |
| Responders vs the untargeted | **+8.94 pp** | Who was targeted, again |
| Responders vs non-responders in the same audience | **−8.73 pp** | Who chose to respond |
| **Exposed vs held back (ITT)** | **−3.88 pp** | **What running the campaign did** |

The first two say the campaign made things *worse*. The third — which looks like
it controlled for something, because it compares inside the audience — flips the
sign and doubles the magnitude. Only the last compares two groups separated by
nothing but a coin flip.

## The part that makes this more than a lecture on confounding

The data model records what every customer would have done **had the campaign
never run**, from the same random draw. So an identity is available that no real
readout has:

> observed difference = the effect the campaign delivered + the imbalance the coin flip handed over

![Decomposition](outputs/decomposition.svg)

Two campaigns, same design, same population:

| Campaign | Observed | Really delivered | Handed over by the flip |
|---|---:|---:|---:|
| Q1 Retention Save | +0.02 pp | −4.75 pp | +4.77 pp |
| Q3 Retention Save | −8.08 pp | −2.84 pp | −5.25 pp |

**Neither headline was about the campaign.** The first worked and reported
nothing, because the flip handed its contacted group almost exactly enough extra
churn to cancel it. The second worked *less* and reported a large, statistically
significant save. A team holding only the second would fund a programme; a team
holding only the first would cancel one. Both estimates are unbiased and both
intervals cover their own true value — unbiased just does not mean right on the
day.

Pooled, the estimate lands on **−3.88 pp against a truth of −3.83 pp** and its
interval still runs from −9.02 to +1.26. The arithmetic was never the problem.

## Why so little was visible

Of 5,000 customers, the campaign changed the outcome of **52**. An offer only
matters to someone whose churn sat between the treated and untreated
probabilities; everyone else was staying, or leaving, either way.

![Power](outputs/power.svg)

Each campaign had roughly an **18% chance** of detecting the effect that was
there — so about four in five come back empty. Pooling both reached 31%, still
short of the conventional 80% bar and still an interval covering zero. Getting
there needs about **817 customers held back per campaign** against the 218
actually held back.

## What it closes

Case 02 priced its contact list with an assumed **save rate of 25%**, flagged it
as an assumption no observational data could settle, and pointed here. Measured:

| | |
|---|---:|
| Measured save rate | **12.4%** |
| 95% interval | −4.0% to 28.9% |
| Assumed by case 02 | 25.0% |
| True value | 11.1% |

Two things are true, and only one is knowable without the answer key. The
experiment **cannot reject** case 02's assumption — 25% sits inside the interval,
which also spans *the campaign does nothing*. And case 02's number was **wrong by
a factor of 2.3**.

Re-pricing case 02's contact list at the measured rate leaves its *decision*
intact and its *business case* halved: the ranking never depended on the save
rate (a positive constant common to every customer's expected value cannot
reorder anybody), but the level does, and with it how many people are worth
calling — optimal capacity drops from 2,188 contacts to 1,312.

## Three traps it demonstrates rather than describes

- **The weak instrument.** Rescaling the ITT by the first stage gives the effect
  on those who accepted, and is legitimate here because a held-back customer
  cannot accept an offer they were never sent. Applied to the upsell campaign —
  which has no first stage on retention offers — the same arithmetic reports a
  change in churn larger than churn itself. Nothing errors, and it is nonsense in
  the direction that flatters the campaign.
- **The balance check that blesses the wrong result.** Comparing the arms on
  pre-campaign covariates is the only diagnostic available without the answer
  key. It flags the campaign whose flip cancelled its effect, and passes the one
  whose headline overstates the truth by 2.8×. It detects broken randomisation,
  not insufficient randomisation.
- **A population filter that is right upstream and wrong here.** Case 02
  correctly excludes customers who churned in the earlier window. Carrying that
  filter into this analysis moves the headline by up to 5.47 pp — more than the
  effect being measured — because the campaign changed who lands in the filter.

## Limitations

- **The outcome is measured long after the campaign**, because the data model
  carries one labelled window. The generator's effect is permanent so nothing
  decays here; in a real operation it would.
- **The two pooled audiences share 337 customers**, so the estimates are not
  independent and the pooled interval is slightly narrow. It does not change the
  verdict; a clustered analysis would be the correct treatment.
- **One draw of one world.** Every claim about luck rests on the two
  randomisations that happened. Many seeds would turn "the imbalance exceeded the
  effect" into a distribution.
- **Consent and eligibility are not enforced.** Audiences are taken as the
  campaign built them — case 03 has to confront who was *allowed* to be
  contacted.

## Layout

```
05-campaign-incrementality/
├── run.py                  # CLI: estimate, write outputs/
├── incrementality/
│   ├── data.py             # the audience, the arms, and who counts as treated
│   ├── estimators.py       # ITT, first stage, Wald, pooling, power — all with intervals
│   ├── balance.py          # pre-campaign covariates, judged against their own noise
│   ├── truth.py            # the answer key, quarantined from every estimator
│   ├── heterogeneity.py    # effect by risk stratum, and whether it is resolvable
│   ├── economics.py        # the translation back into case 02's save rate
│   ├── charts.py           # SVG, hand-written, deterministic
│   ├── report.py           # the markdown in outputs/
│   └── pipeline.py         # the case end to end
└── outputs/                # committed, so the result is visible without running it
```

Tests live in [`../tests/test_incrementality_case.py`](../tests/test_incrementality_case.py).
The one that matters corrupts the answer key and asserts that **no estimate
moves** — a case that peeked would report better numbers, so no assertion on a
result could catch it.

**Why no pandas, scipy or an uplift library.** Every estimate here is a
difference between two proportions; the hard part was never the arithmetic, it
was deciding which two. Writing it out keeps each number in the report auditable,
keeps the result reproducible years from now, and lets CI run the whole thing
without installing anything. This case reuses case 02's feature builder, its
logistic regression and its `Economics` — one data model, one set of tools, many
cases.
