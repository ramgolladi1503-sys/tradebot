from typing import List
from typing import Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import StabilityReport, RollingMetricsPoint
from .statistics_types import StabilityStatus
from .expectancy import compute_expectancy
from .profit_factor import compute_profit_factor
from .drawdown import compute_drawdown
from .statistics_config import ValidationConfig

def compute_stability(usable_records: List[OutcomeEvidenceRecord], config: Optional[ValidationConfig] = None) -> StabilityReport:
    """
    Computes rolling metrics (expectancy, PF, drawdown) to detect drift or collapse.
    """
    if config is None:
        config = ValidationConfig()
        
    rolling_window = config.stability_rolling_window_size
    n = len(usable_records)
    if n < rolling_window:
        return StabilityReport(status=StabilityStatus.INSUFFICIENT_DATA)
        
    sorted_records = sorted(usable_records, key=lambda x: x.created_timestamp)
    rolling_metrics = []
    
    for i in range(n - rolling_window + 1):
        window = sorted_records[i:i+rolling_window]
        exp = compute_expectancy(window)
        pf = compute_profit_factor(window)
        dd = compute_drawdown(window)
        
        rolling_metrics.append(RollingMetricsPoint(
            timestamp=window[-1].created_timestamp,
            rolling_expectancy=exp.average_net_pnl,
            rolling_pf=pf.profit_factor,
            rolling_drawdown=dd.maximum_drawdown,
            rolling_sample_size=rolling_window
        ))
        
    # Analyze drift
    # Compare first 30% of rolling points to last 30%
    num_points = len(rolling_metrics)
    slice_size = max(1, int(num_points * 0.3))
    
    first_slice = [p.rolling_expectancy for p in rolling_metrics[:slice_size] if p.rolling_expectancy is not None]
    last_slice = [p.rolling_expectancy for p in rolling_metrics[-slice_size:] if p.rolling_expectancy is not None]
    
    drift = None
    collapse = False
    improvement = False
    
    if first_slice and last_slice:
        avg_first = sum(first_slice) / len(first_slice)
        avg_last = sum(last_slice) / len(last_slice)
        
        if avg_first != 0:
            drift = (avg_last - avg_first) / abs(avg_first)
            
            if drift < -0.5 and avg_last <= 0:
                collapse = True
            elif drift > 0.5 and avg_last > 0:
                improvement = True

    status = StabilityStatus.UNSTABLE if collapse else StabilityStatus.STABLE
    
    return StabilityReport(
        status=status,
        rolling_metrics=rolling_metrics,
        performance_drift=drift,
        performance_collapse_detected=collapse,
        performance_improvement_detected=improvement,
        regime_dependence_detected=False # We would need regime correlation here, simplifying for now
    )
