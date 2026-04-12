from __future__ import annotations

from typing import Any


def clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, v))


def capped_adjustment(base_score: float, delta: float, max_abs_delta: float = 0.10) -> float:
    adj = max(-max_abs_delta, min(max_abs_delta, float(delta)))
    return clamp01(float(base_score) + adj)


def calibration_hint(candidate: dict[str, Any]) -> float:
    hint = 0.0
    rr = candidate.get("realized_rr")
    if rr is not None:
        rr = float(rr)
        if rr >= 1.5:
            hint += 0.05
        elif rr <= 0.7:
            hint -= 0.05
    bucket = str(candidate.get("calibration_bucket") or "").strip().lower()
    if bucket == "high":
        hint += 0.02
    elif bucket == "low":
        hint -= 0.02
    return hint


def tune_score(score: float, candidate: dict[str, Any]) -> float:
    return capped_adjustment(score, calibration_hint(candidate), max_abs_delta=0.10)


def annotate_score_tuning(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    base_score = float(out.get("score") or out.get("final_score") or 0.0)
    out["score_before_tuning"] = base_score
    out["score_tuning_delta"] = calibration_hint(out)
    tuned = tune_score(base_score, out)
    out["tuned_score"] = tuned
    return out
