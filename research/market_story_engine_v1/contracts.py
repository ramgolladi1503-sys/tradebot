from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class MarketState(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    BALANCED_RANGE = "BALANCED_RANGE"
    APPROACHING_RESISTANCE = "APPROACHING_RESISTANCE"
    APPROACHING_SUPPORT = "APPROACHING_SUPPORT"
    BREAKOUT_ATTEMPT_UP = "BREAKOUT_ATTEMPT_UP"
    BREAKOUT_ATTEMPT_DOWN = "BREAKOUT_ATTEMPT_DOWN"
    REJECTION_UP = "REJECTION_UP"
    REJECTION_DOWN = "REJECTION_DOWN"
    ACCEPTED_ABOVE = "ACCEPTED_ABOVE"
    ACCEPTED_BELOW = "ACCEPTED_BELOW"
    RETEST_HOLD_UP = "RETEST_HOLD_UP"
    RETEST_HOLD_DOWN = "RETEST_HOLD_DOWN"
    EXPANSION_UP = "EXPANSION_UP"
    EXPANSION_DOWN = "EXPANSION_DOWN"
    EXHAUSTION_UP = "EXHAUSTION_UP"
    EXHAUSTION_DOWN = "EXHAUSTION_DOWN"


class Decision(str, Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    WAIT = "WAIT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class LayerEvidence:
    structure_score_long: float
    structure_score_short: float
    participation_score_long: float
    participation_score_short: float
    option_score_long: float
    option_score_short: float
    room_up_bps: float
    room_down_bps: float
    state: str
    level: float | None
    data_complete: bool


@dataclass(frozen=True)
class DecisionRecord:
    timestamp: str
    decision: str
    state: str
    confidence: float
    entry_reference: float | None
    invalidation_level: float | None
    target_reference: float | None
    reason_codes: tuple[str, ...]
    evidence: LayerEvidence
    research_only: bool = True
    allowed_for_live_execution: bool = False
    broker_api_called: bool = False
    is_order_action: bool = False
    live_order_action: bool = False
    broker_order_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
