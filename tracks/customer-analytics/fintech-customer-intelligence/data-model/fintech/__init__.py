"""Synthetic fintech customer-intelligence data model.

The shared, causal, reproducible dataset that the five customer-analytics cases
(segmentation, churn, next-best-offer, ARPU, incrementality) all read from.
"""

from .config import Config
from .model import generate
from .writer import write_tables

__all__ = ["Config", "generate", "write_tables"]
