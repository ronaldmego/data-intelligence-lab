"""The grid: risk against value, and the playbook that turns a cell into an action.

Two axes, chosen because they answer the two questions an action needs and no
single score answers both: *is this customer leaving?* and *does it matter if
they do?* Risk alone sends the retention budget to customers worth less than the
offer; value alone sends it to customers who were never going anywhere.

**The playbook lives in a CSV, not in this module.** Case 03 made the argument
for the contact policy and it applies here with more force: what to *do* with a
segment is a marketing decision, it changes without the analysis changing, and a
decision that lives inside whichever script is scoring cannot be reviewed by the
people who own it. As data it is diffable, and a test can change one row and
assert the output moves.

The segment *profile* is the other half, and it goes the other way: it is
measured, never written down. Naming a cell "disengaged high-value customers"
because the name sounds right is how a segmentation becomes a story. Here each
cell reports the features on which it actually departs from the base, in units
of the base's own spread, and the label is whatever those come out as.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

from .data import FEATURE_NAMES, Snapshot

PLAYBOOK = Path(__file__).resolve().parent.parent / "playbook.csv"

BAND_NAMES = ("low", "mid", "high")

# Feature names as a reader would say them. Only the ones a profile is allowed
# to report — internal encodings ("is_prepaid") describe the account, not
# behaviour, and a profile built from them reads as a finding when it is a
# tautology.
BEHAVIOUR_LABELS: dict[str, str] = {
    "usage_trend": "usage trend",
    "usage_gb_last3": "data used",
    "active_days_last3": "active days",
    "payment_problem_rate": "payment problems",
    "failed_invoices_last6": "failed invoices",
    "avg_days_late_last6": "days late",
    "tickets_last6": "support tickets",
    "unresolved_escalations": "unresolved escalations",
    "app_logins_last3": "app logins",
    "self_service_last3": "self-service actions",
    "tenure_months": "tenure",
    "data_headroom": "unused data allowance",
    "retention_offer_taken": "took a retention offer",
}


@dataclass(frozen=True)
class Play:
    """One row of the playbook: what this cell is for.

    ``contacts`` is a declared column rather than something inferred from the
    action text. Inferring it is tempting and wrong — a play whose action reads
    *"no contact this wave"* contains the word, and a keyword test scores it as
    an outbound contact. Whether a cell gets contacted is the single most
    consequential thing in the file; it is not left to a substring.
    """

    risk_band: int
    value_band: int
    segment: str
    need: str
    contacts: bool
    action: str
    offer_type: str

    @property
    def has_offer(self) -> bool:
        """Is there something in the catalogue to send?"""
        return self.offer_type != "none"


def load_playbook(path: Path | str = PLAYBOOK) -> dict[tuple[int, int], Play]:
    """Read the playbook from CSV, keyed by grid cell."""
    plays: dict[tuple[int, int], Play] = {}
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (int(row["risk_band"]), int(row["value_band"]))
            plays[key] = Play(
                risk_band=key[0],
                value_band=key[1],
                segment=row["segment"],
                need=row["need"],
                contacts=row["contact"].strip().lower() in ("yes", "true", "1"),
                action=row["action"],
                offer_type=row["offer_type"],
            )
    return plays


# --- cutting the axes -------------------------------------------------------


def quantile_cuts(values: list[float], bands: int = 3) -> list[float]:
    """The ``bands - 1`` thresholds that split ``values`` into equal shares.

    Quantiles rather than round numbers, deliberately: a threshold like "risk
    above 20%" is a business rule that has to be argued for and re-argued when
    the base rate moves, and this case is not about defending one. Equal thirds
    are arbitrary in an obvious way, which is the honest kind.
    """
    ordered = sorted(values)
    return [ordered[int(len(ordered) * i / bands)] for i in range(1, bands)]


def band_of(value: float, cuts: list[float]) -> int:
    return sum(1 for cut in cuts if value >= cut)


@dataclass(frozen=True)
class Cuts:
    """Where the two axes were cut, kept so a later snapshot can reuse them."""

    risk: list[float]
    value: list[float]

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot, bands: int = 3) -> Cuts:
        return cls(risk=quantile_cuts(snapshot.risk, bands),
                   value=quantile_cuts(snapshot.value, bands))

    def cell_of(self, risk: float, value: float) -> tuple[int, int]:
        return band_of(risk, self.risk), band_of(value, self.value)


# --- the cells --------------------------------------------------------------


@dataclass(frozen=True)
class Trait:
    """One way a segment departs from the base, in the base's own units."""

    feature: str
    label: str
    z: float           # (cell mean - base mean) / base sd

    def phrase(self) -> str:
        direction = "higher" if self.z > 0 else "lower"
        return f"{self.label} {abs(self.z):.1f} sd {direction}"


@dataclass(frozen=True)
class Segment:
    """One cell of the grid: who is in it, what it is worth, what to do."""

    play: Play
    members: list[int]                 # indices into the snapshot
    mean_risk: float
    mean_value: float
    realised_churn: float              # what actually happened — evaluation only
    expected_value_per_customer: float
    traits: list[Trait]

    @property
    def key(self) -> tuple[int, int]:
        return self.play.risk_band, self.play.value_band

    @property
    def name(self) -> str:
        return self.play.segment

    def __len__(self) -> int:
        return len(self.members)

    @property
    def worth_contacting(self) -> bool:
        """Does contacting the average member of this cell make money?"""
        return self.expected_value_per_customer > 0


def _traits(snapshot: Snapshot, members: list[int], base_mean: list[float],
            base_sd: list[float], top: int = 3) -> list[Trait]:
    """The features on which this cell is furthest from the base."""
    scored: list[Trait] = []
    for column, name in enumerate(FEATURE_NAMES):
        label = BEHAVIOUR_LABELS.get(name)
        if label is None or base_sd[column] == 0:
            continue
        cell_mean = mean(snapshot.features[i][column] for i in members)
        scored.append(Trait(feature=name, label=label,
                            z=(cell_mean - base_mean[column]) / base_sd[column]))
    return sorted(scored, key=lambda t: -abs(t.z))[:top]


def build_segments(
    snapshot: Snapshot,
    cuts: Cuts,
    playbook: dict[tuple[int, int], Play],
    economics,
) -> list[Segment]:
    """Assign every customer to a cell and measure what that cell is.

    Returned in reading order — riskiest first, and within a risk band, most
    valuable first — because that is the order the actions are decided in.
    """
    members: dict[tuple[int, int], list[int]] = {key: [] for key in playbook}
    for i in range(len(snapshot)):
        members.setdefault(cuts.cell_of(snapshot.risk[i], snapshot.value[i]), []).append(i)

    columns = range(len(FEATURE_NAMES))
    base_mean = [mean(row[c] for row in snapshot.features) for c in columns]
    base_sd = [pstdev(row[c] for row in snapshot.features) for c in columns]

    segments = []
    for key, rows in members.items():
        if not rows or key not in playbook:
            continue
        segments.append(Segment(
            play=playbook[key],
            members=rows,
            mean_risk=mean(snapshot.risk[i] for i in rows),
            mean_value=mean(snapshot.value[i] for i in rows),
            realised_churn=mean(snapshot.labels[i] for i in rows),
            expected_value_per_customer=mean(
                economics.expected_value(snapshot.risk[i], snapshot.value[i]) for i in rows
            ),
            traits=_traits(snapshot, rows, base_mean, base_sd),
        ))
    return sorted(segments, key=lambda s: (-s.play.risk_band, -s.play.value_band))
