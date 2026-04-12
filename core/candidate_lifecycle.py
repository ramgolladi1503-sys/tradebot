from __future__ import annotations

import time
from typing import Any


THESIS_TTL_SECONDS = {
    "breakout_continuation": 120,
    "reclaim_continuation": 180,
    "rejection_reversal": 150,
    "mean_reversion_bounce": 300,
    "mean_reversion_fade": 300,
    "trend_pullback": 240,
    "unknown": 120,
}


def _now() -> float:
    return float(time.time())


def attach_timestamp(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out.setdefault("created_at_epoch", _now())
    return out


def candidate_age_seconds(candidate: dict[str, Any]) -> float:
    created = candidate.get("created_at_epoch")
    if not created:
        return 0.0
    return max(0.0, _now() - float(created))


def is_candidate_stale(candidate: dict[str, Any]) -> bool:
    thesis = str(candidate.get("thesis_type") or "unknown")
    ttl = THESIS_TTL_SECONDS.get(thesis, 120)
    return candidate_age_seconds(candidate) > float(ttl)


def apply_staleness_penalty(score: float, candidate: dict[str, Any]) -> float:
    age = candidate_age_seconds(candidate)
    thesis = str(candidate.get("thesis_type") or "unknown")
    ttl = THESIS_TTL_SECONDS.get(thesis, 120)
    if age <= ttl:
        return score
    decay = min(1.0, (age - ttl) / max(1.0, ttl))
    return score * (1.0 - 0.7 * decay)
