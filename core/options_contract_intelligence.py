from __future__ import annotations

from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def spread_pct(candidate: dict[str, Any]) -> float | None:
    value = _safe_float(candidate.get("spread_pct"))
    if value is not None:
        return max(0.0, value)
    bid = _safe_float(candidate.get("best_bid"))
    ask = _safe_float(candidate.get("best_ask"))
    ltp = _safe_float(candidate.get("opt_ltp")) or _safe_float(candidate.get("current_ltp"))
    if bid is None or ask is None or ltp in (None, 0.0):
        return None
    return max(0.0, (ask - bid) / max(ltp, 1e-9))


def option_quality_score(candidate: dict[str, Any]) -> float:
    score = 1.0
    sp = spread_pct(candidate)
    oi = _safe_float(candidate.get("oi")) or _safe_float(candidate.get("open_interest")) or 0.0
    premium = _safe_float(candidate.get("opt_ltp")) or _safe_float(candidate.get("current_ltp")) or 0.0
    iv = _safe_float(candidate.get("iv")) or 0.0
    if sp is None:
        score -= 0.15
    elif sp > 0.015:
        score -= 0.35
    elif sp > 0.010:
        score -= 0.20
    if oi < 1000:
        score -= 0.20
    if premium < 60:
        score -= 0.10
    if premium > 300:
        score -= 0.05
    if iv > 40:
        score -= 0.10
    return max(0.0, min(1.0, score))


def select_contract_bucket(candidate: dict[str, Any]) -> str:
    moneyness = str(candidate.get("moneyness_bucket") or candidate.get("moneyness") or "").strip().lower()
    thesis = str(candidate.get("thesis_type") or "unknown")
    if thesis in {"breakout_continuation", "reclaim_continuation"}:
        if moneyness in {"atm", "slightly_otm", "near_atm"}:
            return "preferred"
        return "acceptable"
    if thesis in {"mean_reversion_bounce", "mean_reversion_fade", "trend_pullback"}:
        if moneyness in {"atm", "slightly_itm", "near_atm"}:
            return "preferred"
        return "acceptable"
    return "unknown"


def annotate_option_intelligence(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out["option_quality_score"] = option_quality_score(out)
    out["contract_bucket"] = select_contract_bucket(out)
    return out
