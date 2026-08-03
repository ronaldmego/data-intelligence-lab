"""Governed next-best-offer — the decision, and the rules that constrain it.

Cases 02 and 05 both take their audiences **as the campaign built them**. This
one asks the question they skipped: who was the company *allowed* to contact,
with what, and how often?

The finding is not that governance costs volume — everyone expects that. It is
that the gates do not remove a random slice, and they do not all miss it in the
same direction:
consent removes the customers least likely to leave (engaged customers opt in),
a cool-off window removes the ones most likely to leave (they were contacted
last quarter *because* they were high risk), and eligibility removes whoever the
catalogue happens to exclude. The permitted population is not a smaller version
of the base — it is a different one, and a programme scored on it is answering a
different question from the one the plan asked.

Standard library only, like the rest of the track: every number in the report is
auditable line by line and CI validates it without installing anything. The
churn model, its feature builder and the base ``Economics`` come from case 02;
the save rate comes from case 05's experiment; the answer key is read through
case 05's quarantined module and never by anything that produces an estimate.
"""

from .allocation import Assignment, Plan, PlanComparison, filter_then_rank, rank_then_filter, ungoverned
from .audit import CampaignAudit, ReachDecomposition, audit_retention_campaigns
from .data import (
    ContactHistory,
    Offer,
    PlanLadder,
    Wave,
    build_wave,
    load_consent,
    load_offers,
    load_tables,
)
from .pipeline import CaseResult, ConsentProfile, RuleCost, SensitivityPoint, run_case
from .policy import ContactPolicy, CustomerFacts, Permission, PermissionMatrix, evaluate
from .value import MEASURED_SAVE_RATE, AcceptanceModel, OfferEconomics, OfferValue, score_offers

__all__ = [
    "MEASURED_SAVE_RATE",
    "AcceptanceModel",
    "Assignment",
    "CampaignAudit",
    "CaseResult",
    "ConsentProfile",
    "ContactHistory",
    "ContactPolicy",
    "CustomerFacts",
    "Offer",
    "OfferEconomics",
    "OfferValue",
    "Permission",
    "PermissionMatrix",
    "Plan",
    "PlanComparison",
    "PlanLadder",
    "ReachDecomposition",
    "RuleCost",
    "SensitivityPoint",
    "Wave",
    "audit_retention_campaigns",
    "build_wave",
    "evaluate",
    "filter_then_rank",
    "load_consent",
    "load_offers",
    "load_tables",
    "rank_then_filter",
    "run_case",
    "score_offers",
    "ungoverned",
]
