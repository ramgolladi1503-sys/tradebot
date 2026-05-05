from __future__ import annotations

from math import log1p
from typing import Any

from config import config as cfg


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _cfg_float(name: str, default: float) -> float:
    try:
        value = getattr(cfg, name, default)
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def _weighted_average(parts: list[tuple[float | None, float]], *, default: float = 0.0) -> float:
    total_weight = 0.0
    total_score = 0.0
    for value, weight in parts:
        if value is None or weight <= 0.0:
            continue
        total_score += float(value) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0.0:
        return _clamp01(default, default=default)
    return _clamp01(total_score / total_weight, default=default)


def assess_liquidity_quality(
    *,
    volume: Any = None,
    oi: Any = None,
    quote_consistency_score: Any = None,
    quote_ok: Any = True,
    target_volume: float | None = None,
    target_oi: float | None = None,
    volume_cap_mult: float | None = None,
    oi_cap_mult: float | None = None,
    flow_weight: float | None = None,
    book_weight: float | None = None,
) -> dict[str, Any]:
    """
    Smooth liquidity quality that avoids hard saturation on normal live volume.

    This is intentionally conservative: when we have no flow data, we fail to a
    neutral score instead of pretending the book is perfect.
    """
    volume_value = max(_safe_float(volume) or 0.0, 0.0)
    oi_value = max(_safe_float(oi) or 0.0, 0.0)
    quote_ok_bool = bool(quote_ok)
    target_volume_value = max(
        _cfg_float("CANDIDATE_SCORING_LIQUIDITY_TARGET_VOLUME", 25000.0)
        if target_volume is None
        else float(target_volume),
        1.0,
    )
    target_oi_value = max(
        _cfg_float("CANDIDATE_SCORING_LIQUIDITY_TARGET_OI", 50000.0)
        if target_oi is None
        else float(target_oi),
        1.0,
    )
    volume_cap = max(
        _cfg_float("CANDIDATE_SCORING_LIQUIDITY_VOLUME_CAP_MULT", 40.0)
        if volume_cap_mult is None
        else float(volume_cap_mult),
        1.0,
    )
    oi_cap = max(
        _cfg_float("CANDIDATE_SCORING_LIQUIDITY_OI_CAP_MULT", 40.0)
        if oi_cap_mult is None
        else float(oi_cap_mult),
        1.0,
    )
    flow_weight_value = max(
        0.0,
        _cfg_float("CANDIDATE_SCORING_LIQUIDITY_FLOW_WEIGHT", 0.60)
        if flow_weight is None
        else float(flow_weight),
    )
    book_weight_value = max(
        0.0,
        _cfg_float("CANDIDATE_SCORING_LIQUIDITY_BOOK_WEIGHT", 0.40)
        if book_weight is None
        else float(book_weight),
    )

    reasons: list[str] = []
    if volume_value <= 0.0 and oi_value <= 0.0:
        reasons.append("missing_liquidity_context")
        return {
            "liquidity_score": 0.5,
            "liquidity_flow_score": None,
            "liquidity_book_score": _clamp01(quote_consistency_score, default=0.5),
            "liquidity_volume_score": None,
            "liquidity_oi_score": None,
            "liquidity_reasons": reasons,
        }

    volume_score = (
        min(1.0, log1p(volume_value) / log1p(target_volume_value * volume_cap))
        if volume_value > 0.0
        else 0.45
    )
    oi_score = (
        min(1.0, log1p(oi_value) / log1p(target_oi_value * oi_cap))
        if oi_value > 0.0
        else 0.50
    )
    flow_score = _weighted_average([(volume_score, 0.7), (oi_score, 0.3)], default=0.5)
    book_score = _clamp01(quote_consistency_score, default=0.5)
    score = _weighted_average(
        [
            (flow_score, flow_weight_value),
            (book_score, book_weight_value),
        ],
        default=0.5,
    )
    if not quote_ok_bool:
        score *= 0.8
        reasons.append("quote_not_ok")

    return {
        "liquidity_score": _clamp01(score, default=0.5),
        "liquidity_flow_score": _clamp01(flow_score, default=0.5),
        "liquidity_book_score": _clamp01(book_score, default=0.5),
        "liquidity_volume_score": _clamp01(volume_score, default=0.5),
        "liquidity_oi_score": _clamp01(oi_score, default=0.5),
        "liquidity_reasons": reasons,
    }
