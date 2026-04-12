from __future__ import annotations


def clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, v))


def weighted_score(components: dict[str, float], weights: dict[str, float]) -> float:
    total = 0.0
    weight_sum = 0.0
    for key, value in components.items():
        w = float(weights.get(key, 0.0))
        v = clamp01(value)
        total += v * w
        weight_sum += w
    if weight_sum <= 0:
        return 0.0
    return clamp01(total / weight_sum)


def safe_add(base: float, delta: float, max_boost: float = 0.3) -> float:
    return clamp01(base + max(-max_boost, min(max_boost, delta)))
