from __future__ import annotations

from typing import Any


def entry_timing_score(candidate: dict[str, Any]) -> float:
    score = 1.0
    extension = float(candidate.get("price_extension_pct") or 0.0)
    reclaim = bool(candidate.get("reclaim_confirmed"))
    candle_close = bool(candidate.get("candle_close_confirmed"))

    if extension > 1.0:
        score -= 0.3
    elif extension > 0.5:
        score -= 0.15

    if reclaim:
        score += 0.1

    if candle_close:
        score += 0.1

    return max(0.0, min(1.0, score))


def annotate_entry_timing(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out["entry_timing_score"] = entry_timing_score(out)
    return out
