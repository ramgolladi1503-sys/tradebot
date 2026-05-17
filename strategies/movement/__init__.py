"""Movement strategy package.

Movement strategies emit read-only StrategyCandidate objects. They do not call
brokers, submit orders, alter execution gates, touch depth subscriptions, or tune
live trading behavior.
"""

from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates

__all__ = [
    "generate_opening_drive_candidates",
    "generate_opening_range_retest_candidates",
]
