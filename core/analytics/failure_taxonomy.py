from __future__ import annotations

from typing import Literal, Union, Dict, Any

# We don't import TradeOutcome directly if it causes circular dependencies, 
# but we can type hint it as a dict or any object with attributes.
FailureCategory = Literal[
    "signal_failure",
    "volatility_failure",
    "execution_failure",
    "no_failure",
    "unknown"
]

def classify_failure(
    outcome: Union[Any, Dict[str, Any]],
    volatility_mfe_threshold: float = 10.0
) -> FailureCategory:
    """
    Classify a trade outcome into a failure taxonomy category.
    
    Args:
        outcome: The trade outcome object or dict.
        volatility_mfe_threshold: The MFE (Maximum Favorable Excursion) points 
                                  required to consider a stop-loss hit as a 'volatility_failure'
                                  rather than a 'signal_failure'.
    
    Returns:
        The failure category.
    """
    # Handle dicts or objects
    if isinstance(outcome, dict):
        out_type = outcome.get("outcome", "unknown")
        exec_feasible = outcome.get("exec_feasible", True)
        mfe = outcome.get("mfe_points") or 0.0
    else:
        out_type = getattr(outcome, "outcome", "unknown")
        exec_feasible = getattr(outcome, "exec_feasible", True)
        mfe = getattr(outcome, "mfe_points", 0.0) or 0.0

    if out_type == "hit_target":
        if not exec_feasible:
            return "execution_failure"
        return "no_failure"
    
    if out_type == "hit_sl":
        if mfe >= volatility_mfe_threshold:
            return "volatility_failure"
        return "signal_failure"
        
    if out_type == "no_hit":
        # Strategy decayed or time ran out without hitting target or SL
        return "signal_failure"

    return "unknown"
