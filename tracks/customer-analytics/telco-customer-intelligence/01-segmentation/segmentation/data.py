"""Loading the shared model, and the two quantities every segment is built on.

A segmentation needs an axis a customer can *move along* and an axis that says
what they are *worth*. This module produces exactly those two, and takes both
from cases that already published them rather than inventing local definitions:

* **risk** is case 02's churn model, refitted here. A segmentation that scores
  risk its own way is a second churn model nobody validated, and it will
  disagree with the published one at the worst possible moment — in a meeting.
* **value** is the monthly revenue case 02 already extracts from the shared
  feature matrix, so "high value" means the same thing in both cases.

The population question is case 02's too: customers who left during the earlier
labelled window are not customers to be segmented.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

_TRACK = Path(__file__).resolve().parents[2]
for _dependency in ("data-model", "02-churn-prediction"):
    _path = str(_TRACK / _dependency)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from churn.data import Population, scoreable_population  # noqa: E402
from churn.features import FEATURE_NAMES, build_features  # noqa: E402
from churn.model import CollinearityFilter, LogisticRegression, PlattCalibrator, Standardiser  # noqa: E402
from telco import Config, generate  # noqa: E402

Tables = dict[str, list[dict]]

__all__ = [
    "FEATURE_NAMES",
    "Population",
    "RiskModel",
    "Snapshot",
    "build_features",
    "build_snapshot",
    "load_tables",
    "scoreable_population",
]


def load_tables(cfg: Config | None = None, data_dir: str | Path | None = None) -> Tables:
    """Return the data model as ``{table_name: [row, ...]}``.

    By default the tables are generated **in memory** from the seed, so the case
    runs on a fresh clone with no setup step and no committed data. Pass
    ``data_dir`` to read CSVs written by ``data-model/generate.py`` instead.
    """
    if data_dir is not None:
        return _read_csv_dir(Path(data_dir))
    return generate(cfg or Config())


def _read_csv_dir(path: Path) -> Tables:
    if not path.is_dir():
        raise FileNotFoundError(
            f"{path} does not exist. Generate it first:\n"
            f"  cd {_TRACK / 'data-model'} && uv run generate.py"
        )
    tables: Tables = {}
    for csv_path in sorted(path.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as fh:
            tables[csv_path.stem] = list(csv.DictReader(fh))
    if not tables:
        raise FileNotFoundError(f"no CSV files in {path}")
    return tables


# --- the risk axis ----------------------------------------------------------


@dataclass(frozen=True)
class RiskModel:
    """Case 02's churn model, bundled with the transforms it is only valid with.

    Kept as one object for the reason case 02 states: the pruner and the
    standardiser are *fitted* objects, and re-deriving either from the data
    being scored is leakage that nothing would flag.
    """

    pruner: CollinearityFilter
    standardiser: Standardiser
    model: LogisticRegression
    calibrator: PlattCalibrator

    @classmethod
    def fit(
        cls,
        x: list[list[float]],
        y: list[int],
        fit_rows: list[int],
        calibration_rows: list[int],
        l2: float = 1.0,
    ) -> RiskModel:
        """Fit on ``fit_rows``, calibrate on ``calibration_rows``.

        The two index sets must be disjoint. Calibrating on rows the model was
        fitted on reports a calibration the model does not have.
        """
        x_fit = [x[i] for i in fit_rows]
        y_fit = [y[i] for i in fit_rows]

        pruner = CollinearityFilter().fit(x_fit)
        pruned = pruner.transform(x_fit)
        standardiser = Standardiser().fit(pruned)
        model = LogisticRegression(l2=l2).fit(standardiser.transform(pruned), y_fit)

        partial = cls(pruner, standardiser, model, PlattCalibrator())
        calibrator = PlattCalibrator().fit(
            partial._log_odds([x[i] for i in calibration_rows]),
            [y[i] for i in calibration_rows],
        )
        return cls(pruner, standardiser, model, calibrator)

    def _log_odds(self, x: list[list[float]]) -> list[float]:
        return self.model.decision_function(self.standardiser.transform(self.pruner.transform(x)))

    def probabilities(self, x: list[list[float]]) -> list[float]:
        return self.calibrator.transform(self._log_odds(x))


def stride(n: int, every: int) -> tuple[list[int], list[int]]:
    """A deterministic split: every ``every``-th row held out.

    No RNG, so the result is byte-reproducible on any machine and in any Python
    version — the same device case 02 uses, and for the same reason.
    """
    held = [i for i in range(n) if i % every == 0]
    kept = [i for i in range(n) if i % every != 0]
    return kept, held


# --- one moment in time -----------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    """The base as it looked at one cutoff: who, how risky, how valuable.

    Two of these — one per observation cutoff — are what let this case ask
    whether a segment survives long enough to act on.
    """

    cutoff: str
    customer_ids: list[str]
    risk: list[float]             # calibrated churn probability
    value: list[float]            # monthly revenue
    labels: list[int]             # what actually happened, for evaluation only
    features: list[list[float]]

    def __len__(self) -> int:
        return len(self.customer_ids)

    def index_of(self) -> dict[str, int]:
        return {cid: i for i, cid in enumerate(self.customer_ids)}


def build_snapshot(
    tables: Tables,
    population: Population,
    risk_model: RiskModel,
    features: list[list[float]] | None = None,
) -> Snapshot:
    """Score one population with an already-fitted risk model."""
    x = features if features is not None else build_features(tables, population.cutoff, population.customer_ids)
    revenue_column = FEATURE_NAMES.index("arpu_last3")
    return Snapshot(
        cutoff=population.cutoff,
        customer_ids=list(population.customer_ids),
        risk=risk_model.probabilities(x),
        value=[row[revenue_column] for row in x],
        labels=[population.labels[c] for c in population.customer_ids],
        features=x,
    )
