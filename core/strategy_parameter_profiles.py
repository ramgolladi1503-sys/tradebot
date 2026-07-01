"""Strategy parameter profiles and WFA evidence store interface."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

EXPERIMENTAL = "EXPERIMENTAL"
ADVISORY_ONLY = "ADVISORY_ONLY"
PAPER_EXECUTABLE = "PAPER_EXECUTABLE"
MANUAL_APPROVAL_ELIGIBLE = "MANUAL_APPROVAL_ELIGIBLE"
PROMOTED = "PROMOTED"
DISABLED = "DISABLED"

@dataclass(frozen=True)
class StrategyParameterProfile:
    strategy_id: str
    strategy_version: str
    instrument: str
    regime_bucket: str
    session_bucket: str
    expiry_context: str
    volatility_bucket: str
    params: dict[str, float | int | str | bool] = field(default_factory=dict)
    params_hash: str = field(init=False)

    def __post_init__(self) -> None:
        params_str = json.dumps(self.params, sort_keys=True)
        # Deterministic SHA256 string including full context
        context_dict = {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "instrument": self.instrument,
            "regime_bucket": self.regime_bucket,
            "session_bucket": self.session_bucket,
            "expiry_context": self.expiry_context,
            "volatility_bucket": self.volatility_bucket,
            "params": self.params,
        }
        full_str = json.dumps(context_dict, sort_keys=True)
        object.__setattr__(self, "params_hash", hashlib.sha256(full_str.encode("utf-8")).hexdigest())

@dataclass
class StrategyEvidenceDecision:
    strategy_id: str
    strategy_version: str
    params_hash: str
    instrument: str
    regime_bucket: str
    session_bucket: str
    promotion_state: str
    evidence_status: str
    evidence_reason: str
    sample_size: int | None = None
    last_updated: float | None = None

class StrategyEvidenceStore(Protocol):
    def get_promotion_state(
        self,
        strategy_id: str,
        strategy_version: str,
        params_hash: str,
        instrument: str,
        regime_bucket: str,
        session_bucket: str,
    ) -> StrategyEvidenceDecision:
        ...

class DefaultStrategyEvidenceStore:
    def get_promotion_state(
        self,
        strategy_id: str,
        strategy_version: str,
        params_hash: str,
        instrument: str,
        regime_bucket: str,
        session_bucket: str,
    ) -> StrategyEvidenceDecision:
        return StrategyEvidenceDecision(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params_hash=params_hash,
            instrument=instrument,
            regime_bucket=regime_bucket,
            session_bucket=session_bucket,
            promotion_state=ADVISORY_ONLY,
            evidence_status="UNKNOWN",
            evidence_reason="Default strategy evidence store assumes ADVISORY_ONLY",
        )

DEFAULT_PROFILES = {
    "opening_drive_v1": StrategyParameterProfile(
        strategy_id="opening_drive",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MAX_OPENING_DRIVE_MINUTES": 20,
            "MIN_OPEN_MOVE_PCT": 0.0015,
            "MIN_VWAP_ALIGNMENT_PCT": 0.0005,
        }
    ),
    "opening_range_breakout_v1": StrategyParameterProfile(
        strategy_id="opening_range_breakout",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_RETEST_MINUTES": 15,
            "MAX_RETEST_MINUTES": 90,
            "MAX_RETEST_DISTANCE_PCT": 0.0018,
            "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
        }
    ),
    "compression_breakout_v1": StrategyParameterProfile(
        strategy_id="compression_breakout",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MAX_RANGE_WIDTH_PCT": 0.35,
            "MAX_ATR_RATIO": 0.75,
            "MIN_COMPRESSION_SCORE": 0.5,
            "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
            "MIN_VWAP_ALIGNMENT_PCT": 0.0004,
        }
    ),
    "trend_pullback_v1": StrategyParameterProfile(
        strategy_id="trend_pullback",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_TREND_SCORE": 0.45,
            "MAX_PULLBACK_DISTANCE_PCT": 0.0035,
            "MIN_STRUCTURE_RESUME_PCT": 0.0004,
        }
    ),
    "vwap_reclaim_rejection_v1": StrategyParameterProfile(
        strategy_id="vwap_reclaim_rejection",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_VWAP_DISTANCE_PCT": 0.00035,
            "MAX_VWAP_ENTRY_DISTANCE_PCT": 0.0035,
            "MAX_CHOP_SCORE": 0.55,
        }
    ),
    "failed_breakout_trap_v1": StrategyParameterProfile(
        strategy_id="failed_breakout_trap",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MAX_REENTRY_DISTANCE_PCT": 0.0035,
            "MIN_FAILED_BREAK_DISTANCE_PCT": 0.0006,
            "MIN_TRAP_EVIDENCE_SCORE": 0.45,
        }
    ),
    "exhaustion_reversal_v1": StrategyParameterProfile(
        strategy_id="exhaustion_reversal",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_STRETCH_FROM_VWAP_PCT": 0.005,
            "MAX_ENTRY_STRETCH_PCT": 0.018,
            "MIN_EXHAUSTION_SCORE": 0.5,
            "MAX_CONTINUATION_PRESSURE_SCORE": 0.55,
        }
    ),
    "mean_reversion_extension_v1": StrategyParameterProfile(
        strategy_id="mean_reversion_extension",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_RANGE_OR_CHOP_SCORE": 0.45,
            "MIN_EXTENSION_FROM_VWAP_PCT": 0.0035,
            "MAX_EXTENSION_FROM_VWAP_PCT": 0.014,
            "MAX_TREND_CONTINUATION_SCORE": 0.55,
        }
    ),
    "event_volatility_expansion_v1": StrategyParameterProfile(
        strategy_id="event_volatility_expansion",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_VOL_EXPANSION_SCORE": 0.4,
            "MIN_IMPULSE_FROM_VWAP_PCT": 0.0025,
            "MAX_CHASE_DISTANCE_PCT": 0.014,
            "MIN_VOLUME_Z": 1.2,
            "MIN_ATR_EXPANSION_RATIO": 1.15,
        }
    ),
    "late_day_momentum_v1": StrategyParameterProfile(
        strategy_id="late_day_momentum",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_MINUTES_SINCE_OPEN": 240,
            "MIN_MINUTES_TO_CLOSE": 20,
            "MIN_DIRECTIONAL_SCORE": 0.45,
            "MIN_VWAP_DISTANCE_PCT": 0.002,
            "MAX_CHASE_DISTANCE_PCT": 0.012,
            "MAX_CHOP_SCORE": 0.5,
        }
    ),
    "option_pressure_v1": StrategyParameterProfile(
        strategy_id="option_pressure",
        strategy_version="v1",
        instrument="ANY",
        regime_bucket="ANY",
        session_bucket="ANY",
        expiry_context="ANY",
        volatility_bucket="ANY",
        params={
            "MIN_PRESSURE_SCORE": 0.45,
        }
    ),
}

def get_default_profile(strategy_id: str, version: str = "v1") -> StrategyParameterProfile | None:
    return DEFAULT_PROFILES.get(strategy_id)
