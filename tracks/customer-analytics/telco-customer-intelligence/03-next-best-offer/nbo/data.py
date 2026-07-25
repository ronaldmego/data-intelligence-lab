"""Loading the shared model, and assembling the things a decision needs.

Three of these are worth naming, because each one is a place where a
next-best-offer engine quietly goes wrong before any model is fitted:

* **the plan ladder** — "upgrade to M" only means something relative to the plan
  the customer is on, and the shared ``plans`` table numbers tiers across
  families (a prepaid M and a postpaid S are both tier 2). Rank has to be taken
  *within* a family or a quarter of the base gets offered a downgrade;
* **the offer catalogue** — an offer carries an objective, a delivery channel and
  a cost, none of which live on the ``offers`` row. They are derived from the
  campaigns that used the offer, so the catalogue matches what the business
  actually ran rather than what a scoring script assumed;
* **the contact history** — who was contacted, when, on what. It is the input to
  every frequency rule, and it is reconstructed from exposures rather than
  assumed to exist.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# The data model lives two levels up. Import it rather than duplicating a
# loader: one data model, many cases, is the whole point of the track.
_DATA_MODEL = Path(__file__).resolve().parents[2] / "data-model"
if str(_DATA_MODEL) not in sys.path:
    sys.path.insert(0, str(_DATA_MODEL))

from telco import Config, generate  # noqa: E402

Tables = dict[str, list[dict]]

# Fallbacks for an offer no campaign has ever used. Stated here rather than
# buried in a conditional: an offer that has never run has no observed channel
# or objective, and guessing from its type is the least-bad option available.
_TYPE_OBJECTIVE = {"discount": "retention", "upgrade": "upsell", "data_bundle": "crosssell"}


def load_tables(cfg: Config | None = None, data_dir: str | Path | None = None) -> Tables:
    """Return the data model as ``{table_name: [row, ...]}``.

    By default the tables are generated **in memory** from the seed, so the case
    runs on a fresh clone with no setup step and no committed data. Pass
    ``data_dir`` to read CSVs written by ``data-model/generate.py`` instead; the
    two are equivalent, CSV values simply arrive as strings.
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


def _int(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))  # type: ignore[arg-type]


def _float(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)  # type: ignore[arg-type]


# --- the plan ladder --------------------------------------------------------


@dataclass(frozen=True)
class PlanLadder:
    """Plans ordered *within* their own family.

    The shared ``plans`` table carries a ``tier`` that is comparable across the
    whole catalogue, which is the right thing for pricing and the wrong thing
    for eligibility: prepaid M and postpaid S are both tier 2, so "is this an
    upgrade?" answered on ``tier`` alone moves a prepaid customer sideways into
    a different family. Rank is therefore taken inside a family, and the fee is
    carried alongside so the value of a move can be priced.
    """

    rank: dict[str, int]                     # plan_id -> 1-based rank in its family
    family: dict[str, str]                   # plan_id -> family
    fee: dict[str, float]                    # plan_id -> monthly fee
    by_family_rank: dict[tuple[str, int], str]  # (family, rank) -> plan_id

    @classmethod
    def build(cls, tables: Tables) -> PlanLadder:
        families: dict[str, list[dict]] = {}
        for row in tables["plans"]:
            families.setdefault(row["family"], []).append(row)

        rank, family, fee, by_family_rank = {}, {}, {}, {}
        for fam, plans in families.items():
            for position, plan in enumerate(sorted(plans, key=lambda p: _int(p["tier"])), start=1):
                plan_id = plan["plan_id"]
                rank[plan_id] = position
                family[plan_id] = fam
                fee[plan_id] = _float(plan["monthly_fee"])
                by_family_rank[(fam, position)] = plan_id
        return cls(rank=rank, family=family, fee=fee, by_family_rank=by_family_rank)

    def target_plan(self, plan_id: str, target_rank: int) -> str | None:
        """The plan an upgrade offer would move this customer to, if any."""
        return self.by_family_rank.get((self.family[plan_id], target_rank))


# --- the offer catalogue ----------------------------------------------------


@dataclass(frozen=True)
class Offer:
    """One offer, with everything needed to decide whether to make it."""

    offer_id: str
    name: str
    type: str                    # discount | data_bundle | upgrade
    value: float                 # discount share, or GB, depending on type
    eligible_family: str         # 'any' or a family name
    upgrade_to_rank: int | None  # target rank within the family, upgrades only
    objective: str               # retention | upsell | crosssell
    channel: str                 # how it is delivered
    has_history: bool            # has any campaign ever sent it?

    @property
    def is_retention(self) -> bool:
        return self.objective == "retention"


