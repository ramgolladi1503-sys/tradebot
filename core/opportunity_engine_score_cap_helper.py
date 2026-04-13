from __future__ import annotations

from typing import Any


def score_cap_for_candidate_class(candidate_class: str) -> float | None:
    caps = {
        "fallback": 0.39,
        "planning_only": 0.34,
        "synthetic": 0.36,
        "softened": 0.44,
        "advisory": 0.44,
    }
    return caps.get(str(candidate_class or "").strip().lower())


def apply_candidate_class_score_cap(score: float, candidate_class: str) -> tuple[float, float | None]:
    cap = score_cap_for_candidate_class(candidate_class)
    if cap is None:
        return float(score), None
    return min(float(score), float(cap)), float(cap)


def enrich_score_payload(payload: dict[str, Any], candidate_class: str) -> dict[str, Any]:
    score = float(payload.get("opportunity_score") or 0.0)
    capped_score, class_score_cap = apply_candidate_class_score_cap(score, candidate_class)
    out = dict(payload)
    out["candidate_class"] = str(candidate_class or "").strip().lower()
    out["class_score_cap"] = class_score_cap
    out["opportunity_score"] = capped_score
    return out
