from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

class DataQualityState(Enum):
    FRESH = "FRESH"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FALLBACK = "FALLBACK"
    SYNTHETIC = "SYNTHETIC"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"

@dataclass
class DataQualityReport:
    state: DataQualityState
    score: float
    reasons: List[str]
    quote_truth_source: Optional[str] = None
    quote_age_sec: Optional[float] = None
    option_ltp_age_sec: Optional[float] = None
    spread_pct: Optional[float] = None
    fallback_detected: bool = False
    stale_detected: bool = False
    synthetic_detected: bool = False
    liquidity_state: Optional[str] = None
    execution_block_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "score": self.score,
            "reasons": self.reasons,
            "quote_truth_source": self.quote_truth_source,
            "quote_age_sec": self.quote_age_sec,
            "option_ltp_age_sec": self.option_ltp_age_sec,
            "spread_pct": self.spread_pct,
            "fallback_detected": self.fallback_detected,
            "stale_detected": self.stale_detected,
            "synthetic_detected": self.synthetic_detected,
            "liquidity_state": self.liquidity_state,
            "execution_block_reason": self.execution_block_reason
        }
