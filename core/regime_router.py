from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


_CANONICAL_REGIMES = {"TRENDING_UP", "TRENDING_DOWN", "RANGE", "VOLATILE", "EXPIRY_CONTEXT"}

_BASE_PROFILES = {
    "TRENDING_UP": {
        "setup_family": "BREAKOUT",
        "vwap_buffer_mult": 0.90,
        "min_move_mult": 0.90,
        "score_bias": 0.05,
        "range_reversion": False,
        "trend_conflict_mult": 1.40,
    },
    "TRENDING_DOWN": {
        "setup_family": "BREAKOUT",
        "vwap_buffer_mult": 0.90,
        "min_move_mult": 0.90,
        "score_bias": 0.05,
        "range_reversion": False,
        "trend_conflict_mult": 1.40,
    },
    "RANGE": {
        "setup_family": "MEAN_REVERSION",
        "vwap_buffer_mult": 1.15,
        "min_move_mult": 0.80,
        "score_bias": -0.02,
        "range_reversion": True,
        "range_extension_mult": 1.15,
    },
    "VOLATILE": {
        "setup_family": "CONTINUATION",
        "vwap_buffer_mult": 1.25,
        "min_move_mult": 1.20,
        "score_bias": -0.04,
        "range_reversion": False,
        "strict_move_mult": 1.15,
    },
    "EXPIRY_CONTEXT": {
        "setup_family": "PULLBACK",
        "vwap_buffer_mult": 1.00,
        "min_move_mult": 0.85,
        "score_bias": 0.00,
        "range_reversion": False,
    },
}

_STRATEGY_OVERRIDES = {
    "banknifty_intraday": {
        "VOLATILE": {"vwap_buffer_mult": 1.35, "min_move_mult": 1.25},
        "RANGE": {"range_extension_mult": 1.20},
    },
    "sensex_intraday": {
        "RANGE": {"score_bias": -0.01},
        "EXPIRY_CONTEXT": {"score_bias": 0.02},
    },
    "zero_hero": {
        "EXPIRY_CONTEXT": {
            "variant": "expiry_context",
            "entry_price_mult": 0.005,
            "premium_floor": 25.0,
            "target_mult": 2.0,
            "stop_loss_mult": 0.80,
            "confidence": 60,
            "confidence_reason": "expiry_window_manual_advisory",
        },
        "TRENDING_UP": {
            "variant": "non_expiry_context",
            "entry_price_mult": 0.0035,
            "premium_floor": 15.0,
            "target_mult": 1.6,
            "stop_loss_mult": 0.85,
            "confidence": 46,
            "confidence_reason": "non_expiry_manual_advisory",
        },
        "TRENDING_DOWN": {
            "variant": "non_expiry_context",
            "entry_price_mult": 0.0035,
            "premium_floor": 15.0,
            "target_mult": 1.6,
            "stop_loss_mult": 0.85,
            "confidence": 46,
            "confidence_reason": "non_expiry_manual_advisory",
        },
        "VOLATILE": {
            "variant": "non_expiry_context",
            "entry_price_mult": 0.0030,
            "premium_floor": 18.0,
            "target_mult": 1.5,
            "stop_loss_mult": 0.88,
            "confidence": 42,
            "confidence_reason": "non_expiry_volatile_manual_advisory",
        },
    },
}


def _normalize_bias(bias: Any) -> str | None:
    if not isinstance(bias, str):
        return None
    text = bias.strip().lower()
    if text in {"bullish", "bull", "long", "up"}:
        return "bullish"
    if text in {"bearish", "bear", "short", "down"}:
        return "bearish"
    return None


def resolve_strategy_regime(raw_regime: Any, *, bias: Any = None, expiry_context: bool = False) -> str:
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
        return "TRENDING_DOWN" if bias_norm == "bearish" else "TRENDING_UP"
    return "TRENDING_DOWN" if bias_norm == "bearish" else "TRENDING_UP"


def get_strategy_regime_profile(strategy_name: str, regime: str) -> dict[str, Any]:
    regime_name = str(regime or "TRENDING_UP").strip().upper()
    profile = dict(_BASE_PROFILES.get(regime_name, _BASE_PROFILES["TRENDING_UP"]))
    strategy_overrides = _STRATEGY_OVERRIDES.get(str(strategy_name or "").strip().lower(), {})
    profile.update(dict(strategy_overrides.get(regime_name, {})))
    profile["regime"] = regime_name
    return profile


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
