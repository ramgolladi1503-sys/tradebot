from __future__ import annotations

from typing import Any


def _safe_float(value: Any) -> float:
    try:
        if value in (None, "", "None"):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _normalize_regime(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("regime")
        or candidate.get("market_regime")
        or candidate.get("regime_state")
        or candidate.get("market_state")
        or ""
    ).strip().upper()


def select_playbook(candidate: dict[str, Any]) -> str:
    if not isinstance(candidate, dict):
        return "none"

    profile_detected = bool(candidate.get("profile_rejection_detected"))
    breakout_detected = bool(candidate.get("breakout_detected"))
    regime = _normalize_regime(candidate)
    range_regimes = {"RANGE", "RANGE_VOLATILE", "MEAN_REVERT", "SIDEWAYS"}
    trend_regimes = {"TREND", "TREND_STRONG", "VOLATILE_TREND", "MOMENTUM", "BREAKOUT"}

    if regime in range_regimes and profile_detected:
        return "profile_rejection"
    if regime in trend_regimes and breakout_detected:
        return "breakout_continuation"

    if profile_detected and not breakout_detected:
        return "profile_rejection"
    if breakout_detected and not profile_detected:
        return "breakout_continuation"

    if profile_detected and breakout_detected:
        profile_score = max(
            _safe_float(candidate.get("profile_rejection_setup_score")),
            _safe_float(candidate.get("setup_score")),
        )
        breakout_score = max(
            _safe_float(candidate.get("breakout_setup_score")),
            _safe_float(candidate.get("setup_score")),
        )
        if breakout_score > profile_score:
            return "breakout_continuation"
        return "profile_rejection"

    return "none"

