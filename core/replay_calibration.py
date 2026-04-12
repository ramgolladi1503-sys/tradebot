from __future__ import annotations

from typing import Any


def calibration_bucket(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def calibrate_score(score: float, realized_rr: float | None) -> float:
    if realized_rr is None:
        return score
    if realized_rr > 1.5:
        return min(1.0, score + 0.05)
    if realized_rr < 0.7:
        return max(0.0, score - 0.05)
    return score


def annotate_replay(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    score = float(out.get("score", 0.0))
    out["calibration_bucket"] = calibration_bucket(score)
    return out
