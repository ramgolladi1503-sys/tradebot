"""Offline statistical validation primitives for TradeBot research.

This package has no broker/order authority and is intentionally not wired to
live execution. It complements, rather than replaces, the existing WFA stack.
"""

from .distribution import DistributionDiagnostics, diagnose_returns
from .ledger import TrialRecord, summarize_trial_ledger, trial_ledger_sha256, validate_trial_ledger
from .pbo import PBOResult, probability_of_backtest_overfitting
from .statistics import (
    adjust_pvalues_benjamini_hochberg,
    adjust_pvalues_benjamini_yekutieli,
    adjust_pvalues_bonferroni,
    adjust_pvalues_holm,
    adjust_pvalues_sidak,
    critical_sharpe_ratio,
    deflated_sharpe_ratio,
    effective_rank,
    effective_trials_from_returns,
    expected_maximum_sharpe_ratio,
    minimum_track_record_length,
    one_sided_pvalue_from_psr,
    probabilistic_sharpe_ratio,
    sharpe_ratio_power,
    sharpe_ratio_variance,
)
from .verdict import (
    ResearchEvidence,
    ResearchValidationPolicy,
    ResearchVerdict,
    ValidationState,
    evaluate_research_evidence,
)

__all__ = [
    "DistributionDiagnostics",
    "PBOResult",
    "ResearchEvidence",
    "ResearchValidationPolicy",
    "ResearchVerdict",
    "TrialRecord",
    "ValidationState",
    "adjust_pvalues_benjamini_hochberg",
    "adjust_pvalues_benjamini_yekutieli",
    "adjust_pvalues_bonferroni",
    "adjust_pvalues_holm",
    "adjust_pvalues_sidak",
    "critical_sharpe_ratio",
    "deflated_sharpe_ratio",
    "diagnose_returns",
    "effective_rank",
    "effective_trials_from_returns",
    "evaluate_research_evidence",
    "expected_maximum_sharpe_ratio",
    "minimum_track_record_length",
    "one_sided_pvalue_from_psr",
    "probabilistic_sharpe_ratio",
    "probability_of_backtest_overfitting",
    "sharpe_ratio_power",
    "sharpe_ratio_variance",
    "summarize_trial_ledger",
    "trial_ledger_sha256",
    "validate_trial_ledger",
]