def load_offers(tables: Tables) -> list[Offer]:
    """The offer catalogue, enriched with how each offer is actually delivered.

    Objective and channel come from the campaigns that used the offer — the
    business's revealed behaviour — not from a mapping invented here. An offer
    no campaign has used falls back to the convention for its type, and that
    fallback is **flagged** (``has_history``) rather than left silent: an offer
    that has never run has no response evidence behind it, and pricing it
    anyway is how the least-known offer ends up winning the ranking.
    """
    used_by = {r["offer_id"]: r for r in tables["campaigns"]}
    type_channel = {
        next(o["type"] for o in tables["offers"] if o["offer_id"] == r["offer_id"]): r["channel"]
        for r in tables["campaigns"]
    }

    offers = []
    for row in tables["offers"]:
        campaign = used_by.get(row["offer_id"])
        objective = campaign["objective"] if campaign else _TYPE_OBJECTIVE.get(row["type"], "upsell")
        channel = campaign["channel"] if campaign else type_channel.get(row["type"], "email")
        rank = row.get("upgrade_to_rank", "")
        offers.append(Offer(
            offer_id=row["offer_id"],
            name=row["name"],
            type=row["type"],
            value=_float(row["value"]),
            eligible_family=row["eligible_family"],
            upgrade_to_rank=None if rank in ("", None) else _int(rank),
            objective=objective,
            channel=channel,
            has_history=campaign is not None,
        ))
    return offers


def priced_offers(offers: list[Offer]) -> list[Offer]:
    """The offers that can honestly be given an acceptance probability."""
    return [o for o in offers if o.has_history]


# --- the contact history ----------------------------------------------------


def month_calendar(tables: Tables) -> list[str]:
    """Month index -> ISO month start, read off the observed months.

    The campaigns table dates itself by ``month_index``. Rather than re-deriving
    the generator's calendar anchor (and coupling this case to it), the calendar
    is read from the data — the same approach case 02 takes.
    """
    return sorted({r["period_month"] for r in tables["usage_monthly"]})


@dataclass(frozen=True)
class Contact:
    customer_id: str
    campaign_id: str
    when: str      # ISO date of the campaign month
    channel: str
    objective: str


@dataclass(frozen=True)
class ContactHistory:
    """Every outbound contact that actually happened, per customer.

    Only *exposed* rows count. A customer held back in a control group was
    selected into the audience but never contacted, so they carry no frequency
    burden — treating them as contacted would suppress exactly the people whose
    whole purpose was to remain untouched.
    """

    by_customer: dict[str, list[Contact]]

    @classmethod
    def build(cls, tables: Tables) -> ContactHistory:
        calendar = month_calendar(tables)
        campaigns = {
            r["campaign_id"]: (
                calendar[min(_int(r["month_index"]), len(calendar) - 1)],
                r["channel"],
                r["objective"],
            )
            for r in tables["campaigns"]
        }

        by_customer: dict[str, list[Contact]] = {}
        for row in tables["campaign_exposures"]:
            if _int(row["exposed"]) != 1:
                continue
            when, channel, objective = campaigns[row["campaign_id"]]
            by_customer.setdefault(row["customer_id"], []).append(Contact(
                customer_id=row["customer_id"],
                campaign_id=row["campaign_id"],
                when=when,
                channel=channel,
                objective=objective,
            ))
        for contacts in by_customer.values():
            contacts.sort(key=lambda c: c.when)
        return cls(by_customer=by_customer)

    def for_customer(self, customer_id: str) -> list[Contact]:
        return self.by_customer.get(customer_id, [])

    def days_since_last(self, customer_id: str, as_of: str) -> int | None:
        """Days between the most recent contact on-or-before ``as_of`` and it."""
        previous = [c.when for c in self.for_customer(customer_id) if c.when <= as_of]
        if not previous:
            return None
        return (date.fromisoformat(as_of) - date.fromisoformat(max(previous))).days

    def count_within(self, customer_id: str, as_of: str, days: int) -> int:
        cutoff = date.fromisoformat(as_of)
        return sum(
            1 for c in self.for_customer(customer_id)
            if c.when <= as_of and (cutoff - date.fromisoformat(c.when)).days <= days
        )


# --- consent ----------------------------------------------------------------


def load_consent(tables: Tables) -> dict[str, dict[str, bool]]:
    """``customer_id -> {channel: opted_in}``."""
    consent: dict[str, dict[str, bool]] = {}
    for row in tables["consent"]:
        consent.setdefault(row["customer_id"], {})[row["channel"]] = _int(row["consent"]) == 1
    return consent


# --- the wave ---------------------------------------------------------------


@dataclass(frozen=True)
class Wave:
    """One decision point: who is in scope, when, and how many can be contacted.

    A wave is not the whole customer base. Customers who left during the earlier
    labelled window are gone — case 02 settled that population question and the
    same answer applies here, because an offer sent to someone who has already
    churned is not a next-best offer, it is a mailing error.

    The population is therefore taken *from case 02's scored population* rather
    than rebuilt: two definitions of "who is a customer" that agree today is a
    coincidence waiting to expire.
    """

    cutoff: str
    customer_ids: list[str]
    capacity: int
    excluded_already_churned: int

    def __len__(self) -> int:
        return len(self.customer_ids)


def build_wave(tables: Tables, cutoff: str, customer_ids: list[str],
               capacity_share: float = 0.10) -> Wave:
    return Wave(
        cutoff=cutoff,
        customer_ids=list(customer_ids),
        capacity=max(1, int(len(customer_ids) * capacity_share)),
        excluded_already_churned=len(tables["churn_labels"]) - len(customer_ids),
    )


def churn_labels(tables: Tables) -> dict[str, int]:
    """What actually happened in the 90 days after the final cutoff."""
    return {r["customer_id"]: _int(r["churned_next_90d"]) for r in tables["churn_labels"]}
