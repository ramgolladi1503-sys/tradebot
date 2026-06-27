from typing import Optional
from .evidence_models import ReplayCandidate, OptionTracePoint, ExecutionSimulation
from .evidence_types import EvidenceQuality


class ExecutionSimulator:
    """Simulates realistic execution fills and records candidate hypothetical status."""
    
    def simulate(self, candidate: ReplayCandidate, entry_tick: Optional[OptionTracePoint], exit_tick: Optional[OptionTracePoint]) -> ExecutionSimulation:
        if candidate.evidence_quality == EvidenceQuality.UNUSABLE or candidate.entry_price is None or candidate.target_price is None:
            return ExecutionSimulation(0.0, 0.0, 0.0, 0.0, False, False, not candidate.execution_ok)
            
        # Default fills are the requested prices unless we have exact trace data
        entry_fill = candidate.entry_price
        exit_fill = 0.0
        spread_impact = 0.0
        slippage_impact = 0.5  # default
        
        if entry_tick:
            if entry_tick.ask and candidate.target_price > candidate.entry_price:
                # Long entry hits ask
                entry_fill = entry_tick.ask
                if entry_tick.bid:
                    spread_impact = entry_tick.ask - entry_tick.bid
            elif entry_tick.bid and candidate.target_price < candidate.entry_price:
                # Short entry hits bid
                entry_fill = entry_tick.bid
                if entry_tick.ask:
                    spread_impact = entry_tick.ask - entry_tick.bid
            else:
                entry_fill = entry_tick.ltp
                
        if exit_tick:
            if exit_tick.bid and candidate.target_price > candidate.entry_price:
                # Long exit hits bid
                exit_fill = exit_tick.bid
            elif exit_tick.ask and candidate.target_price < candidate.entry_price:
                # Short exit hits ask
                exit_fill = exit_tick.ask
            else:
                exit_fill = exit_tick.ltp
                
        return ExecutionSimulation(
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            spread_impact=spread_impact,
            slippage_impact=slippage_impact,
            delayed_entry=False,
            delayed_exit=False,
            is_hypothetical_rejected=not candidate.execution_ok
        )
