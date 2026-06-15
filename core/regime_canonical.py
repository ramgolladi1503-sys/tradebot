from __future__ import annotations

from typing import Any


ROUTER_CANONICAL_REGIMES: tuple[str, ...] = (
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGE",
    "VOLATILE",
    "EXPIRY_CONTEXT",
    "UNKNOWN",
)

LEGACY_REGIME_BUCKETS: tuple[str, ...] = ("TREND", "RANGE", "EVENT", "NEUTRAL")


def normalize_bias(bias: Any) -> str | None:
    if not isinstance(bias, str):
        return None
    text = bias.strip().lower()
    if text in {"bullish", "bull", "long", "up"}:
        return "bullish"
    if text in {"bearish", "bear", "short", "down"}:
        return "bearish"
    return None


def resolve_strategy_regime_label(
    raw_regime: Any,
    *,
    bias: Any = None,
    expiry_context: bool = False,
) -> str:
    if expiry_context:
        return "EXPIRY_CONTEXT"

    text = str(raw_regime or "").strip().upper()
    if not text:
        return "UNKNOWN"
    if text in ROUTER_CANONICAL_REGIMES:
        return text
    if text in {"EXPIRY_DAY", "EXPIRY_CONTEXT"}:
        return "EXPIRY_CONTEXT"
    if text in {"TREND_UP", "TRENDING_UP"}:
        return "TRENDING_UP"
    if text in {"TREND_DOWN", "TRENDING_DOWN"}:
        return "TRENDING_DOWN"
    if text in {"RANGE", "RANGE_DAY", "CHOP", "COMPRESSION"}:
        return "RANGE"
    if text in {
        "VOLATILE",
        "RANGE_VOLATILE",
        "EVENT",
        "PANIC",
        "UNSTABLE",
        "VOLATILITY_EXPANSION",
        "TRAP_RISK",
        "EXHAUSTION_RISK",
    }:
        return "VOLATILE"
    if text in {"INCONCLUSIVE", "UNKNOWN"}:
        return "UNKNOWN"
    if text in {"TREND", "TREND_DAY", "TREND_RANGE_DAY", "RANGE_TREND_DAY"}:
        bias_norm = normalize_bias(bias)
        if bias_norm == "bearish":
            return "TRENDING_DOWN"
        if bias_norm == "bullish":
            return "TRENDING_UP"
        return "UNKNOWN"
    return "UNKNOWN"


def normalize_legacy_regime_bucket(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"TREND", "TREND_DAY", "TREND_UP", "TREND_DOWN", "TRENDING_UP", "TRENDING_DOWN"}:
        return "TREND"
    if text in {"RANGE", "RANGE_DAY", "CHOP", "COMPRESSION", "MEAN_REVERT", "MEANREVERT"}:
        return "RANGE"
    if text in {
        "EVENT",
        "PANIC",
        "VOLATILE",
        "RANGE_VOLATILE",
        "UNSTABLE",
        "VOLATILITY_EXPANSION",
        "TRAP_RISK",
        "EXHAUSTION_RISK",
        "EXPIRY_CONTEXT",
        "EXPIRY_DAY",
    }:
        return "EVENT"
    return "NEUTRAL"


__all__ = [
    "LEGACY_REGIME_BUCKETS",
    "ROUTER_CANONICAL_REGIMES",
    "normalize_bias",
    "normalize_legacy_regime_bucket",
    "resolve_strategy_regime_label",
]
