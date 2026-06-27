from typing import List
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import DrawdownReport, EquityPoint
from .statistics_types import ValidationStatus

def compute_drawdown(usable_records: List[OutcomeEvidenceRecord]) -> DrawdownReport:
    """
    Computes equity curve, peak equity, maximum drawdown, and maximum drawdown duration.
    Assumes usable_records are sorted chronologically by timestamp.
    """
    if not usable_records:
        return DrawdownReport(status=ValidationStatus.INSUFFICIENT_SAMPLE)
        
    sorted_records = sorted(usable_records, key=lambda x: x.created_timestamp)
    
    equity = 0.0
    high_water_mark = 0.0
    equity_curve = []
    
    max_dd = 0.0
    max_dd_duration = 0.0
    
    peak_timestamp = sorted_records[0].created_timestamp
    
    for r in sorted_records:
        equity += r.net_pnl
        if equity > high_water_mark:
            high_water_mark = equity
            peak_timestamp = r.created_timestamp
            
        current_dd = high_water_mark - equity
        
        if current_dd > max_dd:
            max_dd = current_dd
            
        # Drawdown duration is time since the last peak
        dd_duration = r.created_timestamp - peak_timestamp
        if dd_duration > max_dd_duration:
            max_dd_duration = dd_duration
            
        equity_curve.append(EquityPoint(
            timestamp=r.created_timestamp,
            cumulative_net_pnl=equity,
            high_water_mark=high_water_mark,
            drawdown=current_dd
        ))
        
    return DrawdownReport(
        status=ValidationStatus.VALID,
        equity_curve=equity_curve,
        peak_equity=high_water_mark,
        current_drawdown=high_water_mark - equity,
        maximum_drawdown=max_dd,
        max_drawdown_duration_seconds=max_dd_duration
    )
