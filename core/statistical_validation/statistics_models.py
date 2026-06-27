from dataclasses import dataclass, field
from typing import Optional, List, Dict
from .statistics_types import ValidationStatus, SignificanceLevel, StabilityStatus

@dataclass(frozen=True)
class SampleValidationReport:
    total_records: int
    usable_sample_size: int
    rejected_sample_size: int
    insufficient_evidence_count: int
    ambiguous_count: int
    missing_trace_count: int
    executable_count: int
    hypothetical_count: int
    status: ValidationStatus

@dataclass(frozen=True)
class ExpectancyReport:
    status: ValidationStatus
    average_r: Optional[float] = None
    average_points: Optional[float] = None
    average_net_pnl: Optional[float] = None
    average_gross_pnl: Optional[float] = None
    win_count: int = 0
    loss_count: int = 0
    timeout_count: int = 0
    ambiguous_count: int = 0
    insufficient_count: int = 0

@dataclass(frozen=True)
class ProfitFactorReport:
    status: ValidationStatus
    gross_profits: Optional[float] = None
    gross_losses: Optional[float] = None
    profit_factor: Optional[float] = None

@dataclass(frozen=True)
class EquityPoint:
    timestamp: float
    cumulative_net_pnl: float
    high_water_mark: float
    drawdown: float

@dataclass(frozen=True)
class DrawdownReport:
    status: ValidationStatus
    equity_curve: List[EquityPoint] = field(default_factory=list)
    peak_equity: Optional[float] = None
    current_drawdown: Optional[float] = None
    maximum_drawdown: Optional[float] = None
    max_drawdown_duration_seconds: Optional[float] = None

@dataclass(frozen=True)
class DescriptiveStats:
    count: int
    mean: float
    median: float
    variance: float
    standard_deviation: float
    percentile_5: float
    percentile_25: float
    percentile_75: float
    percentile_95: float

@dataclass(frozen=True)
class DistributionReport:
    status: ValidationStatus
    win_distribution: Optional[DescriptiveStats] = None
    loss_distribution: Optional[DescriptiveStats] = None
    r_distribution: Optional[DescriptiveStats] = None
    duration_distribution: Optional[DescriptiveStats] = None
    mfe_distribution: Optional[DescriptiveStats] = None
    mae_distribution: Optional[DescriptiveStats] = None

@dataclass(frozen=True)
class ConfidenceInterval:
    lower_bound: float
    upper_bound: float
    mean_estimate: float

@dataclass(frozen=True)
class BootstrapReport:
    status: SignificanceLevel
    expectancy_ci: Optional[ConfidenceInterval] = None
    profit_factor_ci: Optional[ConfidenceInterval] = None
    mean_r_ci: Optional[ConfidenceInterval] = None

@dataclass(frozen=True)
class CostSensitivityReport:
    status: ValidationStatus
    no_slippage_expectancy: Optional[float] = None
    estimated_slippage_expectancy: Optional[float] = None
    increased_slippage_expectancy: Optional[float] = None
    higher_brokerage_expectancy: Optional[float] = None
    spread_expansion_expectancy: Optional[float] = None
    remains_positive_under_stress: Optional[bool] = None

@dataclass(frozen=True)
class RegimeMetrics:
    regime_name: str
    sample_size: int
    expectancy: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown: Optional[float] = None
    confidence: SignificanceLevel = SignificanceLevel.INSUFFICIENT_SAMPLE
    status: ValidationStatus = ValidationStatus.INSUFFICIENT_SAMPLE

@dataclass(frozen=True)
class RegimeReport:
    status: ValidationStatus
    trend_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    range_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    entropy_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    volatility_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    expiry_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    iv_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    liquidity_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)
    spread_metrics: Dict[str, RegimeMetrics] = field(default_factory=dict)

@dataclass(frozen=True)
class WalkForwardWindowMetrics:
    start_time: float
    end_time: float
    sample_size: int
    expectancy: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown: Optional[float] = None
    status: ValidationStatus = ValidationStatus.INSUFFICIENT_SAMPLE

@dataclass(frozen=True)
class WalkForwardReport:
    status: StabilityStatus
    windows: List[WalkForwardWindowMetrics] = field(default_factory=list)

@dataclass(frozen=True)
class RollingMetricsPoint:
    timestamp: float
    rolling_expectancy: Optional[float] = None
    rolling_pf: Optional[float] = None
    rolling_drawdown: Optional[float] = None
    rolling_sample_size: int = 0

@dataclass(frozen=True)
class StabilityReport:
    status: StabilityStatus
    rolling_metrics: List[RollingMetricsPoint] = field(default_factory=list)
    performance_drift: Optional[float] = None
    performance_collapse_detected: bool = False
    performance_improvement_detected: bool = False
    regime_dependence_detected: bool = False

@dataclass(frozen=True)
class StatisticalValidationReport:
    run_id: str
    sample_validation: SampleValidationReport
    expectancy: ExpectancyReport
    profit_factor: ProfitFactorReport
    drawdown: DrawdownReport
    distribution: DistributionReport
    bootstrap: BootstrapReport
    cost_sensitivity: CostSensitivityReport
    regime_analysis: RegimeReport
    walk_forward: WalkForwardReport
    stability: StabilityReport
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
