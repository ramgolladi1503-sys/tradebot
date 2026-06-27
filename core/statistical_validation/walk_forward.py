from typing import List
from typing import Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import WalkForwardReport, WalkForwardWindowMetrics
from .statistics_types import StabilityStatus, ValidationStatus
from .expectancy import compute_expectancy
from .profit_factor import compute_profit_factor
from .drawdown import compute_drawdown
from .statistics_config import ValidationConfig

def compute_walk_forward(usable_records: List[OutcomeEvidenceRecord], config: Optional[ValidationConfig] = None) -> WalkForwardReport:
    """
    Slices evidence chronologically and computes metrics per window.
    """
    if config is None:
        config = ValidationConfig()
        
    n = len(usable_records)
    window_size = config.walk_forward_window_size
    if n < window_size:
        return WalkForwardReport(status=StabilityStatus.INSUFFICIENT_DATA)
        
    sorted_records = sorted(usable_records, key=lambda x: x.created_timestamp)
    windows = []
    
    # Chunk by size
    for i in range(0, n, window_size):
        chunk = sorted_records[i:i+window_size]
        if len(chunk) < window_size * 0.5: # Skip very small final remainder chunk
            continue
            
        exp = compute_expectancy(chunk)
        pf = compute_profit_factor(chunk)
        dd = compute_drawdown(chunk)
        
        start_time = chunk[0].created_timestamp
        end_time = chunk[-1].created_timestamp
        
        if len(chunk) >= config.walk_forward_minimum_internal_size: # minimum internal size
            windows.append(WalkForwardWindowMetrics(
                start_time=start_time,
                end_time=end_time,
                sample_size=len(chunk),
                expectancy=exp.average_net_pnl,
                profit_factor=pf.profit_factor,
                max_drawdown=dd.maximum_drawdown,
                status=ValidationStatus.VALID
            ))
        else:
            windows.append(WalkForwardWindowMetrics(
                start_time=start_time,
                end_time=end_time,
                sample_size=len(chunk),
                status=ValidationStatus.INSUFFICIENT_SAMPLE
            ))
            
    # Simple stability heuristic based on windows
    # If more than 30% of windows are negative expectancy, it's unstable
    valid_windows = [w for w in windows if w.status == ValidationStatus.VALID]
    if not valid_windows:
        status = StabilityStatus.INSUFFICIENT_DATA
    else:
        negative_windows = sum(1 for w in valid_windows if w.expectancy is not None and w.expectancy < 0)
        unstable = (negative_windows / len(valid_windows)) > 0.3
        status = StabilityStatus.UNSTABLE if unstable else StabilityStatus.STABLE
        
    return WalkForwardReport(
        status=status,
        windows=windows
    )
