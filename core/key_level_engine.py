from __future__ import annotations

from typing import Any


def level_proximity_penalty(price: float, levels: list[float], threshold: float = 20.0) -> float:
    if not levels:
        return 0.0
    min_dist = min(abs(price - lvl) for lvl in levels)
    if min_dist > threshold:
        return 0.0
    return max(0.0, 1.0 - (min_dist / threshold))


def level_context_score(price: float, context: dict[str, Any]) -> float:
    resistance = context.get("resistance_levels", [])
    support = context.get("support_levels", [])

    penalty = level_proximity_penalty(price, resistance)
    boost = level_proximity_penalty(price, support)

    return boost - penalty
