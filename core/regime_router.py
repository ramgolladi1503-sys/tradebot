from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


_CANONICAL_REGIMES = {"TRENDING_UP", "TRENDING_DOWN", "RANGE", "VOLATILE", "EXPIRY_CONTEXT"}

# Strategy thresholds moved to strategies / core.strategy_profiles


def _normalize_bias(bias: Any) -> str | None:
    if not isinstance(bias, str):
        return None
    text = bias.strip().lower()
    if text in {"bullish", "bull", "long", "up"}:
        return "bullish"
    if text in {"bearish", "bear", "short", "down"}:
        return "bearish"
    return None


from core.events import append_event

_last_regime_emitted = None

def resolve_strategy_regime(raw_regime: Any, *, bias: Any = None, expiry_context: bool = False) -> str:
    global _last_regime_emitted
    
    def _resolve() -> str:
        if expiry_context:
            return "EXPIRY_CONTEXT"
        text = str(raw_regime or "").strip().upper()
        if text in _CANONICAL_REGIMES:
            return text
        if text in {"EXPIRY_DAY", "EXPIRY_CONTEXT"}:
            return "EXPIRY_CONTEXT"
        if text in {"VOLATILE", "RANGE_VOLATILE", "EVENT", "PANIC", "UNSTABLE"}:
            return "VOLATILE"
        if text in {"RANGE", "RANGE_DAY"}:
            return "RANGE"
        bias_norm = _normalize_bias(bias)
        if text in {"TREND", "TREND_DAY", "TREND_RANGE_DAY", "RANGE_TREND_DAY", "TRENDING_DOWN", "TRENDING_UP"}:
            if bias_norm == "bearish":
                return "TRENDING_DOWN"
            if bias_norm == "bullish":
                return "TRENDING_UP"
            return "UNKNOWN"
            
        return "UNKNOWN"
        
    regime = _resolve()
    
    if _last_regime_emitted is not None and _last_regime_emitted != regime:
        append_event("regime_transition", {
            "previous_regime": _last_regime_emitted,
            "new_regime": regime,
            "raw_input": str(raw_regime),
            "bias_input": str(bias),
        })
        logger.info("regime_transition previous=%s new=%s", _last_regime_emitted, regime)
        
    _last_regime_emitted = regime
    return regime


# get_strategy_regime_profile has been moved out of this module

def record_strategy_regime_path(
    strategy_name: str,
    regime: str,
    profile: dict[str, Any],
    *,
    debug_stats: dict[str, Any] | None = None,
) -> None:
    payload = {
        "strategy": str(strategy_name),
        "regime": str(regime),
        "setup_family": str(profile.get("setup_family") or ""),
        "variant": str(profile.get("variant") or ""),
        "score_bias": float(profile.get("score_bias") or 0.0),
        "vwap_buffer_mult": float(profile.get("vwap_buffer_mult") or 1.0),
        "min_move_mult": float(profile.get("min_move_mult") or 1.0),
    }
    if isinstance(debug_stats, dict):
        debug_stats["regime_path"] = payload
    logger.info(
        "strategy_regime_path strategy=%s regime=%s setup_family=%s variant=%s score_bias=%.3f vwap_buffer_mult=%.3f min_move_mult=%.3f",
        payload["strategy"],
        payload["regime"],
        payload["setup_family"],
        payload["variant"],
        payload["score_bias"],
        payload["vwap_buffer_mult"],
        payload["min_move_mult"],
    )
