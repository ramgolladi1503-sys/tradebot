from __future__ import annotations

from typing import Any

from config import config as cfg


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(float(lower), min(float(upper), float(value)))


def adjust_threshold(current: float | int | None, impact_score: float | int | None) -> float:
    current_value = float(_safe_float(current, 0.0) or 0.0)
    impact_value = _clamp(float(_safe_float(impact_score, 0.0) or 0.0), -1.0, 1.0)
    max_step_pct = max(
        0.0,
        float(getattr(cfg, "OFFLINE_THRESHOLD_LEARNING_MAX_STEP_PCT", 0.02) or 0.02),
    )
    if impact_value > 0.0:
        adjusted = current_value * (1.0 - max_step_pct)
    elif impact_value < 0.0:
        adjusted = current_value * (1.0 + max_step_pct)
    else:
        adjusted = current_value
    lower = current_value * (1.0 - max_step_pct)
    upper = current_value * (1.0 + max_step_pct)
    return round(_clamp(adjusted, lower, upper), 6)


def score_adjustment_from_impact(impact_score: float | int | None) -> float:
    impact_value = _clamp(float(_safe_float(impact_score, 0.0) or 0.0), -1.0, 1.0)
    max_adjustment = max(
        0.0,
        float(getattr(cfg, "OFFLINE_THRESHOLD_LEARNING_MAX_SCORE_ADJUSTMENT", 0.05) or 0.05),
    )
    return round(_clamp(impact_value * max_adjustment, -max_adjustment, max_adjustment), 6)
