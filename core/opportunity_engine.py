from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import Any, Iterable

from config import config as cfg
from core.analytics.confidence_calibration import calibrate_confidence, load_latest_confidence_calibration_report
from core.capital_allocator import allocate_capital_slots
from core.execution_quality import evaluate_pretrade_execution_quality
from core.portfolio_optimizer import optimize_portfolio_selection


_HOSTILE_REGIMES = {"EVENT", "PANIC"}
logger = logging.getLogger(__name__)


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


def _candidate_key(candidate: Any) -> str:
    return str(
        _get_value(candidate, "trade_id")
        or _get_value(candidate, "trade_key")
        or _get_value(candidate, "instrument_id")
        or _get_value(candidate, "symbol")
        or ""
    ).strip()


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


def _strategy_priority(candidate: Any) -> float:
    detail = _candidate_detail(candidate)
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    value = (
        _safe_float(_get_value(candidate, "strategy_priority"))
        or _safe_float(detail.get("strategy_priority"))
        or _safe_float(source_flags.get("strategy_priority"))
    )
    return _clamp01(value, default=0.5) or 0.5


def _risk_adjusted_quality(candidate: Any) -> float:
    entry_price = _safe_float(_get_value(candidate, "entry_price"))
    stop_loss = _safe_float(_get_value(candidate, "stop_loss"))
    target = _safe_float(_get_value(candidate, "target"))
    if entry_price in (None, 0.0) or stop_loss is None or target is None:
        return 0.5
    reward = abs(float(target) - float(entry_price))
    risk = max(abs(float(entry_price) - float(stop_loss)), 1e-6)
    rr = reward / risk
    return _clamp01(min(rr / 3.0, 1.0), default=0.5) or 0.5


def _opportunity_bucket(score: float | None) -> str:
    value = _clamp01(score, default=0.0) or 0.0
    if value >= 0.75:
        return "TOP"
    if value >= 0.60:
        return "STRONG"
    if value >= 0.45:
        return "WATCH"
    return "LOW"


def _adaptive_execution_threshold_context(candidate: Any) -> dict[str, Any]:
    base = float(getattr(cfg, "OPPORTUNITY_EXECUTION_SCORE_BASE", 0.52))
    adjustments: list[tuple[str, float]] = []
    regime = str(_get_value(candidate, "regime") or "").strip().upper()
    liquidity_quality = _liquidity_quality(candidate)
    freshness_quality = _freshness_quality(candidate)
    spread_quality = _spread_quality(candidate)
    minutes_since_open = _safe_float(_get_value(candidate, "minutes_since_open"))
    minutes_to_close = _safe_float(_get_value(candidate, "minutes_to_close"))

    if regime in _HOSTILE_REGIMES:
        adjustments.append(("hostile_regime", float(getattr(cfg, "OPPORTUNITY_EXECUTION_HOSTILE_REGIME_PENALTY", 0.05))))
    elif regime in {"TREND", "RANGE"} and not bool(_get_value(candidate, "countertrend", False)):
        adjustments.append(("supportive_regime", -float(getattr(cfg, "OPPORTUNITY_EXECUTION_SUPPORTIVE_REGIME_BONUS", 0.02))))

    if bool(_get_value(candidate, "countertrend", False)):
        adjustments.append(("countertrend", float(getattr(cfg, "OPPORTUNITY_EXECUTION_COUNTERTREND_PENALTY", 0.04))))

    if liquidity_quality >= float(getattr(cfg, "OPPORTUNITY_STRONG_LIQUIDITY_THRESHOLD", 0.80)):
        adjustments.append(("strong_liquidity", -float(getattr(cfg, "OPPORTUNITY_EXECUTION_LIQUIDITY_BONUS", 0.03))))
    elif liquidity_quality <= float(getattr(cfg, "OPPORTUNITY_WEAK_LIQUIDITY_THRESHOLD", 0.45)):
        adjustments.append(("weak_liquidity", float(getattr(cfg, "OPPORTUNITY_EXECUTION_WEAK_LIQUIDITY_PENALTY", 0.02))))

    if freshness_quality >= float(getattr(cfg, "OPPORTUNITY_STRONG_FRESHNESS_THRESHOLD", 0.85)):
        adjustments.append(("fresh_quote", -float(getattr(cfg, "OPPORTUNITY_EXECUTION_STRONG_FRESHNESS_BONUS", 0.015))))
    elif freshness_quality <= float(getattr(cfg, "OPPORTUNITY_WEAK_FRESHNESS_THRESHOLD", 0.35)):
        adjustments.append(("aging_quote", float(getattr(cfg, "OPPORTUNITY_EXECUTION_WEAK_FRESHNESS_PENALTY", 0.025))))

    if spread_quality >= float(getattr(cfg, "OPPORTUNITY_STRONG_SPREAD_THRESHOLD", 0.85)):
        adjustments.append(("tight_spread", -float(getattr(cfg, "OPPORTUNITY_EXECUTION_STRONG_SPREAD_BONUS", 0.01))))
    elif spread_quality <= float(getattr(cfg, "OPPORTUNITY_WEAK_SPREAD_THRESHOLD", 0.35)):
        adjustments.append(("wide_spread", float(getattr(cfg, "OPPORTUNITY_EXECUTION_WEAK_SPREAD_PENALTY", 0.02))))

    opening_window = max(0.0, float(getattr(cfg, "OPPORTUNITY_EXECUTION_OPENING_WINDOW_MIN", 20) or 0.0))
    closing_window = max(0.0, float(getattr(cfg, "OPPORTUNITY_EXECUTION_CLOSING_WINDOW_MIN", 30) or 0.0))
    if minutes_since_open is not None and opening_window > 0 and minutes_since_open < opening_window:
        adjustments.append(("opening_window", float(getattr(cfg, "OPPORTUNITY_EXECUTION_OPENING_PENALTY", 0.02))))
    if minutes_to_close is not None and closing_window > 0 and minutes_to_close < closing_window:
        adjustments.append(("closing_window", float(getattr(cfg, "OPPORTUNITY_EXECUTION_CLOSING_PENALTY", 0.03))))

    max_adjustment = max(0.0, float(getattr(cfg, "OPPORTUNITY_EXECUTION_THRESHOLD_MAX_ADJUSTMENT", 0.08) or 0.0))
    raw_adjustment = sum(float(delta) for _reason, delta in adjustments)
    effective_adjustment = max(-max_adjustment, min(max_adjustment, raw_adjustment))
    threshold_effective = _clamp01(base + effective_adjustment, default=base) or base
    reason_parts = [f"{reason}:{delta:+.3f}" for reason, delta in adjustments]
    if raw_adjustment != effective_adjustment:
        reason_parts.append(f"bounded:{effective_adjustment:+.3f}")
    if not reason_parts:
        reason_parts.append("base:+0.000")
    return {
        "threshold_base": round(base, 6),
        "threshold_effective": round(float(threshold_effective), 6),
        "threshold_adjustment_reason": ";".join(reason_parts),
    }


