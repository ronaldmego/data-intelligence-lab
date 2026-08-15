"""Loading the campaign, and the two questions that decide everything after it.

**Who was randomised, and what were they randomised into?** Every estimate in
this case is a difference between two groups; if those groups were not formed by
a coin flip, no amount of modelling downstream recovers the answer.

The audience is therefore defined as *the people the campaign selected* —
including the ones it deliberately did not contact. That is the population the
experiment can speak about. Widening it to "everyone" compares the targeted to
the untargeted and measures the targeting; narrowing it by anything that
happened *after* the flip breaks the comparison the flip bought.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

# One data model, many cases — import it rather than duplicating a loader.
_DATA_MODEL = Path(__file__).resolve().parents[2] / "data-model"
if str(_DATA_MODEL) not in sys.path:
    sys.path.insert(0, str(_DATA_MODEL))

from fintech import Config, generate  # noqa: E402

Tables = dict[str, list[dict]]


def load_tables(cfg: Config | None = None, data_dir: str | Path | None = None) -> Tables:
    """Return the data model as ``{table_name: [row, ...]}``.

    Generated in memory from the seed by default, so the case runs on a fresh
    clone with no setup step. ``data_dir`` reads the CSVs instead; the two are
    equivalent, CSV values simply arrive as strings.
    """
    if data_dir is not None:
        return _read_csv_dir(Path(data_dir))
    return generate(cfg or Config())


def _read_csv_dir(path: Path) -> Tables:
    if not path.is_dir():
        raise FileNotFoundError(
            f"{path} does not exist. Generate it first:\n"
            f"  cd {_DATA_MODEL} && uv run generate.py"
        )
    tables: Tables = {}
    for csv_path in sorted(path.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as fh:
            tables[csv_path.stem] = list(csv.DictReader(fh))
    if not tables:
        raise FileNotFoundError(f"no CSV files in {path}")
    return tables


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    name: str
    channel: str
    objective: str
    offer_id: str
    month_index: int
    month: str        # ISO month the campaign ran
    prior_month: str  # the last month that is unambiguously pre-campaign

    @property
    def is_retention(self) -> bool:
        return self.objective == "retention"


def month_calendar(tables: Tables) -> list[str]:
    """Month index -> ISO month start, read off the data rather than re-derived.

    The campaigns table dates itself by ``month_index``; the fact tables date
    themselves by month. This is the join between them.
    """
    return sorted({r["period_month"] for r in tables["activity_monthly"]})


def load_campaigns(tables: Tables) -> list[Campaign]:
    calendar = month_calendar(tables)
    campaigns = []
    for row in tables["campaigns"]:
        idx = int(row["month_index"])
        campaigns.append(Campaign(
            campaign_id=row["campaign_id"],
            name=row["name"],
            channel=row["channel"],
            objective=row["objective"],
            offer_id=row["offer_id"],
            month_index=idx,
            month=calendar[min(idx, len(calendar) - 1)],
            prior_month=calendar[max(0, idx - 1)],
        ))
    return campaigns


def retention_responders(tables: Tables) -> set[str]:
    """Customers who accepted a retention offer — the mediator the effect runs through.

    Defined across *all* retention campaigns, not one, and that is deliberate.
    The treatment a customer actually received is "took a retention offer",
    whichever campaign delivered it. Measuring a single campaign's first stage
    against a single campaign's responses would understate how many of its
    control group were treated by the *other* campaign, and a first stage that
    is too large deflates the effect it is used to divide out.
    """
    retention = {c.campaign_id for c in load_campaigns(tables) if c.is_retention}
    return {
        r["customer_id"] for r in tables["campaign_exposures"]
        if r["campaign_id"] in retention and int(r["responded"]) == 1
    }


@dataclass(frozen=True)
class Audience:
    """One campaign's randomised audience, split by the coin flip."""

    campaign: Campaign
    cutoff: str                  # observation cutoff of the outcome
    exposed: list[str]
    control: list[str]
    treated: set[str]            # took a retention offer (any campaign)
    responded: set[str]          # responded to *this* campaign
    outcome: dict[str, int]      # customer_id -> churned in the 90 days after the cutoff

    def __len__(self) -> int:
        return len(self.exposed) + len(self.control)

    @property
    def members(self) -> list[str]:
        return [*self.exposed, *self.control]

    def outcomes(self, ids: list[str]) -> list[int]:
        return [self.outcome[c] for c in ids]

    def treated_flags(self, ids: list[str]) -> list[int]:
        return [1 if c in self.treated else 0 for c in ids]

    @property
    def control_churn(self) -> float:
        """What happens to this audience when it is left alone.

        The denominator for anything expressed as a *rate* of saves, and the
        only unbiased estimate of it that exists — which is the entire reason a
        control group is worth the revenue it costs.
        """
        return _mean(self.outcomes(self.control))


def _mean(values: list[int] | list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_audience(tables: Tables, campaign: Campaign, label_table: str = "churn_labels") -> Audience:
    """Split one campaign's audience into the two arms of its randomisation.

    ``exposed`` was contacted, ``control`` was selected by the same targeting
    rule and then held back. Both were chosen by the campaign; only the coin
    flip separates them, which is what makes the difference between them causal.
    """
    labels = tables[label_table]
    cutoff = labels[0]["observation_cutoff"]
    outcome = {r["customer_id"]: int(r["churned_next_90d"]) for r in labels}

    exposed, control, responded = [], [], set()
    for row in tables["campaign_exposures"]:
        if row["campaign_id"] != campaign.campaign_id:
            continue
        cid = row["customer_id"]
        if cid not in outcome:  # not scoreable at this cutoff
            continue
        if int(row["exposed"]) == 1:
            exposed.append(cid)
            if int(row["responded"]) == 1:
                responded.add(cid)
        else:
            control.append(cid)

    return Audience(
        campaign=campaign,
        cutoff=cutoff,
        exposed=exposed,
        control=control,
        treated=retention_responders(tables),
        responded=responded,
        outcome=outcome,
    )


def untargeted(tables: Tables, audiences: list[Audience], label_table: str = "churn_labels") -> list[str]:
    """Customers no retention campaign selected — the comparison group that is
    lying in wait in every campaign readout, and the one that answers a different
    question than the one being asked."""
    targeted = {c for a in audiences for c in a.members}
    return [r["customer_id"] for r in tables[label_table] if r["customer_id"] not in targeted]
