"""Research-only constituent lead-lag package."""

from .model import (
    DataContractError,
    SignalState,
    StrategyThresholds,
    TradeOutcome,
    evaluate_first_signal_per_session,
    evaluate_signals_with_entry_delay,
    generate_signal_states,
    summarize_outcomes,
    validate_bars,
    validate_weights,
)
from .unweighted import (
    UnweightedSignalState,
    UnweightedThresholds,
    chronological_fold_summary,
    classify_unweighted_state,
    evaluate_unweighted_first_signal_per_session,
    generate_unweighted_signal_states,
    select_universe_snapshot,
    summarize_unweighted_outcomes,
    validate_universe,
)

__all__ = [
    "DataContractError", "SignalState", "StrategyThresholds", "TradeOutcome",
    "UnweightedSignalState", "UnweightedThresholds", "chronological_fold_summary",
    "classify_unweighted_state", "evaluate_first_signal_per_session",
    "evaluate_signals_with_entry_delay", "evaluate_unweighted_first_signal_per_session",
    "generate_signal_states", "generate_unweighted_signal_states", "select_universe_snapshot",
    "summarize_outcomes", "summarize_unweighted_outcomes", "validate_bars",
    "validate_universe", "validate_weights",
]
