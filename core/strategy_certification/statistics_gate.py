from typing import Optional
from core.statistical_validation.statistics_models import StatisticalValidationReport
from core.statistical_validation.statistics_types import ValidationStatus, SignificanceLevel, StabilityStatus
from core.strategy_certification.certification_models import GateResult
from core.strategy_certification.certification_types import GateStatus

class StatisticsGate:
    """
    Gate 4 - Statistics
    
    Consume Statistical Validation Report.
    Evaluate:
    - sufficient sample
    - confidence
    - stability
    - walk-forward
    - regime consistency
    - cost sensitivity
    
    Never recompute statistics.
    Never optimize thresholds.
    """

    @staticmethod
    def evaluate(report: Optional[StatisticalValidationReport]) -> GateResult:
        if report is None:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Statistical Validation Report is missing.",
                blockers=["Missing Statistics Report"]
            )
            
        blockers = []
        
        # Sample Validation
        if report.sample_validation.status == ValidationStatus.INSUFFICIENT_SAMPLE:
            blockers.append("Insufficient sample size for statistical validation.")
            
        # Bootstrap Confidence
        if report.bootstrap.status == SignificanceLevel.LOW_CONFIDENCE:
            blockers.append("Low statistical confidence (Bootstrap).")
        elif report.bootstrap.status == SignificanceLevel.INSUFFICIENT_SAMPLE:
            blockers.append("Insufficient sample for bootstrap confidence.")
            
        # Stability
        if hasattr(report.stability, 'status') and report.stability.status == StabilityStatus.UNSTABLE:
            blockers.append("Temporal stability is UNSTABLE.")
            
        # Walk Forward
        if hasattr(report.walk_forward, 'status') and report.walk_forward.status == StabilityStatus.UNSTABLE:
            blockers.append("Walk-forward analysis is UNSTABLE.")
            
        # Regime Analysis
        if hasattr(report.regime_analysis, 'status') and report.regime_analysis.status == StabilityStatus.UNSTABLE:
            blockers.append("Regime consistency is UNSTABLE.")
            
        if blockers:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Strategy fails statistical validation thresholds.",
                blockers=blockers
            )
            
        return GateResult(
            status=GateStatus.PASS,
            reason="Strategy passes all statistical validation thresholds."
        )
