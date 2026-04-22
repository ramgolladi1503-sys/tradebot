from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _normalized_confidence(row: dict[str, Any]) -> float:
    confidence = _safe_float(row.get("confidence"))
    if confidence is None:
        return 0.15
    if confidence > 1.0:
        confidence = confidence / 100.0
    return _clamp(confidence)


def _freshness_score(row: dict[str, Any]) -> float:
    age = _safe_float(row.get("quote_age_sec"))
    if age is None:
        return 0.35
    if age <= 3:
        return 1.0
    if age <= 10:
        return 0.85
    if age <= 20:
        return 0.65
    if age <= 45:
        return 0.4
    return 0.15


def _liquidity_score(row: dict[str, Any]) -> float:
    spread_pct = _safe_float(row.get("spread_pct"))
    if spread_pct is None:
        return 0.45
    if spread_pct <= 0.25:
        return 1.0
    if spread_pct <= 0.5:
        return 0.9
    if spread_pct <= 1.0:
        return 0.78
    if spread_pct <= 2.0:
        return 0.58
    if spread_pct <= 4.0:
        return 0.3
    return 0.08


def _risk_reward_score(row: dict[str, Any]) -> float:
    entry = _safe_float(row.get("entry"))
    stop = _safe_float(row.get("stop"))
    target = _safe_float(row.get("target"))
    if entry is None or stop is None or target is None:
        return 0.35
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0:
        return 0.2
    rr = reward / risk
    if rr >= 2.5:
        return 1.0
    if rr >= 2.0:
        return 0.85
    if rr >= 1.5:
        return 0.68
    if rr >= 1.0:
        return 0.48
    return 0.2


def _source_quality_score(row: dict[str, Any]) -> float:
    source = str(row.get("price_source") or "").strip().upper()
    if source in {"ASK", "BID", "LTP", "LIVE", "DEPTH"}:
        return 1.0
    if source in {"CLOSE", "PREV_CLOSE"}:
        return 0.5
    if source in {"REST_FALLBACK", "LAST", "MID", "MARK", "NONE"}:
        return 0.0
    return 0.55


def _candidate_class_score(row: dict[str, Any]) -> float:
    candidate_class = str(row.get("candidate_class") or "").strip().upper()
    if bool(row.get("real_executable")) or candidate_class == "EXECUTABLE":
        return 1.0
    if candidate_class == "WATCHLIST":
        return 0.6
    return 0.25


def _compute_score_components(row: dict[str, Any]) -> dict[str, float]:
    return {
        "confidence": _normalized_confidence(row),
        "freshness": _freshness_score(row),
        "liquidity": _liquidity_score(row),
        "risk_reward": _risk_reward_score(row),
        "source_quality": _source_quality_score(row),
        "candidate_class": _candidate_class_score(row),
    }


def score_row(row: dict[str, Any]) -> dict[str, Any]:
    components = _compute_score_components(row)
    score = (
        components["confidence"] * 0.34
        + components["liquidity"] * 0.20
        + components["freshness"] * 0.16
        + components["risk_reward"] * 0.14
        + components["source_quality"] * 0.10
        + components["candidate_class"] * 0.06
    )
    score = _clamp(score)
    ranked = dict(row)
    ranked["ranking_score"] = round(score, 4)
    ranked["ranking_components"] = {k: round(v, 4) for k, v in components.items()}
    if score >= 0.8:
        ranked["ranking_tier"] = "A"
    elif score >= 0.65:
        ranked["ranking_tier"] = "B"
    elif score >= 0.5:
        ranked["ranking_tier"] = "C"
    else:
        ranked["ranking_tier"] = "D"
    return ranked


def rank_rows(rows: list[dict[str, Any]], *, top_n: int | None = None) -> list[dict[str, Any]]:
    ranked = [score_row(row) for row in rows if isinstance(row, dict)]
    ranked.sort(
        key=lambda row: (
            float(row.get("ranking_score") or 0.0),
            1 if bool(row.get("real_executable")) else 0,
            float(_safe_float(row.get("confidence")) or 0.0),
        ),
        reverse=True,
    )
    if top_n is not None:
        return ranked[: max(1, int(top_n))]
    return ranked


def allocate_capital(rows: list[dict[str, Any]], *, top_n: int = 3) -> list[dict[str, Any]]:
    selected = rank_rows(rows, top_n=top_n)
    total = sum(max(float(row.get("ranking_score") or 0.0), 0.0) for row in selected)
    if total <= 0:
        even = round(1.0 / max(len(selected), 1), 4)
        out = []
        for row in selected:
            item = dict(row)
            item["capital_fraction"] = even
            out.append(item)
        return out
    out = []
    for row in selected:
        item = dict(row)
        item["capital_fraction"] = round(max(float(item.get("ranking_score") or 0.0), 0.0) / total, 4)
        out.append(item)
    return out
