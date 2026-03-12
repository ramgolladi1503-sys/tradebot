from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from config import config as cfg


_HOSTILE_REGIMES = {"EVENT", "PANIC"}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _get_value(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _candidate_detail(candidate: Any) -> dict[str, Any]:
    detail = _get_value(candidate, "trade_score_detail", {}) or {}
    return detail if isinstance(detail, dict) else {}


def _clamp01(value: float | None, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    return max(0.0, min(1.0, float(value)))


def _weighted_average(parts: list[tuple[float | None, float]]) -> float:
    total_weight = 0.0
    total_score = 0.0
    for value, weight in parts:
        if value is None or weight <= 0:
            continue
        total_score += float(value) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        return 0.0
    return _clamp01(total_score / total_weight, default=0.0) or 0.0


def _liquidity_quality(candidate: Any) -> float:
    volume = max(_safe_float(_get_value(candidate, "volume")) or 0.0, _safe_float(_get_value(candidate, "current_volume")) or 0.0)
    min_volume = max(float(getattr(cfg, "MIN_VOLUME_FILTER", 1.0) or 1.0), 1.0)
    volume_score = min(1.0, volume / min_volume) if volume > 0 else 0.35
    quote_ok = bool(_get_value(candidate, "quote_ok", True))
    if not quote_ok:
        volume_score *= 0.65
    return _clamp01(volume_score, default=0.35) or 0.35


def _spread_quality(candidate: Any) -> float:
    spread_pct = _safe_float(_get_value(candidate, "spread_pct"))
    max_spread = max(float(getattr(cfg, "MAX_SPREAD_PCT", 0.02) or 0.02), 1e-6)
    if spread_pct is None:
        bid = _safe_float(_get_value(candidate, "best_bid"))
        ask = _safe_float(_get_value(candidate, "best_ask"))
        ltp = _safe_float(_get_value(candidate, "opt_ltp")) or _safe_float(_get_value(candidate, "current_ltp"))
        if bid is not None and ask is not None and ltp not in (None, 0):
            spread_pct = max(0.0, ask - bid) / max(float(ltp), 1e-6)
    if spread_pct is None:
        return 0.5
    return _clamp01(1.0 - min(float(spread_pct) / max_spread, 1.0), default=0.0) or 0.0


def _freshness_quality(candidate: Any) -> float:
    quote_age = _safe_float(_get_value(candidate, "quote_age_sec"))
    max_age = max(float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0) or 2.0), 1e-6)
    if quote_age is None:
        return 0.5
    return _clamp01(1.0 - min(float(quote_age) / max_age, 1.0), default=0.0) or 0.0


def _regime_alignment(candidate: Any) -> float:
    regime = str(_get_value(candidate, "regime") or "").strip().upper()
    countertrend = bool(_get_value(candidate, "countertrend", False))
    if countertrend:
        return 0.35
    if regime in _HOSTILE_REGIMES:
        return 0.45
    if regime in {"TREND", "RANGE", "RANGE_VOLATILE"}:
        return 0.8
    return 0.65


def _adaptive_execution_threshold(candidate: Any) -> float:
    base = float(getattr(cfg, "OPPORTUNITY_EXECUTION_SCORE_BASE", 0.52))
    threshold = base
    if _liquidity_quality(candidate) >= float(getattr(cfg, "OPPORTUNITY_STRONG_LIQUIDITY_THRESHOLD", 0.80)):
        threshold -= float(getattr(cfg, "OPPORTUNITY_EXECUTION_LIQUIDITY_BONUS", 0.03))
    if str(_get_value(candidate, "regime") or "").strip().upper() in _HOSTILE_REGIMES:
        threshold += float(getattr(cfg, "OPPORTUNITY_EXECUTION_HOSTILE_REGIME_PENALTY", 0.05))
    if bool(_get_value(candidate, "countertrend", False)):
        threshold += float(getattr(cfg, "OPPORTUNITY_EXECUTION_COUNTERTREND_PENALTY", 0.04))
    return _clamp01(threshold, default=base) or base


