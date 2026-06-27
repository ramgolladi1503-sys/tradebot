from typing import List
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from core.outcome_evidence.evidence_types import OutcomeStatus
from .statistics_models import ExpectancyReport
from .statistics_types import ValidationStatus

def compute_expectancy(records: List[OutcomeEvidenceRecord]) -> ExpectancyReport:
    """
    Computes average R, points, and P&L across a set of usable records.
    Filters out rejected/unusable/ambiguous records prior to computation.
    """
    usable_records = []
    
    win_count = 0
    loss_count = 0
    timeout_count = 0
    ambiguous_count = 0
    insufficient_count = 0
    
    for r in records:
        if r.outcome_status in (OutcomeStatus.AMBIGUOUS_BOTH_HIT, OutcomeStatus.NO_TRACE_DATA, OutcomeStatus.INSUFFICIENT_CANDIDATE_FIELDS, OutcomeStatus.PENDING):
            ambiguous_count += 1
            continue
            
        if r.simulation.is_hypothetical_rejected:
            insufficient_count += 1
            continue
            
        usable_records.append(r)
        
        if r.net_pnl > 0:
            win_count += 1
        elif r.net_pnl < 0:
            loss_count += 1
            
        if r.outcome_status == OutcomeStatus.TIME_STOP:
            timeout_count += 1
            
    if not usable_records:
        return ExpectancyReport(
            status=ValidationStatus.INSUFFICIENT_SAMPLE,
            win_count=win_count,
            loss_count=loss_count,
            timeout_count=timeout_count,
            ambiguous_count=ambiguous_count,
            insufficient_count=insufficient_count
        )
        
    total_net = sum(r.net_pnl for r in usable_records)
    total_gross = sum(r.gross_pnl for r in usable_records)
    total_r = sum(r.mfe_mae.realized_r for r in usable_records if r.mfe_mae is not None)
    total_points = sum(r.simulation.exit_fill - r.simulation.entry_fill for r in usable_records if r.simulation.exit_fill and r.simulation.entry_fill)
    
    n = len(usable_records)
    n_r = sum(1 for r in usable_records if r.mfe_mae is not None)
    n_pts = sum(1 for r in usable_records if r.simulation.exit_fill and r.simulation.entry_fill)
    
    avg_r = (total_r / n_r) if n_r > 0 else 0.0
    avg_pts = (total_points / n_pts) if n_pts > 0 else 0.0
    
    return ExpectancyReport(
        status=ValidationStatus.VALID,
        average_r=avg_r,
        average_points=avg_pts,
        average_net_pnl=total_net / n,
        average_gross_pnl=total_gross / n,
        win_count=win_count,
        loss_count=loss_count,
        timeout_count=timeout_count,
        ambiguous_count=ambiguous_count,
        insufficient_count=insufficient_count
    )
