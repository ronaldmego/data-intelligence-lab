"""Campaign incrementality — did the campaign cause anything, and can we tell?

Reads the shared telco data model, finds the held-out control group the
retention campaigns were run with, and works through the readings of the same
data that disagree with each other: the confounded ones available without a
control, the intent-to-treat comparison the control was bought for, and the
complier effect that rescales it.

The finding is not an effect size. It is that **the interval is wider than the
effect** — two identically designed campaigns on the same population report
"nothing" and "a large, significant save", and the answer key shows both are the
same true effect plus a randomisation draw. What the case delivers is the honest
version of the number case 02 had to assume, the interval around it, and the
sample size it would take to shrink that interval.

Standard library only, like the rest of the track: every number in the report is
auditable line by line and CI validates it without installing anything.
"""

from .balance import check_balance
from .data import Audience, Campaign, build_audience, load_campaigns, load_tables, retention_responders
from .economics import measured_save_rate, reprice_case_02
from .estimators import Estimate, first_stage, intent_to_treat, pool, wald
from .heterogeneity import by_risk
from .pipeline import CaseResult, run_case
from .truth import Truth, decompose, load_truth

__all__ = [
    "Audience",
    "CaseResult",
    "Campaign",
    "Estimate",
    "Truth",
    "build_audience",
    "by_risk",
    "check_balance",
    "decompose",
    "first_stage",
    "intent_to_treat",
    "load_campaigns",
    "load_tables",
    "load_truth",
    "measured_save_rate",
    "pool",
    "reprice_case_02",
    "retention_responders",
    "run_case",
    "wald",
]