def build_opportunity_score(candidate: Any) -> dict[str, Any]:
    detail = _candidate_detail(candidate)
    builder_confidence = _clamp01(
        _safe_float(_get_value(candidate, "builder_confidence"))
        or _safe_float(_get_value(candidate, "confidence_model_raw"))
        or _safe_float(_get_value(candidate, "confidence")),
        default=0.0,
    ) or 0.0
    permission_confidence = _clamp01(
        _safe_float(_get_value(candidate, "permission_confidence"))
        or _safe_float(_get_value(candidate, "global_confidence")),
        default=builder_confidence,
    )
    gating_confidence = _clamp01(
        _safe_float(_get_value(candidate, "gating_final_confidence"))
        or _safe_float(_get_value(candidate, "confidence_final"))
        or _safe_float(_get_value(candidate, "confidence_after_soft_veto")),
        default=builder_confidence,
    )
    confluence_score = _clamp01(
        _safe_float(_get_value(candidate, "sizing_confluence_score"))
        or _safe_float(detail.get("confluence_score"))
        or _safe_float(_get_value(candidate, "trade_alignment")),
        default=0.5,
    )
    spread_quality = _spread_quality(candidate)
    liquidity_quality = _liquidity_quality(candidate)
    freshness_quality = _freshness_quality(candidate)
    regime_alignment = _regime_alignment(candidate)
    score = _weighted_average(
        [
            (builder_confidence, float(getattr(cfg, "OPPORTUNITY_WEIGHT_BUILDER_CONFIDENCE", 0.32))),
            (permission_confidence, float(getattr(cfg, "OPPORTUNITY_WEIGHT_PERMISSION_CONFIDENCE", 0.12))),
            (gating_confidence, float(getattr(cfg, "OPPORTUNITY_WEIGHT_GATING_CONFIDENCE", 0.18))),
            (confluence_score, float(getattr(cfg, "OPPORTUNITY_WEIGHT_CONFLUENCE", 0.16))),
            (regime_alignment, float(getattr(cfg, "OPPORTUNITY_WEIGHT_REGIME_ALIGNMENT", 0.08))),
            (liquidity_quality, float(getattr(cfg, "OPPORTUNITY_WEIGHT_LIQUIDITY", 0.07))),
            (spread_quality, float(getattr(cfg, "OPPORTUNITY_WEIGHT_SPREAD", 0.04))),
            (freshness_quality, float(getattr(cfg, "OPPORTUNITY_WEIGHT_FRESHNESS", 0.03))),
        ]
    )
    return {
        "builder_confidence": builder_confidence,
        "permission_confidence": permission_confidence,
        "gating_final_confidence": gating_confidence,
        "confluence_score": confluence_score,
        "regime_alignment": regime_alignment,
        "liquidity_quality": liquidity_quality,
        "spread_quality": spread_quality,
        "freshness_quality": freshness_quality,
        "opportunity_score": score,
        "adaptive_execution_threshold": _adaptive_execution_threshold(candidate),
        "survival_floor": float(getattr(cfg, "OPPORTUNITY_SURVIVAL_SCORE_FLOOR", 0.35)),
    }


def derive_opportunity_size_multiplier(candidate: Any, rank_context: dict[str, Any]) -> tuple[float, str]:
    score = float(rank_context.get("opportunity_score") or 0.0)
    floor = float(rank_context.get("survival_floor") or getattr(cfg, "OPPORTUNITY_SURVIVAL_SCORE_FLOOR", 0.35))
    if score <= floor:
        return 0.0, "below_survival_floor"
    quality_span = max(1e-6, 1.0 - floor)
    quality_scale = max(0.0, min(1.0, (score - floor) / quality_span))
    rank = max(1, int(rank_context.get("opportunity_rank") or 1))
    rank_decay = max(0.0, float(getattr(cfg, "OPPORTUNITY_RANK_SIZE_DECAY", 0.20)))
    rank_scale = max(
        float(getattr(cfg, "OPPORTUNITY_SIZE_MIN_MULT", 0.25)),
        1.0 - (rank_decay * float(rank - 1)),
    )
    minimum = float(getattr(cfg, "OPPORTUNITY_SIZE_MIN_MULT", 0.25))
    multiplier = max(minimum, minimum + ((1.0 - minimum) * quality_scale))
    multiplier *= rank_scale
    multiplier = max(0.0, min(1.0, multiplier))
    reason = f"score={score:.3f};rank={rank};quality_scale={quality_scale:.3f};rank_scale={rank_scale:.3f}"
    return multiplier, reason


