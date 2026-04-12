from __future__ import annotations

from typing import Any


def alignment_score(mtf_context: dict[str, Any]) -> float:
    short = float(mtf_context.get("1m_bias", 0.0))
    mid = float(mtf_context.get("5m_bias", 0.0))
    long = float(mtf_context.get("15m_bias", 0.0))

    score = 0.0
    if short * mid > 0:
        score += 0.4
    if mid * long > 0:
        score += 0.4
    if short * long > 0:
        score += 0.2

    return max(0.0, min(1.0, score))


def downgrade_if_conflict(score: float, mtf_context: dict[str, Any]) -> float:
    align = alignment_score(mtf_context)
    if align < 0.3:
        return score * 0.5
    if align < 0.6:
        return score * 0.8
    return score
