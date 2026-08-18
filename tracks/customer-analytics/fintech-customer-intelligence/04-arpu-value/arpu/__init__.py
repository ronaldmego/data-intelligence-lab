"""ARPU and value decomposition — what a customer is worth, link by link.

Reads the shared fintech data model and case 02's churn model, then takes apart
the single number every earlier case used for customer value: ``arpu_last3``
times a flat margin times a flat twelve months. Each link of the chain — plan
fee, billed ARPU, collected ARPU, contribution, expected life — is measured on
its own, so the effect of changing it is attributable rather than aggregate.

Standard library only, same as the rest of the track: every figure in the report
is auditable line by line, reproducible byte for byte from the seed, and CI can
run the whole thing without installing anything.
"""

from .bridge import Bridge, build_bridge
from .collection import Collection, measure_collection
from .costs import CostModel, ServiceProfile, load_cost_model
from .data import Population, Product, RevenueBase, load_tables, revenue_base
from .decision import Accounting, Bakeoff, Constants, run_bakeoff
from .horizon import expected_remaining_months, hazard_horizon, monthly_hazard
from .pipeline import MEASURED_SAVE_RATE, CaseResult, run_case
from .revenue import split_revenue, usage_link
from .stability import AxisStability, measure_axis

__all__ = [
    "MEASURED_SAVE_RATE",
    "Accounting",
    "AxisStability",
    "Bakeoff",
    "Bridge",
    "CaseResult",
    "Collection",
    "Constants",
    "CostModel",
    "Product",
    "Population",
    "RevenueBase",
    "ServiceProfile",
    "build_bridge",
    "expected_remaining_months",
    "hazard_horizon",
    "load_cost_model",
    "load_tables",
    "measure_axis",
    "measure_collection",
    "monthly_hazard",
    "revenue_base",
    "run_case",
    "split_revenue",
    "usage_link",
]