def annotate_ranked_opportunities(
    candidates: Iterable[Any],
    *,
    scope: str,
    top_n: int | None = None,
) -> list[Any]:
    candidate_list = list(candidates or [])
    if not candidate_list:
        return []
    if not bool(getattr(cfg, "OPPORTUNITY_ENGINE_ENABLE", True)):
        return candidate_list
    executable_top_n = max(1, int(top_n or getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)))
    scored: list[tuple[tuple[int, float, float], Any, dict[str, Any]]] = []
    for candidate in candidate_list:
        metrics = build_opportunity_score(candidate)
        execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
        tradable = bool(_get_value(candidate, "tradable", False))
        execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
        execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
        executable_truth = execution_entry is not None and execution_entry_status == "executable"
        execution_eligible = bool(tradable and execution_allowed and executable_truth)
        scored.append(
            (
                (
                    1 if execution_eligible else 0,
                    float(metrics["opportunity_score"]),
                    float(metrics["builder_confidence"]),
                ),
                candidate,
                {
                    **metrics,
                    "execution_eligible": execution_eligible,
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    annotated: list[Any] = []
    for index, (_sort_key, candidate, metrics) in enumerate(scored, start=1):
        rank_context = dict(metrics)
        rank_context["opportunity_rank"] = index
        size_multiplier, size_reason = derive_opportunity_size_multiplier(candidate, rank_context)
        score = float(metrics["opportunity_score"])
        adaptive_threshold = float(metrics["adaptive_execution_threshold"])
        floor = float(metrics["survival_floor"])
        selected = bool(
            metrics["execution_eligible"]
            and index <= executable_top_n
            and score >= adaptive_threshold
        )
        if selected:
            selection_reason = "selected_top_rank"
        elif not metrics["execution_eligible"]:
            selection_reason = "not_execution_eligible"
        elif score < floor:
            selection_reason = "below_survival_floor"
        elif score < adaptive_threshold:
            selection_reason = "below_adaptive_threshold"
        else:
            selection_reason = "rank_outside_top_n"
        source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
        source_flags.update(
            {
                "opportunity_scope": scope,
                "opportunity_score": round(score, 6),
                "opportunity_rank": int(index),
                "selected_for_execution": bool(selected),
                "selection_reason": selection_reason,
                "size_multiplier_reason": size_reason,
                "opportunity_size_multiplier": round(size_multiplier, 6),
                "adaptive_execution_threshold": round(adaptive_threshold, 6),
            }
        )
        if isinstance(candidate, dict):
            updated = dict(candidate)
            updated.update(
                {
                    "opportunity_score": round(score, 6),
                    "opportunity_rank": int(index),
                    "selected_for_execution": bool(selected),
                    "selection_reason": selection_reason,
                    "size_multiplier_reason": size_reason,
                    "opportunity_size_multiplier": round(size_multiplier, 6),
                    "size_mult": (
                        (_safe_float(updated.get("size_mult")) or 1.0) * size_multiplier
                        if selected
                        else (_safe_float(updated.get("size_mult")) or 1.0)
                    ),
                    "source_flags": source_flags,
                }
            )
        else:
            current_size_mult = _safe_float(_get_value(candidate, "size_mult")) or 1.0
            updated = replace(
                candidate,
                opportunity_score=round(score, 6),
                opportunity_rank=int(index),
                selected_for_execution=bool(selected),
                selection_reason=selection_reason,
                size_multiplier_reason=size_reason,
                opportunity_size_multiplier=round(size_multiplier, 6),
                size_mult=(current_size_mult * size_multiplier) if selected else current_size_mult,
                source_flags=source_flags,
            )
        annotated.append(updated)
    return annotated


def select_best_opportunity(
    candidates: Iterable[Any],
    *,
    scope: str,
    top_n: int | None = None,
) -> tuple[Any | None, list[Any]]:
    ranked = annotate_ranked_opportunities(candidates, scope=scope, top_n=top_n)
    if not ranked:
        return None, []
    best = ranked[0]
    if bool(_get_value(best, "execution_allowed", False)) and not bool(_get_value(best, "selected_for_execution", False)):
        source_flags = dict(_get_value(best, "source_flags", {}) or {})
        source_flags["opportunity_execution_downgraded"] = True
        source_flags["opportunity_execution_downgrade_reason"] = _get_value(best, "selection_reason")
        if isinstance(best, dict):
            best = dict(best)
            best["execution_allowed"] = False
            best["reason"] = best.get("reason") or f"opportunity_{best.get('selection_reason') or 'not_selected'}"
            best["source_flags"] = source_flags
        else:
            best = replace(
                best,
                execution_allowed=False,
                reason=(getattr(best, "reason", None) or f"opportunity_{_get_value(best, 'selection_reason') or 'not_selected'}"),
                source_flags=source_flags,
            )
        ranked[0] = best
    return best, ranked
