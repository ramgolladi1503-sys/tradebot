"""
Statistical Validation Engine

Consumes immutable OutcomeEvidenceRecord objects to compute rigorous statistical
metrics without evaluating or asserting trading edge directly.
"""

from .statistics_types import (
    ValidationStatus,
    SignificanceLevel,
    StabilityStatus,
    DrawdownStatus
)
from .statistics_config import ValidationConfig
from .statistics_models import (
    SampleValidationReport,
    ExpectancyReport,
    ProfitFactorReport,
    EquityPoint,
    DrawdownReport,
    DescriptiveStats,
    DistributionReport,
    ConfidenceInterval,
    BootstrapReport,
    CostSensitivityReport,
    RegimeMetrics,
    RegimeReport,
    WalkForwardWindowMetrics,
    WalkForwardReport,
    RollingMetricsPoint,
    StabilityReport,
    StatisticalValidationReport
)

__all__ = [
    "ValidationConfig",
    "ValidationStatus",
    "SignificanceLevel",
    "StabilityStatus",
    "DrawdownStatus",
    "SampleValidationReport",
    "ExpectancyReport",
    "ProfitFactorReport",
    "EquityPoint",
    "DrawdownReport",
    "DescriptiveStats",
    "DistributionReport",
    "ConfidenceInterval",
    "BootstrapReport",
    "CostSensitivityReport",
    "RegimeMetrics",
    "RegimeReport",
    "WalkForwardWindowMetrics",
    "WalkForwardReport",
    "RollingMetricsPoint",
    "StabilityReport",
    "StatisticalValidationReport"
]
