"""Churn without leakage — a reproducible, dependency-free churn pipeline.

Reads the shared fintech data model, builds features strictly as of an observation
cutoff, trains at an earlier cutoff and scores a later one (out-of-time), then
judges the result on discrimination, **calibration**, explainable drivers and
the only thing a retention team can act on: expected value per contact.

Standard library only — no numpy, pandas or scikit-learn. That is a deliberate
constraint, not a limitation to apologise for: it makes every number in the
report auditable line by line, keeps the result byte-for-byte reproducible years
from now (no library version can silently change it), and lets CI validate the
whole thing without installing anything.
"""

from .data import Population, load_tables, scoreable_population
from .features import FEATURE_NAMES, build_features
from .model import LogisticRegression, PlattCalibrator, Standardiser
from .pipeline import CaseResult, run_case

__all__ = [
    "FEATURE_NAMES",
    "CaseResult",
    "LogisticRegression",
    "PlattCalibrator",
    "Population",
    "Standardiser",
    "build_features",
    "load_tables",
    "run_case",
    "scoreable_population",
]
