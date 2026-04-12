from __future__ import annotations

from typing import Any


def strike_preference(candidate: dict[str, Any]) -> str:
    thesis = str(candidate.get("thesis_type") or "unknown")
    if thesis in {"breakout_continuation", "reclaim_continuation"}:
        return "ATM_or_slight_OTM"
    if thesis in {"mean_reversion_bounce", "mean_reversion_fade", "trend_pullback"}:
        return "ATM_or_slight_ITM"
    return "ATM"


def premium_band(candidate: dict[str, Any]) -> str:
    premium = float(candidate.get("opt_ltp") or candidate.get("current_ltp") or 0.0)
    if premium < 50:
        return "too_cheap"
    if premium > 300:
        return "too_expensive"
    return "acceptable"


def strike_score(candidate: dict[str, Any]) -> float:
    score = 1.0
    band = premium_band(candidate)
    if band == "too_cheap":
        score -= 0.2
    elif band == "too_expensive":
        score -= 0.1
    pref = strike_preference(candidate)
    actual = str(candidate.get("moneyness_bucket") or "").lower()
    if pref == "ATM_or_slight_OTM" and actual not in {"atm", "slightly_otm"}:
        score -= 0.2
    if pref == "ATM_or_slight_ITM" and actual not in {"atm", "slightly_itm"}:
        score -= 0.2
    return max(0.0, min(1.0, score))


def annotate_strike(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out["strike_preference"] = strike_preference(out)
    out["strike_score"] = strike_score(out)
    return out
