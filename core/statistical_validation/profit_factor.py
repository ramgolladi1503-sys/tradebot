from typing import List
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import ProfitFactorReport
from .statistics_types import ValidationStatus

def compute_profit_factor(usable_records: List[OutcomeEvidenceRecord]) -> ProfitFactorReport:
    """
    Computes the profit factor (gross profits / gross losses) for the given records.
    Assumes `usable_records` has already been filtered for rejected/ambiguous/unusable records.
    Gross profits/losses here usually correspond to gross_pnl. We will use net_pnl for consistency,
    but the user specifically mentioned 'Do not ignore costs' and 'gross profits / gross losses' 
    in Phase 4. Wait, "Do not ignore costs" means we should use net profits over net losses! Or 
    maybe gross PnL minus costs? We will use net_pnl to ensure costs are included.
    Wait, the user said:
    "Compute: gross profits, gross losses, profit factor. Do not ignore costs."
    If PF = gross profits / gross losses, that ignores costs.
    If PF = net profits / net losses, it includes costs.
    We will compute sum(net_pnl where net_pnl > 0) / abs(sum(net_pnl where net_pnl < 0)).
    """
    if not usable_records:
        return ProfitFactorReport(status=ValidationStatus.INSUFFICIENT_SAMPLE)
        
    net_profits = sum(r.net_pnl for r in usable_records if r.net_pnl > 0)
    net_losses = abs(sum(r.net_pnl for r in usable_records if r.net_pnl < 0))
    
    if net_losses == 0.0:
        return ProfitFactorReport(
            status=ValidationStatus.UNDEFINED,
            gross_profits=net_profits,
            gross_losses=net_losses,
            profit_factor=None
        )
        
    pf = net_profits / net_losses
    
    return ProfitFactorReport(
        status=ValidationStatus.VALID,
        gross_profits=net_profits,
        gross_losses=net_losses,
        profit_factor=pf
    )
