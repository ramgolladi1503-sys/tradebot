"""Research-only constituent lead-lag package."""

from .model import (
    DataContractError,
    SignalState,
    StrategyThresholds,
    TradeOutcome,
    evaluate_first_signal_per_session,
    generate_signal_states,
    summarize_outcomes,
    validate_bars,
    validate_weights,
)

__all__ = [
    "DataContractError",
    "SignalState",
    "StrategyThresholds",
    "TradeOutcome",
    "evaluate_first_signal_per_session",
    "generate_signal_states",
    "summarize_outcomes",
    "validate_bars",
    "validate_weights",
]