def _ranking_score(candidate: Any, metrics: dict[str, Any] | None = None) -> float:
    explicit_rank = _safe_float(_get_value(candidate, "rank_score"))
    if explicit_rank is not None:
        return float(explicit_rank)
    explicit_opportunity = _safe_float(_get_value(candidate, "opportunity_score"))
    if explicit_opportunity is not None:
        return float(explicit_opportunity)
    if metrics is None:
        metrics = build_opportunity_score(candidate)
    return float(metrics.get("opportunity_score") or 0.0)


def _confidence_filter_value(candidate: Any, metrics: dict[str, Any] | None = None) -> float:
    if metrics is None:
        metrics = build_opportunity_score(candidate)
    value = _clamp01(
        _safe_float(_get_value(candidate, "confidence_after_soft_veto"))
        or _safe_float(_get_value(candidate, "gating_final_confidence"))
        or _safe_float(metrics.get("gating_final_confidence"))
        or _safe_float(_get_value(candidate, "confidence_final"))
        or _safe_float(_get_value(candidate, "builder_confidence"))
        or _safe_float(metrics.get("builder_confidence"))
        or _safe_float(_get_value(candidate, "confidence")),
        default=0.0,
    )
    return float(value or 0.0)


def _percentile_value(values: Iterable[float], percentile: float) -> float | None:
    series = sorted(float(value) for value in values)
    if not series:
        return None
    clamped = max(0.0, min(1.0, float(percentile)))
    if len(series) == 1:
        return float(series[0])
    position = clamped * float(len(series) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(series[lower])
    fraction = float(position - lower)
    return float(series[lower] + ((series[upper] - series[lower]) * fraction))


def _apply_global_opportunity_filter(
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],
    *,
    scope: str,
) -> tuple[
    list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],
    dict[str, Any],
]:
    if not scored:
        return [], {
            "applied": False,
            "max_active_opportunities": 0,
            "min_confidence_percentile": 0.0,
            "confidence_threshold": None,
            "candidates_before": 0,
            "candidates_after": 0,
        }

    max_active = max(0, int(getattr(cfg, "MAX_ACTIVE_OPPORTUNITIES", 0) or 0))
    percentile = max(0.0, min(1.0, float(getattr(cfg, "MIN_CONFIDENCE_PERCENTILE", 0.0) or 0.0)))
    if max_active <= 0 and percentile <= 0.0:
        count = len(scored)
        return scored, {
            "applied": False,
            "max_active_opportunities": max_active,
            "min_confidence_percentile": percentile,
            "confidence_threshold": None,
            "candidates_before": count,
            "candidates_after": count,
        }

    filtered = list(scored)
    confidence_threshold = None
    if percentile > 0.0 and filtered:
        confidence_values = [_confidence_filter_value(candidate, metrics) for _sort_key, candidate, metrics in filtered]
        confidence_threshold = _percentile_value(confidence_values, percentile)
        if confidence_threshold is not None:
            filtered = [
                entry
                for entry in filtered
                if _confidence_filter_value(entry[1], entry[2]) >= float(confidence_threshold)
            ]

    if max_active > 0 and len(filtered) > max_active:
        filtered = filtered[:max_active]

    metadata = {
        "applied": True,
        "max_active_opportunities": max_active,
        "min_confidence_percentile": percentile,
        "confidence_threshold": None if confidence_threshold is None else round(float(confidence_threshold), 6),
        "candidates_before": len(scored),
        "candidates_after": len(filtered),
    }
    if len(filtered) != len(scored):
        kept_keys = {
            str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or _get_value(candidate, "instrument_id") or "")
            for _sort_key, candidate, _metrics in filtered
        }
        trimmed_ids = [
            str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or "")
            for _sort_key, candidate, _metrics in scored
            if str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or _get_value(candidate, "instrument_id") or "") not in kept_keys
        ]
        logger.info(
            "OPPORTUNITY_GLOBAL_FILTER scope=%s candidates_before=%s candidates_after=%s max_active_opportunities=%s min_confidence_percentile=%.3f confidence_threshold=%s filtered_ids=%s",
            scope,
            metadata["candidates_before"],
            metadata["candidates_after"],
            max_active,
            percentile,
            metadata["confidence_threshold"],
            trimmed_ids[:10],
        )
    return filtered, metadata


