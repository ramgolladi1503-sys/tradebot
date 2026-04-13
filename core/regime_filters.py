from __future__ import annotations

from typing import Dict, Any
from core.setup_types import RegimeDecision


def evaluate_regime(candidate: Dict[str, Any]) -> RegimeDecision:
    regime = str(candidate.get("regime") or "").upper()
    countertrend = bool(candidate.get("countertrend", False))

    reasons = []
    allow = True

    if regime in {"EVENT", "PANIC"}:
        allow = False
        reasons.append("hostile_regime")

    if regime == "TREND" and countertrend:
        allow = False
        reasons.append("countertrend_trend_day")

    return RegimeDecision(
        allow_mean_reversion=allow,
        regime=regime or "UNKNOWN",
        confidence=0.7 if allow else 0.3,
        reasons=reasons,
    )
