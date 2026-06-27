from typing import List, Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import CostSensitivityReport
from .statistics_types import ValidationStatus
from .statistics_config import ValidationConfig

def compute_cost_sensitivity(usable_records: List[OutcomeEvidenceRecord], config: Optional[ValidationConfig] = None) -> CostSensitivityReport:
    """
    Evaluates expectancy under different cost assumptions to measure sensitivity.
    """
    if config is None:
        config = ValidationConfig()
    if not usable_records:
        return CostSensitivityReport(status=ValidationStatus.INSUFFICIENT_SAMPLE)
        
    n = len(usable_records)
    
    no_slippage_pnl = 0.0
    estimated_slippage_pnl = 0.0
    increased_slippage_pnl = 0.0
    higher_brokerage_pnl = 0.0
    spread_expansion_pnl = 0.0
    
    for r in usable_records:
        # Reconstruct base components
        gross = r.gross_pnl
        base_cost = r.cost_breakdown.total_cost
        
        # We need to extract the slippage, spread, and brokerage components
        slippage_cost = next((c.value for c in r.cost_breakdown.components if c.name == "slippage"), 0.0)
        spread_cost = next((c.value for c in r.cost_breakdown.components if c.name == "spread"), 0.0)
        brokerage_cost = next((c.value for c in r.cost_breakdown.components if c.name == "brokerage"), 0.0)
        
        # Scenario 1: No slippage
        # Remove slippage from base_cost
        no_slip_cost = base_cost - slippage_cost
        no_slippage_pnl += (gross - no_slip_cost)
        
        # Scenario 2: Base (Estimated/Actual) - this is just net_pnl
        estimated_slippage_pnl += r.net_pnl
        
        # Scenario 3: Increased slippage
        inc_slip_cost = base_cost + slippage_cost * (config.increased_slippage_multiplier - 1)
        increased_slippage_pnl += (gross - inc_slip_cost)
        
        # Scenario 4: Higher brokerage
        high_brok_cost = base_cost + brokerage_cost * (config.higher_brokerage_multiplier - 1)
        higher_brokerage_pnl += (gross - high_brok_cost)
        
        # Scenario 5: Spread expansion
        spread_exp_cost = base_cost + spread_cost * (config.spread_expansion_multiplier - 1)
        spread_expansion_pnl += (gross - spread_exp_cost)
        
    base_exp = estimated_slippage_pnl / n
    remains_positive = (
        increased_slippage_pnl / n > 0 and 
        higher_brokerage_pnl / n > 0 and 
        spread_expansion_pnl / n > 0
    )
    
    # If base is negative, obviously it doesn't remain positive under stress.
    if base_exp <= 0:
        remains_positive = False

    return CostSensitivityReport(
        status=ValidationStatus.VALID,
        no_slippage_expectancy=no_slippage_pnl / n,
        estimated_slippage_expectancy=base_exp,
        increased_slippage_expectancy=increased_slippage_pnl / n,
        higher_brokerage_expectancy=higher_brokerage_pnl / n,
        spread_expansion_expectancy=spread_expansion_pnl / n,
        remains_positive_under_stress=remains_positive
    )