def build_opportunity_score(
    candidate: Any,
    *,
    builder_confidence_override: float | None = None,
    gating_confidence_override: float | None = None,
) -> dict[str, Any]:
    detail = _candidate_detail(candidate)
    builder_confidence = (
        _clamp01(builder_confidence_override, default=None)
        if builder_confidence_override is not None
        else None
    )
    if builder_confidence is None:
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
    gating_confidence = (
        _clamp01(gating_confidence_override, default=None)
        if gating_confidence_override is not None
        else None
    )
    if gating_confidence is None:
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
    timing_score = _clamp01(
        _safe_float(_get_value(candidate, "timing_score"))
        or _safe_float(detail.get("entry_score"))
        or _safe_float(_get_value(candidate, "entry_score")),
        default=None,
    )
    spread_quality = _spread_quality(candidate)
    liquidity_quality = _liquidity_quality(candidate)
    freshness_quality = _freshness_quality(candidate)
    regime_alignment = _regime_alignment(candidate)
    strategy_priority = _strategy_priority(candidate)
    risk_adjusted_quality = _risk_adjusted_quality(candidate)
    score = _weighted_average(
        [
            (builder_confidence, float(getattr(cfg, "OPPORTUNITY_WEIGHT_BUILDER_CONFIDENCE", 0.32))),
            (permission_confidence, float(getattr(cfg, "OPPORTUNITY_WEIGHT_PERMISSION_CONFIDENCE", 0.12))),
            (gating_confidence, float(getattr(cfg, "OPPORTUNITY_WEIGHT_GATING_CONFIDENCE", 0.18))),
            (confluence_score, float(getattr(cfg, "OPPORTUNITY_WEIGHT_CONFLUENCE", 0.16))),
            (timing_score, float(getattr(cfg, "OPPORTUNITY_WEIGHT_TIMING", 0.10))),
            (regime_alignment, float(getattr(cfg, "OPPORTUNITY_WEIGHT_REGIME_ALIGNMENT", 0.08))),
            (liquidity_quality, float(getattr(cfg, "OPPORTUNITY_WEIGHT_LIQUIDITY", 0.07))),
            (spread_quality, float(getattr(cfg, "OPPORTUNITY_WEIGHT_SPREAD", 0.04))),
            (freshness_quality, float(getattr(cfg, "OPPORTUNITY_WEIGHT_FRESHNESS", 0.03))),
        ]
    )
    execution_quality = evaluate_pretrade_execution_quality(candidate)
    score = _clamp01(score - float(execution_quality.spread_penalty or 0.0), default=0.0) or 0.0
    threshold_context = _adaptive_execution_threshold_context(candidate)
    return {
        "builder_confidence": builder_confidence,
        "permission_confidence": permission_confidence,
        "gating_final_confidence": gating_confidence,
        "confluence_score": confluence_score,
        "timing_score": timing_score,
        "regime_alignment": regime_alignment,
        "liquidity_quality": liquidity_quality,
        "spread_quality": spread_quality,
        "freshness_quality": freshness_quality,
        "strategy_priority": strategy_priority,
        "risk_adjusted_quality": risk_adjusted_quality,
        "opportunity_score": score,
        "expected_slippage": execution_quality.expected_slippage,
        "expected_slippage_bps": execution_quality.expected_slippage_bps,
        "spread_penalty": float(execution_quality.spread_penalty or 0.0),
        "slippage_risk": float(execution_quality.slippage_risk or 0.0),
        "depth_score": float(execution_quality.depth_score or 0.0),
        "fill_probability": float(execution_quality.fill_probability or 0.0),
        "execution_quality_score": float(execution_quality.execution_quality_score or 0.0),
        "executable_price_estimate": execution_quality.executable_price_estimate,
        "execution_ok": bool(execution_quality.execution_ok),
        "order_policy": str(execution_quality.order_policy),
        "order_policy_reason": str(execution_quality.reason_code),
        "adaptive_execution_threshold": float(threshold_context["threshold_effective"]),
        "threshold_base": float(threshold_context["threshold_base"]),
        "threshold_effective": float(threshold_context["threshold_effective"]),
        "threshold_adjustment_reason": str(threshold_context["threshold_adjustment_reason"]),
        "survival_floor": float(getattr(cfg, "OPPORTUNITY_SURVIVAL_SCORE_FLOOR", 0.35)),
    }


def _confidence_calibration_shadow_payload() -> dict[str, Any] | None:
    if not bool(getattr(cfg, "CONFIDENCE_CALIBRATION_SHADOW_ENABLE", False)):
        return None
    payload = load_latest_confidence_calibration_report(require_eligible=True)
    if not isinstance(payload, dict):
        return None
    reliability_curve = list(((payload.get("calibration") or {}).get("reliability_curve") or []))
    if not reliability_curve:
        return None
    return payload


