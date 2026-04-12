from __future__ import annotations

from typing import Any


THESIS_BREAKOUT_CONTINUATION = "breakout_continuation"
THESIS_RECLAIM_CONTINUATION = "reclaim_continuation"
THESIS_REJECTION_REVERSAL = "rejection_reversal"
THESIS_MEAN_REVERSION_BOUNCE = "mean_reversion_bounce"
THESIS_MEAN_REVERSION_FADE = "mean_reversion_fade"
THESIS_TREND_PULLBACK = "trend_pullback"
THESIS_UNKNOWN = "unknown"


THESIS_ALIASES = {
    "breakout_momentum": THESIS_BREAKOUT_CONTINUATION,
    "or_breakout_followthrough": THESIS_BREAKOUT_CONTINUATION,
    "reclaim_continuation": THESIS_RECLAIM_CONTINUATION,
    "reject_continuation": THESIS_REJECTION_REVERSAL,
    "mean_reversion_long": THESIS_MEAN_REVERSION_BOUNCE,
    "mean_reversion_short": THESIS_MEAN_REVERSION_FADE,
    "pullback_trend": THESIS_TREND_PULLBACK,
    "pullback_trend_short": THESIS_TREND_PULLBACK,
    "builder_soft_reject": THESIS_UNKNOWN,
}


def standardize_thesis(candidate: dict[str, Any]) -> str:
    explicit = str(candidate.get("thesis_type") or "").strip().lower()
    if explicit:
        return explicit

    for key in ("strategy_name", "strategy_family", "setup_family", "candidate_origin"):
        value = str(candidate.get(key) or "").strip().lower()
        if value in THESIS_ALIASES:
            return THESIS_ALIASES[value]
        if "breakout" in value:
            return THESIS_BREAKOUT_CONTINUATION
        if "reclaim" in value:
            return THESIS_RECLAIM_CONTINUATION
        if "reject" in value:
            return THESIS_REJECTION_REVERSAL
        if "mean_reversion" in value:
            return THESIS_MEAN_REVERSION_BOUNCE if "long" in value else THESIS_MEAN_REVERSION_FADE
        if "pullback" in value:
            return THESIS_TREND_PULLBACK
    return THESIS_UNKNOWN


def annotate_thesis(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out["thesis_type"] = standardize_thesis(out)
    return out
