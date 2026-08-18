"""Loading the shared data model, and deciding **who is even scoreable**.

The population question comes before the model and is answered wrong more often
than the model is. A churn model scored on customers who had already left is
measuring nothing; one scored on customers who could not yet churn is measuring
the calendar.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

# The data model lives next door. Import it rather than duplicating a loader:
# one data model, many cases, is the whole point of the track.
_DATA_MODEL = Path(__file__).resolve().parents[2] / "data-model"
if str(_DATA_MODEL) not in sys.path:
    sys.path.insert(0, str(_DATA_MODEL))

from fintech import Config, generate  # noqa: E402

Tables = dict[str, list[dict]]


def load_tables(cfg: Config | None = None, data_dir: str | Path | None = None) -> Tables:
    """Return the data model as ``{table_name: [row, ...]}``.

    By default the tables are generated **in memory** from the seed, so the case
    runs on a fresh clone with no setup step and no committed data. Pass
    ``data_dir`` to read the CSVs written by ``data-model/generate.py`` instead
    — the two are equivalent; CSV values simply arrive as strings, which the
    feature builder coerces either way.
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
class Population:
    """The customers a model may legitimately be scored on at one cutoff."""

    name: str
    cutoff: str  # ISO date of the observation cutoff
    customer_ids: list[str]
    labels: dict[str, int]  # customer_id -> churned in the next 90 days
    excluded_already_churned: int = 0

    @property
    def base_rate(self) -> float:
        return sum(self.labels.values()) / max(1, len(self.customer_ids))

    def __len__(self) -> int:
        return len(self.customer_ids)


def scoreable_population(tables: Tables, label_table: str, exclude_churned_in: str | None = None) -> Population:
    """Build the population for one cutoff.

    ``exclude_churned_in`` names an *earlier* label table whose churners must be
    dropped: they left during that earlier window, so at this cutoff they are
    not customers to be saved — they are history. The synthetic data model does
    not remove them (its data card says so plainly), which makes defining the
    population part of the exercise rather than something handed to you.
    """
    labels_rows = tables[label_table]
    cutoff = labels_rows[0]["observation_cutoff"]

    gone: set[str] = set()
    if exclude_churned_in:
        gone = {r["customer_id"] for r in tables[exclude_churned_in] if int(r["churned_next_90d"]) == 1}

    customer_ids: list[str] = []
    labels: dict[str, int] = {}
    for row in labels_rows:
        cid = row["customer_id"]
        if cid in gone:
            continue
        customer_ids.append(cid)
        labels[cid] = int(row["churned_next_90d"])

    return Population(
        name=label_table,
        cutoff=cutoff,
        customer_ids=customer_ids,
        labels=labels,
        excluded_already_churned=len(labels_rows) - len(customer_ids),
    )
