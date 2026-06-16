import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AlphaDecayState:
    initial_edge_bps: float
    current_edge_bps: float
    holding_time_sec: int
    expected_holding_time_sec: int
    execution_cost_bps: float

def monitor_alpha_decay(state: AlphaDecayState, l2_support_ratio: float, current_momentum_bps: float) -> bool:
    """
    Evaluates real-time expected value (EV) of an open trade.
    If the total remaining edge falls below execution costs, it emits a FORCE_EXIT signal.
    
    Returns:
        bool: True if trade should be force-exited, False otherwise.
    """
    try:
        # 1. Calculate Theta Decay Penalty (Time penalty)
        # If we have held the trade longer than expected, the edge decays exponentially
        if state.expected_holding_time_sec > 0:
            time_ratio = state.holding_time_sec / state.expected_holding_time_sec
            theta_penalty = state.initial_edge_bps * (time_ratio ** 1.5)
        else:
            theta_penalty = 0.0
            
        # 2. Calculate L2 Support Edge
        # If order flow strongly supports us (e.g. ratio > 0.5), we get a boost to our edge
        # If it's weak (< 0.2), we lose edge
        l2_edge_adjustment = (l2_support_ratio - 0.35) * 10.0 # scale basis points
        
        # 3. Calculate Momentum Edge
        momentum_edge = current_momentum_bps
        
        # 4. Total Expected Value Remaining
        total_edge_remaining = state.initial_edge_bps - theta_penalty + l2_edge_adjustment + momentum_edge
        
        # Update state for logging
        state.current_edge_bps = total_edge_remaining
        
        # Check against execution cost
        if total_edge_remaining < state.execution_cost_bps:
            logger.info(f"Alpha Decay Exit Triggered: Edge {total_edge_remaining:.2f}bps < Costs {state.execution_cost_bps:.2f}bps")
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Alpha decay monitoring failed: {e}")
        # Fail open, do not force exit if monitoring breaks
        return False