def _shadow_confidence(candidate: Any, calibration_payload: dict[str, Any]) -> float | None:
    raw_confidence = _clamp01(
        _safe_float(_get_value(candidate, "confidence_raw_canonical"))
        or _safe_float(_get_value(candidate, "confidence_model_raw"))
        or _safe_float(_get_value(candidate, "builder_confidence"))
        or _safe_float(_get_value(candidate, "confidence")),
        default=None,
    )
    if raw_confidence is None:
        return None
    calibration = dict(calibration_payload.get("calibration") or {})
    return calibrate_confidence(
        raw_confidence,
        calibration.get("reliability_curve") or [],
        min_bin_count=int(calibration.get("min_bin_count") or getattr(cfg, "CONFIDENCE_CALIBRATION_MIN_BIN_COUNT", 3)),
    )


def _build_confidence_shadow_map(
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],
    *,
    scope: str,
    executable_top_n: int,
) -> dict[str, dict[str, Any]]:
    payload = _confidence_calibration_shadow_payload()
    if not payload or not scored:
        return {}
    shadow_scored: list[tuple[tuple[int, float, float, float], str, dict[str, Any]]] = []
    for _sort_key, candidate, metrics in scored:
        key = _candidate_key(candidate)
        shadow_conf = _shadow_confidence(candidate, payload)
        if shadow_conf is None:
            continue
        shadow_metrics = build_opportunity_score(
            candidate,
            builder_confidence_override=shadow_conf,
            gating_confidence_override=shadow_conf,
        )
        execution_eligible = bool(metrics.get("execution_eligible"))
        shadow_scored.append(
            (
                (
                    1 if execution_eligible else 0,
                    float(shadow_metrics["opportunity_score"]),
                    float(shadow_metrics["gating_final_confidence"] or 0.0),
                    float(shadow_metrics["builder_confidence"]),
                ),
                key,
                {
                    "confidence_shadow": float(shadow_conf),
                    "opportunity_score_shadow": float(shadow_metrics["opportunity_score"]),
                    "adaptive_execution_threshold_shadow": float(shadow_metrics["adaptive_execution_threshold"]),
                    "execution_eligible": execution_eligible,
                },
            )
        )
    if not shadow_scored:
        return {}
    shadow_scored.sort(key=lambda item: item[0], reverse=True)
    shadow_by_key: dict[str, dict[str, Any]] = {}
    for index, (_sort_key, key, shadow_meta) in enumerate(shadow_scored, start=1):
        shadow_selected = bool(
            shadow_meta["execution_eligible"]
            and index <= executable_top_n
            and float(shadow_meta["opportunity_score_shadow"]) >= float(shadow_meta["adaptive_execution_threshold_shadow"])
        )
        shadow_by_key[key] = {
            **shadow_meta,
            "opportunity_rank_shadow": int(index),
            "selected_for_execution_shadow": shadow_selected,
        }

    drift_rows: list[dict[str, Any]] = []
    for raw_index, (_sort_key, candidate, metrics) in enumerate(scored, start=1):
        key = _candidate_key(candidate)
        shadow_meta = shadow_by_key.get(key)
        if shadow_meta is None:
            continue
        raw_selected = bool(
            metrics["execution_eligible"]
            and raw_index <= executable_top_n
            and float(metrics["opportunity_score"]) >= float(metrics["adaptive_execution_threshold"])
        )
        if int(shadow_meta["opportunity_rank_shadow"]) != int(raw_index) or bool(shadow_meta["selected_for_execution_shadow"]) != raw_selected:
            drift_rows.append(
                {
                    "candidate_key": key,
                    "rank_raw": int(raw_index),
                    "rank_calibrated": int(shadow_meta["opportunity_rank_shadow"]),
                    "decision_raw": "selected" if raw_selected else "not_selected",
                    "decision_calibrated": "selected" if bool(shadow_meta["selected_for_execution_shadow"]) else "not_selected",
                    "confidence_raw": _confidence_filter_value(candidate, metrics),
                    "confidence_calibrated": float(shadow_meta["confidence_shadow"]),
                }
            )
    if drift_rows:
        logger.info(
            "CONFIDENCE_CALIBRATION_DRIFT scope=%s calibration_date=%s rank_raw=%s rank_calibrated=%s decisions_raw=%s decisions_calibrated=%s",
            scope,
            payload.get("date"),
            [row["rank_raw"] for row in drift_rows[:10]],
            [row["rank_calibrated"] for row in drift_rows[:10]],
            [row["decision_raw"] for row in drift_rows[:10]],
            [row["decision_calibrated"] for row in drift_rows[:10]],
        )
    return shadow_by_key


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


