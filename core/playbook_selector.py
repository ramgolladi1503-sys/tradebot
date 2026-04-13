from __future__ import annotations

from typing import Dict, Any


def select_playbook(candidate: Dict[str, Any]) -> str:
    regime = str(candidate.get("regime") or "").upper()

    profile_detected = bool(candidate.get("profile_rejection_detected"))
    breakout_signal = candidate.get("breakout_signal") or candidate.get("breakout_level")

    # Mean reversion preferred in range
    if regime == "RANGE" and profile_detected:
        return "profile_rejection"

    # Breakout preferred in trend
    if regime in {"TREND", "TRENDING"} and breakout_signal:
        return "breakout_continuation"

    # fallback
    if profile_detected:
        return "profile_rejection"

    if breakout_signal:
        return "breakout_continuation"

    return "none"
