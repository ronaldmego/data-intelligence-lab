"""Loading the shared model, and the question that comes before ARPU: **which
revenue, over which customers?**

ARPU is a ratio, and both halves of it are decisions. This module makes them
explicitly rather than letting a `GROUP BY` make them silently:

* the **numerator** is invoices, and the data model keeps invoicing customers
  who already churned — its data card says so — so the base-wide revenue total
  includes money from people who are gone;
* the **denominator** is the population case 02 defined, for the same reason it
  defined one: a customer who left during the earlier window is history, not a
  customer to be valued.

Nothing here is clever. It is the part that is skipped.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

_TRACK = Path(__file__).resolve().parents[2]
for _dependency in ("data-model", "02-churn-prediction"):
    _path = str(_TRACK / _dependency)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from churn.data import Population, scoreable_population  # noqa: E402
from fintech import Config, generate  # noqa: E402

Tables = dict[str, list[dict]]

__all__ = [
    "Product",
    "Population",
    "RevenueBase",
    "Tables",
    "billing_months",
    "load_products",
    "load_tables",
    "revenue_base",
    "scoreable_population",
    "trailing_mean",
]


def load_tables(cfg: Config | None = None, data_dir: str | Path | None = None) -> Tables:
    """Return the data model as ``{table_name: [row, ...]}``.

    Generated in memory from the seed by default, so the case runs on a fresh
    clone with no setup step; pass ``data_dir`` to read the CSVs that
    ``data-model/generate.py`` writes. The two are equivalent — CSV values
    arrive as strings, which :func:`_f` coerces either way.
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


def _f(value: object, default: float = 0.0) -> float:
    """Coerce to float, tolerating both native values and CSV strings."""
    if value is None or value == "":
        return default
    return float(value)  # type: ignore[arg-type]


# --- the price list ---------------------------------------------------------


@dataclass(frozen=True)
class Product:
    """One tariff. The fee is the only revenue fact in this business that is
    known exactly and in advance — which turns out to matter."""

    product_id: str
    family: str
    monthly_fee: float
    credit_limit_k: float
    tier: int

    @property
    def label(self) -> str:
        return self.product_id


def load_products(tables: Tables) -> dict[str, Product]:
    return {
        row["product_id"]: Product(
            product_id=row["product_id"],
            family=row["family"],
            monthly_fee=_f(row["monthly_fee"]),
            credit_limit_k=_f(row["credit_limit_k"]),
            tier=int(_f(row["tier"])),
        )
        for row in tables["products"]
    }


def product_of(tables: Tables) -> dict[str, str]:
    return {row["customer_id"]: row["current_product_id"] for row in tables["customers"]}


def billing_months(tables: Tables) -> list[str]:
    """Every invoiced month, oldest first — the case's calendar."""
    return sorted({row["period_month"] for row in tables["billing"]})


def trailing_mean(rows: list[dict], field: str, cutoff: str, months: int) -> float:
    """The mean of ``field`` over the last ``months`` invoiced months up to ``cutoff``.

    Rows after the cutoff are dropped here rather than by the caller: an ARPU
    that quietly includes a month the analysis is supposed to be blind to is the
    revenue-side version of the leakage case 02 exists to prevent.
    """
    recent = sorted((r for r in rows if r["period_month"] <= cutoff), key=lambda r: r["period_month"])[-months:]
    return mean(_f(r[field]) for r in recent) if recent else 0.0


# --- the numerator ----------------------------------------------------------


@dataclass(frozen=True)
class RevenueBase:
    """What the revenue total is made of, once the departed are separated out.

    ``phantom_*`` is revenue invoiced *after* the earlier observation cutoff to
    customers whose label at that cutoff says they churned. The data model's card
    states plainly that it does not stop billing them; that omission is what
    makes defining the base an exercise rather than a lookup, in exactly the way
    case 02 found for the scoreable population.

    In a real operator this is neither exotic nor rare — it is what revenue
    assurance is for, and it is invisible from inside the data: `billing` is
    complete, internally consistent, and reconciles with itself.
    """

    cutoff: str
    prior_cutoff: str
    months_after_prior: int
    invoices_after_prior: int
    revenue_after_prior: float
    phantom_invoices: int
    phantom_revenue: float
    departed_customers: int
    live_customers: int

    @property
    def phantom_share(self) -> float:
        return self.phantom_revenue / self.revenue_after_prior if self.revenue_after_prior else 0.0

    @property
    def arpu_with_departed(self) -> float:
        """ARPU as a `GROUP BY` returns it: every invoice, every billed customer."""
        n = self.live_customers + self.departed_customers
        return self.revenue_after_prior / (n * self.months_after_prior) if n else 0.0

    @property
    def arpu_live_only(self) -> float:
        """ARPU over the customers who were actually there to be served."""
        live = self.revenue_after_prior - self.phantom_revenue
        return live / (self.live_customers * self.months_after_prior) if self.live_customers else 0.0


def revenue_base(tables: Tables, population: Population) -> RevenueBase:
    """Size the gap between *invoiced* revenue and revenue from live customers."""
    prior_rows = tables["churn_labels_prior"]
    prior_cutoff = prior_rows[0]["observation_cutoff"]
    departed = {r["customer_id"] for r in prior_rows if int(_f(r["churned_next_90d"])) == 1}

    after = [r for r in tables["billing"] if r["period_month"] > prior_cutoff]
    phantom = [r for r in after if r["customer_id"] in departed]
    months = len({r["period_month"] for r in after})

    return RevenueBase(
        cutoff=population.cutoff,
        prior_cutoff=prior_cutoff,
        months_after_prior=months,
        invoices_after_prior=len(after),
        revenue_after_prior=sum(_f(r["amount_billed"]) for r in after),
        phantom_invoices=len(phantom),
        phantom_revenue=sum(_f(r["amount_billed"]) for r in phantom),
        departed_customers=len(departed),
        live_customers=len(population),
    )