def annotate_relative_opportunity_ranks(
    candidates: Iterable[Any],
    *,
    scope: str,
) -> list[Any]:
    candidate_list = list(candidates or [])
    if not candidate_list:
        return []
    scored: list[tuple[tuple[float, float, float, float, float, float, str, str], Any, dict[str, Any]]] = []
    for candidate in candidate_list:
        metrics = build_opportunity_score(candidate)
        rank_score = _ranking_score(candidate, metrics)
        scored.append(
            (
                (
                    float(rank_score),
                    float(metrics["opportunity_score"]),
                    float(metrics["strategy_priority"]),
                    float(metrics["risk_adjusted_quality"]),
                    float(metrics["builder_confidence"]),
                    float(metrics["permission_confidence"] or 0.0),
                    str(_get_value(candidate, "symbol") or ""),
                    str(_get_value(candidate, "trade_id") or ""),
                ),
                candidate,
                metrics,
            )
        )
    scored.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            -item[0][2],
            -item[0][3],
            -item[0][4],
            -item[0][5],
            item[0][6],
            item[0][7],
        )
    )
    per_symbol_rank: dict[str, int] = {}
    annotated: list[Any] = []
    for index, (_sort_key, candidate, metrics) in enumerate(scored, start=1):
        symbol = str(_get_value(candidate, "symbol") or "").strip().upper()
        per_symbol_rank[symbol] = int(per_symbol_rank.get(symbol, 0)) + 1
        source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
        source_flags.update(
            {
                "opportunity_scope": scope,
                "rank_global": int(index),
                "rank_within_symbol": int(per_symbol_rank[symbol]),
                "opportunity_bucket": _opportunity_bucket(metrics.get("opportunity_score")),
            }
        )
        if isinstance(candidate, dict):
            updated = dict(candidate)
            updated.update(
                {
                    "opportunity_score": round(float(metrics["opportunity_score"]), 6),
                    "rank_global": int(index),
                    "rank_within_symbol": int(per_symbol_rank[symbol]),
                    "opportunity_bucket": _opportunity_bucket(metrics.get("opportunity_score")),
                    "source_flags": source_flags,
                }
            )
        else:
            updated = replace(
                candidate,
                opportunity_score=round(float(metrics["opportunity_score"]), 6),
                rank_global=int(index),
                rank_within_symbol=int(per_symbol_rank[symbol]),
                opportunity_bucket=_opportunity_bucket(metrics.get("opportunity_score")),
                source_flags=source_flags,
            )
        annotated.append(updated)
    return annotated


def _visibility_sort_key(candidate: Any) -> tuple[float, float, float, float, float, float, str, str]:
    metrics = build_opportunity_score(candidate)
    return (
        float(_ranking_score(candidate, metrics)),
        float(_safe_float(_get_value(candidate, "opportunity_score")) or metrics["opportunity_score"] or 0.0),
        float(metrics["strategy_priority"]),
        float(metrics["risk_adjusted_quality"]),
        float(metrics["builder_confidence"]),
        float(metrics["permission_confidence"] or 0.0),
        str(_get_value(candidate, "symbol") or ""),
        str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or ""),
    )


def _is_executable_opportunity(candidate: Any) -> bool:
    truth = _execution_truth(candidate)
    if not truth["truth_allows_execution"]:
        return False
    execution_ok = _get_value(candidate, "execution_ok", None)
    if execution_ok is False:
        return False
    execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
    execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
    return bool(execution_entry is not None and execution_entry_status == "executable")


def _is_portfolio_selected(candidate: Any) -> bool:
    optimized = _get_value(candidate, "portfolio_optimization_selected")
    if optimized is not None:
        return bool(optimized)
    return bool(_get_value(candidate, "selected_for_execution", False))


def _is_advisory_opportunity(candidate: Any) -> bool:
    if _is_executable_opportunity(candidate):
        return False
    display_entry = _safe_float(_get_value(candidate, "display_entry"))
    display_entry_status = str(_get_value(candidate, "display_entry_status") or "").strip().lower()
    return bool(display_entry is not None and display_entry_status in {"displayable", "non_executable"})


def _string_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        return {values.strip().lower()} if values.strip() else set()
    out: set[str] = set()
    try:
        for value in values:
            text = str(value or "").strip().lower()
            if text:
                out.add(text)
    except Exception:
        text = str(values or "").strip().lower()
        if text:
            out.add(text)
    return out


def _candidate_class(candidate: Any) -> str:
    source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
    explicit_class = str(
        _get_value(candidate, "candidate_class")
        or source_flags.get("candidate_class")
        or source_flags.get("opportunity_candidate_class")
        or ""
    ).strip().lower()
    if explicit_class:
        return explicit_class

    row_kind = str(
        _get_value(candidate, "row_kind")
        or _get_value(candidate, "candidate_row_kind")
        or source_flags.get("row_kind")
        or source_flags.get("candidate_row_kind")
        or ""
    ).strip().lower()
    origin = str(
        _get_value(candidate, "candidate_origin")
        or source_flags.get("candidate_origin")
        or source_flags.get("origin")
        or ""
    ).strip().lower()
    status = str(
        _get_value(candidate, "trade_status")
        or source_flags.get("trade_status")
        or ""
    ).strip().lower()
    reasons = _string_set(
        _get_value(candidate, "recoveries")
        or _get_value(candidate, "recovery_reasons")
        or source_flags.get("recoveries")
        or source_flags.get("recovery_reasons")
        or []
    )
    tags = _string_set(
        _get_value(candidate, "candidate_tags")
        or source_flags.get("candidate_tags")
        or []
    )

    if row_kind in {"fallback", "recovered_fallback"}:
        return "fallback"
    if "recovered_fallback" in reasons or "fallback" in tags or "fallback" in reasons:
        return "fallback"
    if "planning" in origin or "planning" in row_kind or status == "planning_only":
        return "planning_only"
    if "synthetic" in origin or "synthetic" in row_kind or "synthetic" in tags:
        return "synthetic"
    if "soft" in origin or "soft" in row_kind or "soft_reject" in tags or "softened" in tags:
        return "softened"
    if "advisory" in origin or "advisory" in row_kind or status == "advisory_only":
        return "advisory"
    return "executable"


