"""Movement strategy package.

Movement strategies emit read-only StrategyCandidate objects. They do not call
brokers, submit orders, alter execution gates, touch depth subscriptions, or tune
live trading behavior.
"""

from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
from strategies.movement.exhaustion_reversal import generate_exhaustion_reversal_candidates
from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
from strategies.movement.late_day_momentum import generate_late_day_momentum_candidates
from strategies.movement.market_event_graph_reversal import generate_market_event_graph_reversal_candidates
from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates
from strategies.movement.no_trade_chop import generate_no_trade_candidates
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates

__all__ = [
    "generate_compression_breakout_candidates",
    "generate_event_volatility_expansion_candidates",
    "generate_exhaustion_reversal_candidates",
    "generate_failed_breakout_trap_candidates",
    "generate_late_day_momentum_candidates",
    "generate_market_event_graph_reversal_candidates",
    "generate_mean_reversion_extension_candidates",
    "generate_no_trade_candidates",
    "generate_opening_drive_candidates",
    "generate_opening_range_retest_candidates",
    "generate_option_pressure_candidates",
    "generate_trend_pullback_candidates",
    "generate_vwap_reclaim_rejection_candidates",
]
