from __future__ import annotations

from typing import Dict, Any


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def evaluate_breakout_continuation_setup(candidate: Dict[str, Any]) -> Dict[str, Any]:
    current_price = _safe_float(candidate.get("current_price") or candidate.get("last_price") or candidate.get("entry")) or 0.0
    breakout_level = _safe_float(candidate.get("breakout_level") or candidate.get("orb_high") or candidate.get("day_high"))
    candle = dict(candidate.get("latest_candle") or {})
    regime = str(candidate.get("regime") or "").upper()

    if breakout_level is None:
        return {
            "detected": False,
            "direction": "BUY",
            "setup_score": 0.0,
            "trigger_score": 0.0,
            "entry_quality_score": 0.0,
            "rr": 0.0,
            "entry": current_price,
            "stop": current_price,
            "target": current_price,
            "reasons": ["no_breakout_level"],
            "telemetry": {},
        }

    open_ = _safe_float(candle.get("open")) or current_price
    close = _safe_float(candle.get("close")) or current_price
    high = _safe_float(candle.get("high")) or current_price
    low = _safe_float(candle.get("low")) or current_price

    closes_above = 1.0 if close > breakout_level else 0.0
    body_strength = max(0.0, close - open_)
    candle_range = max(high - low, 1e-6)
    trigger_score = min(1.0, (body_strength / candle_range)) * closes_above

    regime_score = 1.0 if regime in {"TREND", "TRENDING", "RANGE_VOLATILE"} else 0.4
    level_score = 1.0 if current_price >= breakout_level else 0.0

    stop = low
    target = current_price + max(current_price - stop, 0.0) * 2.0
    rr = abs(target - current_price) / max(abs(current_price - stop), 1e-6)
    entry_quality_score = min(1.0, rr / 2.5)

    setup_score = (
        0.30 * level_score
        + 0.30 * trigger_score
        + 0.20 * regime_score
        + 0.20 * entry_quality_score
    )

    detected = bool(
        closes_above > 0.5
        and trigger_score > 0.35
        and rr >= 1.5
    )

    return {
        "detected": detected,
        "direction": "BUY",
        "setup_score": float(setup_score),
        "trigger_score": float(trigger_score),
        "entry_quality_score": float(entry_quality_score),
        "rr": float(rr),
        "entry": float(current_price),
        "stop": float(stop),
        "target": float(target),
        "reasons": [] if detected else ["weak_breakout_continuation"],
        "telemetry": {
            "breakout_level": breakout_level,
            "close": close,
            "trigger_score": trigger_score,
            "regime": regime,
            "rr": rr,
        },
    }
