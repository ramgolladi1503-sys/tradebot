from __future__ import annotations

from typing import Any


def detect_state(context: dict[str, Any]) -> str:
    volatility = float(context.get("volatility", 0.0))
    trend = float(context.get("trend_strength", 0.0))

    if volatility < 0.3 and trend < 0.3:
        return "range"
    if volatility > 0.6 and trend > 0.5:
        return "expansion"
    if trend > 0.5 and volatility < 0.5:
        return "trend"
    if volatility > 0.5 and trend < 0.3:
        return "chop"
    return "neutral"


def transition_bias(prev_state: str, current_state: str) -> float:
    if prev_state == "range" and current_state == "expansion":
        return 0.2
    if prev_state == "expansion" and current_state == "range":
        return -0.2
    return 0.0