def _execution_truth(candidate: Any) -> dict[str, Any]:
    source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
    candidate_class = _candidate_class(candidate)
    execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
    execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))
    execution_truth = bool(
        execution_entry is not None
        and execution_entry_status == "executable"
        and execution_allowed
        and tradable
    )
    class_blocks = candidate_class in {
        "fallback",
        "planning_only",
        "synthetic",
        "softened",
        "advisory",
    }
    debug_block = bool(
        _get_value(candidate, "planning_only", False)
        or _get_value(candidate, "advisory_only", False)
        or source_flags.get("planning_only")
        or source_flags.get("advisory_only")
        or source_flags.get("debug_candidate")
    )
    truth_allows_execution = bool(execution_truth and not class_blocks and not debug_block)
    return {
        "candidate_class": candidate_class,
        "execution_truth": execution_truth,
        "truth_allows_execution": truth_allows_execution,
        "class_blocks_execution": class_blocks,
        "debug_blocks_execution": debug_block,
    }


def _dedupe_opportunity_candidates(candidates: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for candidate in candidates or []:
        key = str(
            _get_value(candidate, "trade_id")
            or _get_value(candidate, "trade_key")
            or _get_value(candidate, "instrument_id")
            or ""
        ).strip()
        if not key:
            key = f"candidate:{len(out)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def select_top_opportunities(
    candidates: Iterable[Any],
    *,
    executable_top_n: int | None = None,
    advisory_top_n: int | None = None,
    current_portfolio_exposure: Any = None,
) -> dict[str, Any]:
    executable_limit = max(0, int(executable_top_n if executable_top_n is not None else getattr(cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5)))
    advisory_limit = max(0, int(advisory_top_n if advisory_top_n is not None else getattr(cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5)))
    candidate_list = _dedupe_opportunity_candidates(candidates)
    scored = [(_visibility_sort_key(candidate), candidate) for candidate in candidate_list]
    scored.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            -item[0][2],
            -item[0][3],
            -item[0][4],
            -item[0][5],
            item[0][6],
            item[0][7],
        )
    )
    top_executable: list[Any] = []
    top_advisory: list[Any] = []
    for _sort_key, candidate in scored:
        if _is_executable_opportunity(candidate):
            if len(top_executable) < executable_limit:
                top_executable.append(candidate)
            continue
        if _is_advisory_opportunity(candidate) and len(top_advisory) < advisory_limit:
            top_advisory.append(candidate)
        if len(top_executable) >= executable_limit and len(top_advisory) >= advisory_limit:
            break
    if top_executable and bool(getattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", True)):
        executable_seed: list[Any] = []
        for candidate in top_executable:
            if isinstance(candidate, dict):
                seeded = dict(candidate)
                seeded.setdefault("selected_for_execution", True)
            else:
                selected = _get_value(candidate, "selected_for_execution")
                seeded = candidate if selected is True else replace(candidate, selected_for_execution=True)
            executable_seed.append(seeded)
        top_executable = allocate_capital_slots(
            executable_seed,
            max_slots=max(1, int(getattr(cfg, "CAPITAL_ALLOCATOR_MAX_SLOTS", executable_limit or 1) or 1)),
            per_symbol_cap=max(0, int(getattr(cfg, "CAPITAL_ALLOCATOR_PER_SYMBOL_CAP", 1) or 0)),
            per_theme_cap=max(0, int(getattr(cfg, "CAPITAL_ALLOCATOR_PER_THEME_CAP", 1) or 0)),
            capital_budget_cap=(
                float(getattr(cfg, "CAPITAL_ALLOCATOR_BUDGET_CAP", 0) or 0.0)
                if float(getattr(cfg, "CAPITAL_ALLOCATOR_BUDGET_CAP", 0) or 0.0) > 0
                else None
            ),
            minimum_quality_threshold=max(0.0, float(getattr(cfg, "CAPITAL_ALLOCATOR_MIN_QUALITY_THRESHOLD", 0.0) or 0.0)),
            replacement_enabled=bool(getattr(cfg, "CAPITAL_ALLOCATOR_REPLACEMENT_ENABLE", True)),
            replacement_min_delta=max(0.0, float(getattr(cfg, "CAPITAL_ALLOCATOR_REPLACEMENT_MIN_DELTA", 0.03) or 0.0)),
        )
    if top_executable and bool(getattr(cfg, "PORTFOLIO_OPTIMIZER_ENABLE", False)):
        optimized = optimize_portfolio_selection(
            top_executable,
            current_portfolio_exposure=current_portfolio_exposure,
        )
        top_executable = [candidate for candidate in optimized if _is_portfolio_selected(candidate)]
    return {
        "top_executable_opportunities": top_executable,
        "top_advisory_opportunities": top_advisory,
        "candidates_considered": len(candidate_list),
    }


def annotate_ranked_opportunities(
    candidates: Iterable[Any],
    *,
    scope: str,
    top_n: int | None = None,
    current_portfolio_exposure: Any = None,
) -> list[Any]:
    candidate_list = annotate_relative_opportunity_ranks(candidates, scope=scope)
    if not candidate_list:
        return []
    if not bool(getattr(cfg, "OPPORTUNITY_ENGINE_ENABLE", True)):
        return candidate_list
    executable_top_n = max(1, int(top_n or getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)))
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]] = []
    for candidate in candidate_list:
        metrics = build_opportunity_score(candidate)
        ranking_score = _ranking_score(candidate, metrics)
        execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
        tradable = bool(_get_value(candidate, "tradable", False))
        truth = _execution_truth(candidate)
        execution_eligible = bool(
            truth["truth_allows_execution"] and bool(metrics["execution_ok"])
        )
        scored.append(
            (
                (
                    1 if execution_eligible else 0,
                    float(ranking_score),
                    float(metrics["opportunity_score"]),
                    float(metrics["builder_confidence"]),
                ),
                candidate,
                {
                    **metrics,
                    "ranking_score": float(ranking_score),
                    "execution_allowed": execution_allowed,
                    "tradable": tradable,
                    "candidate_class": truth["candidate_class"],
                    "executable_truth": truth["execution_truth"],
                    "truth_allows_execution": truth["truth_allows_execution"],
                    "class_blocks_execution": truth["class_blocks_execution"],
                    "debug_blocks_execution": truth["debug_blocks_execution"],
                    "execution_eligible": execution_eligible,
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    scored, global_filter_meta = _apply_global_opportunity_filter(scored, scope=scope)
    shadow_by_key = _build_confidence_shadow_map(scored, scope=scope, executable_top_n=executable_top_n)
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
        elif not bool(metrics["executable_truth"]) or not bool(metrics["tradable"]) or not bool(metrics["execution_allowed"]):
            selection_reason = "not_execution_eligible"
        elif not bool(metrics["truth_allows_execution"]):
            selection_reason = "execution_truth_blocked"
        elif not bool(metrics["execution_ok"]):
            selection_reason = "execution_quality_reject"
        elif score < floor:
            selection_reason = "below_survival_floor"
        elif score < adaptive_threshold:
            selection_reason = "below_adaptive_threshold"
        else:
            selection_reason = "rank_outside_top_n"
        shadow_meta = shadow_by_key.get(_candidate_key(candidate), {})
        source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
        source_flags.update(
            {
                "opportunity_scope": scope,
                "opportunity_score": round(score, 6),
                "opportunity_rank": int(index),
                "selected_for_execution": bool(selected),
                "selection_reason": selection_reason,
                "candidate_class": str(metrics["candidate_class"]),
                "truth_allows_execution": bool(metrics["truth_allows_execution"]),
                "class_blocks_execution": bool(metrics["class_blocks_execution"]),
                "debug_blocks_execution": bool(metrics["debug_blocks_execution"]),
                "size_multiplier_reason": size_reason,
                "opportunity_size_multiplier": round(size_multiplier, 6),
                "adaptive_execution_threshold": round(adaptive_threshold, 6),
                "threshold_base": round(float(metrics["threshold_base"]), 6),
                "threshold_effective": round(float(metrics["threshold_effective"]), 6),
                "threshold_adjustment_reason": str(metrics["threshold_adjustment_reason"]),
                "expected_slippage": metrics["expected_slippage"],
                "expected_slippage_bps": metrics["expected_slippage_bps"],
                "spread_penalty": round(float(metrics["spread_penalty"]), 6),
                "slippage_risk": round(float(metrics["slippage_risk"]), 6),
                "depth_score": round(float(metrics["depth_score"]), 6),
                "fill_probability": round(float(metrics["fill_probability"]), 6),
                "execution_quality_score": round(float(metrics["execution_quality_score"]), 6),
                "executable_price_estimate": metrics["executable_price_estimate"],
                "execution_ok": bool(metrics["execution_ok"]),
                "order_policy": str(metrics["order_policy"]),
                "order_policy_reason": str(metrics["order_policy_reason"]),
                "global_opportunity_filter_applied": bool(global_filter_meta["applied"]),
                "global_opportunity_filter_scope": scope,
                "global_opportunity_confidence_threshold": global_filter_meta["confidence_threshold"],
                "global_opportunity_max_active": int(global_filter_meta["max_active_opportunities"]),
                "global_opportunity_min_confidence_percentile": float(global_filter_meta["min_confidence_percentile"]),
                "confidence_shadow": shadow_meta.get("confidence_shadow"),
                "opportunity_score_shadow": shadow_meta.get("opportunity_score_shadow"),
                "opportunity_rank_shadow": shadow_meta.get("opportunity_rank_shadow"),
                "selected_for_execution_shadow": shadow_meta.get("selected_for_execution_shadow"),
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
                    "candidate_class": str(metrics["candidate_class"]),
                    "truth_allows_execution": bool(metrics["truth_allows_execution"]),
                    "class_blocks_execution": bool(metrics["class_blocks_execution"]),
                    "debug_blocks_execution": bool(metrics["debug_blocks_execution"]),
                    "size_multiplier_reason": size_reason,
                    "opportunity_size_multiplier": round(size_multiplier, 6),
                    "threshold_base": round(float(metrics["threshold_base"]), 6),
                    "threshold_effective": round(float(metrics["threshold_effective"]), 6),
                    "threshold_adjustment_reason": str(metrics["threshold_adjustment_reason"]),
                    "expected_slippage": metrics["expected_slippage"],
                    "expected_slippage_bps": metrics["expected_slippage_bps"],
                    "spread_penalty": round(float(metrics["spread_penalty"]), 6),
                    "slippage_risk": round(float(metrics["slippage_risk"]), 6),
                    "depth_score": round(float(metrics["depth_score"]), 6),
                    "fill_probability": round(float(metrics["fill_probability"]), 6),
                    "execution_quality_score": round(float(metrics["execution_quality_score"]), 6),
                    "executable_price_estimate": metrics["executable_price_estimate"],
                    "execution_ok": bool(metrics["execution_ok"]),
                    "order_policy": str(metrics["order_policy"]),
                    "order_policy_reason": str(metrics["order_policy_reason"]),
                    "confidence_shadow": shadow_meta.get("confidence_shadow"),
                    "opportunity_score_shadow": shadow_meta.get("opportunity_score_shadow"),
                    "opportunity_rank_shadow": shadow_meta.get("opportunity_rank_shadow"),
                    "selected_for_execution_shadow": shadow_meta.get("selected_for_execution_shadow"),
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
                candidate_class=str(metrics["candidate_class"]),
                truth_allows_execution=bool(metrics["truth_allows_execution"]),
                class_blocks_execution=bool(metrics["class_blocks_execution"]),
                debug_blocks_execution=bool(metrics["debug_blocks_execution"]),
                size_multiplier_reason=size_reason,
                opportunity_size_multiplier=round(size_multiplier, 6),
                threshold_base=round(float(metrics["threshold_base"]), 6),
                threshold_effective=round(float(metrics["threshold_effective"]), 6),
                threshold_adjustment_reason=str(metrics["threshold_adjustment_reason"]),
                expected_slippage=metrics["expected_slippage"],
                expected_slippage_bps=metrics["expected_slippage_bps"],
                spread_penalty=round(float(metrics["spread_penalty"]), 6),
                slippage_risk=round(float(metrics["slippage_risk"]), 6),
                depth_score=round(float(metrics["depth_score"]), 6),
                fill_probability=round(float(metrics["fill_probability"]), 6),
                execution_quality_score=round(float(metrics["execution_quality_score"]), 6),
                executable_price_estimate=metrics["executable_price_estimate"],
                execution_ok=bool(metrics["execution_ok"]),
                order_policy=str(metrics["order_policy"]),
                order_policy_reason=str(metrics["order_policy_reason"]),
                confidence_shadow=shadow_meta.get("confidence_shadow"),
                opportunity_score_shadow=shadow_meta.get("opportunity_score_shadow"),
                opportunity_rank_shadow=shadow_meta.get("opportunity_rank_shadow"),
                selected_for_execution_shadow=shadow_meta.get("selected_for_execution_shadow"),
                size_mult=(current_size_mult * size_multiplier) if selected else current_size_mult,
                source_flags=source_flags,
            )
        annotated.append(updated)
    if annotated and bool(getattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", True)):
        annotated = allocate_capital_slots(
            annotated,
            max_slots=max(1, int(getattr(cfg, "CAPITAL_ALLOCATOR_MAX_SLOTS", executable_top_n) or executable_top_n)),
            per_symbol_cap=max(0, int(getattr(cfg, "CAPITAL_ALLOCATOR_PER_SYMBOL_CAP", 1) or 0)),
            per_theme_cap=max(0, int(getattr(cfg, "CAPITAL_ALLOCATOR_PER_THEME_CAP", 1) or 0)),
            capital_budget_cap=(
                float(getattr(cfg, "CAPITAL_ALLOCATOR_BUDGET_CAP", 0) or 0.0)
                if float(getattr(cfg, "CAPITAL_ALLOCATOR_BUDGET_CAP", 0) or 0.0) > 0
                else None
            ),
            minimum_quality_threshold=max(0.0, float(getattr(cfg, "CAPITAL_ALLOCATOR_MIN_QUALITY_THRESHOLD", 0.0) or 0.0)),
            replacement_enabled=bool(getattr(cfg, "CAPITAL_ALLOCATOR_REPLACEMENT_ENABLE", True)),
            replacement_min_delta=max(0.0, float(getattr(cfg, "CAPITAL_ALLOCATOR_REPLACEMENT_MIN_DELTA", 0.03) or 0.0)),
        )
    if annotated and bool(getattr(cfg, "PORTFOLIO_OPTIMIZER_ENABLE", False)):
        annotated = optimize_portfolio_selection(
            annotated,
            current_portfolio_exposure=current_portfolio_exposure,
        )
    return annotated


def select_best_opportunity(
    candidates: Iterable[Any],
    *,
    scope: str,
    top_n: int | None = None,
    current_portfolio_exposure: Any = None,
) -> tuple[Any | None, list[Any]]:
    ranked = annotate_ranked_opportunities(
        candidates,
        scope=scope,
        top_n=top_n,
        current_portfolio_exposure=current_portfolio_exposure,
    )
    if not ranked:
        return None, []
    allocated = [
        candidate
        for candidate in ranked
        if _is_portfolio_selected(candidate) and bool(_get_value(candidate, "slot_id", None))
    ]
    best = allocated[0] if allocated else ranked[0]
    if bool(_get_value(best, "execution_allowed", False)) and not _is_portfolio_selected(best):
        source_flags = dict(_get_value(best, "source_flags", {}) or {})
        source_flags["opportunity_execution_downgraded"] = True
        source_flags["opportunity_execution_downgrade_reason"] = (
            _get_value(best, "portfolio_optimization_reason")
            or _get_value(best, "selection_reason")
        )
        if isinstance(best, dict):
            best = dict(best)
            best["execution_allowed"] = False
            best["reason"] = best.get("reason") or f"opportunity_{best.get('portfolio_optimization_reason') or best.get('selection_reason') or 'not_selected'}"
            best["source_flags"] = source_flags
        else:
            best = replace(
                best,
                execution_allowed=False,
                reason=(
                    getattr(best, "reason", None)
                    or f"opportunity_{_get_value(best, 'portfolio_optimization_reason') or _get_value(best, 'selection_reason') or 'not_selected'}"
                ),
                source_flags=source_flags,
            )
        ranked[0] = best
    return best, ranked
