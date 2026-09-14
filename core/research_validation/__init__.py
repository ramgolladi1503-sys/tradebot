"""Offline statistical research-validation primitives.

This package is deliberately read-only with respect to trading runtime state. It has
no broker, order, strategy, live-runtime, or credential imports.
"""

from .policy import CertificationInput, CertificationVerdict, certify_research
from .statistics import (
    benjamini_hochberg,
    bonferroni_rejections,
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_ratio,
    effective_rank,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
    sample_sharpe,
)

__all__ = [
    "CertificationInput",
    "CertificationVerdict",
    "certify_research",
    "sample_sharpe",
    "probabilistic_sharpe_ratio",
    "minimum_track_record_length",
    "effective_rank",
    "deflated_sharpe_ratio",
    "bonferroni_rejections",
    "benjamini_hochberg",
    "cscv_probability_of_backtest_overfitting",
]
