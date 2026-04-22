from __future__ import annotations

from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _clamp01(value: float | None, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def score_stock_option_shadow_candidate(
    *,
    symbol: str,
    market_data: dict[str, Any],
    option_row: dict[str, Any],
    strategy_family: str,
    rules: dict[str, Any],
) -> dict[str, float | str | dict[str, float]]:
    spot = _safe_float(option_row.get("spot")) or _safe_float(market_data.get("spot")) or _safe_float(market_data.get("ltp")) or 0.0
    strike = _safe_float(option_row.get("strike")) or 0.0
    spread_pct = _safe_float(option_row.get("spread_pct")) or 999.0
    quote_age_sec = _safe_float(option_row.get("quote_age_sec")) or 999.0
    oi = _safe_float(option_row.get("oi")) or 0.0
    volume = _safe_float(option_row.get("volume")) or 0.0
    max_spread_pct = max(0.01, float(rules.get("max_spread_pct", 1.0) or 1.0))
    max_quote_age_sec = max(0.1, float(rules.get("max_quote_age_sec", 2.5) or 2.5))
    min_oi = max(1.0, float(rules.get("min_oi", 50000.0) or 50000.0))
    min_volume = max(1.0, float(rules.get("min_volume", 10000.0) or 10000.0))

    liquidity_score = _clamp01((0.55 * min(volume / min_volume, 2.0) + 0.45 * min(oi / min_oi, 2.0)) / 2.0, default=0.0)
    spread_score = _clamp01(1.0 - (spread_pct / max_spread_pct), default=0.0)
    freshness_score = _clamp01(1.0 - (quote_age_sec / max_quote_age_sec), default=0.0)
    moneyness_abs = abs(strike - spot)
    moneyness_score = _clamp01(1.0 - (moneyness_abs / max(spot * 0.03, 1.0)), default=0.0)

    vwap = _safe_float(market_data.get("vwap"))
    ltp = _safe_float(market_data.get("ltp")) or spot
    bias = str(market_data.get("bias") or "").strip().lower()
    regime = str(market_data.get("regime") or "").strip().upper()
    option_type = str(option_row.get("option_type") or "").strip().upper()

    directional_alignment = 0.55
    if vwap not in (None, 0.0) and ltp not in (None, 0.0):
        bullish = ltp >= vwap
        if option_type == "CE":
            directional_alignment = 0.78 if bullish else 0.28
        elif option_type == "PE":
            directional_alignment = 0.78 if not bullish else 0.28
    if bias in {"bullish", "bull", "up"}:
        directional_alignment = max(directional_alignment, 0.72 if option_type == "CE" else 0.30)
    elif bias in {"bearish", "bear", "down"}:
        directional_alignment = max(directional_alignment, 0.72 if option_type == "PE" else 0.30)

    regime_score = 0.58
    if regime == "TREND":
        regime_score = 0.74
    elif regime in {"EVENT", "PANIC"}:
        regime_score = 0.35
    elif regime in {"RANGE", "RANGE_VOLATILE"}:
        regime_score = 0.48

    family_bonus = {
        "breakout": 0.04,
        "trend_continuation": 0.06,
        "mean_reversion": -0.02,
        "volatility_expansion": 0.02,
    }.get(str(strategy_family or "").strip().lower(), 0.0)

    confidence = _clamp01(
        (0.28 * liquidity_score)
        + (0.22 * spread_score)
        + (0.15 * freshness_score)
        + (0.15 * moneyness_score)
        + (0.12 * directional_alignment)
        + (0.08 * regime_score)
        + family_bonus,
        default=0.0,
    )
    final_score = _clamp01((0.60 * confidence) + (0.25 * liquidity_score) + (0.15 * freshness_score), default=0.0)

    return {
        "symbol": str(symbol),
        "strategy_family": str(strategy_family),
        "confidence": round(confidence, 4),
        "final_score": round(final_score, 4),
        "components": {
            "liquidity_score": round(liquidity_score, 4),
            "spread_score": round(spread_score, 4),
            "freshness_score": round(freshness_score, 4),
            "moneyness_score": round(moneyness_score, 4),
            "directional_alignment": round(directional_alignment, 4),
            "regime_score": round(regime_score, 4),
        },
    }
