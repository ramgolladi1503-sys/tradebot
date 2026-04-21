from __future__ import annotations

from typing import Any

from config import config as cfg
from core.execution_quality import evaluate_pretrade_execution_quality
from core.opportunity_engine_score_cap_helper import apply_candidate_class_score_cap


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


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


def _cfg_reason_code_set(name: str, default: tuple[str, ...]) -> set[str]:
    raw = getattr(cfg, name, default)
    if isinstance(raw, (tuple, list, set)):
        values = raw
    else:
        values = str(raw or "").split(",")
    return {str(value or "").strip().lower() for value in values if str(value or "").strip()}


def _get_value(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _normalize_regime(value: Any) -> str:
    return str(value or "").strip().upper()


def _entry_reason_codes(entry: Any) -> set[str]:
    codes: set[str] = set()
    if not isinstance(entry, dict):
        return codes

    for field in ("reject_reason", "entry_block_code", "permission_reason", "reason"):
        text = str(entry.get(field) or "").strip().lower()
        if text:
            codes.add(text)

    for key in ("gate_reasons", "soft_penalties", "warnings", "blockers", "hard_blockers"):
        for item in list(entry.get(key) or []):
            text = str(item or "").strip().lower()
            if text:
                codes.add(text)

    source_flags = entry.get("source_flags") or {}
    if isinstance(source_flags, dict):
        text = str(source_flags.get("soft_reject_reason") or "").strip().lower()
        if text:
            codes.add(text)

    return codes


def _is_weak_signal_candidate(candidate: Any) -> bool:
    codes = _entry_reason_codes(candidate if isinstance(candidate, dict) else {})
    return bool(codes & {"weak_signal", "no_signal"})


def _soft_reject_reason(candidate: Any) -> str:
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    soft_reason = ""
    if isinstance(source_flags, dict):
        soft_reason = str(source_flags.get("soft_reject_reason") or "").strip().lower()
    if soft_reason:
        return soft_reason
    return str(
        _get_value(candidate, "entry_block_code")
        or _get_value(candidate, "reject_reason")
        or ""
    ).strip().lower()


def _blocks_execute_due_to_soft_reject(candidate: Any) -> bool:
    soft_reason = _soft_reject_reason(candidate)
    candidate_origin = str(
        (
            (_get_value(candidate, "source_flags", {}) or {}).get("candidate_origin")
            if isinstance(_get_value(candidate, "source_flags", {}) or {}, dict)
            else ""
        )
        or _get_value(candidate, "candidate_origin")
        or ""
    ).strip().lower()
    if soft_reason in {"weak_signal", "no_signal", "signal_score_below_min"}:
        return True
    if candidate_origin in {"softened_builder_path", "softened"} and bool(soft_reason):
        return True
    return False


def _infer_candidate_class(candidate: Any) -> str:
    explicit = str(_get_value(candidate, "candidate_class") or "").strip().lower()
    if explicit:
        return explicit

    source_flags = _get_value(candidate, "source_flags", {}) or {}
    origin = str(
        source_flags.get("candidate_origin") or _get_value(candidate, "candidate_origin") or ""
    ).strip().lower()
    strategy_family = str(_get_value(candidate, "strategy_family") or "").strip().lower()
    candidate_status = str(_get_value(candidate, "candidate_status") or "").strip().lower()

    if origin in {"fallback_min_breadth", "fallback", "recovered_fallback"}:
        return "fallback"
    if origin in {"planning_only"}:
        return "planning_only"
    if strategy_family == "synthetic_advisory":
        return "synthetic"
    if candidate_status == "advisory_only":
        return "advisory"
    if candidate_status == "near_executable":
        return "softened"
    return "real"


def _liquidity_quality(candidate: Any) -> float:
    volume = max(
        _safe_float(_get_value(candidate, "volume")) or 0.0,
        _safe_float(_get_value(candidate, "current_volume")) or 0.0,
    )
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
        ltp = _safe_float(_get_value(candidate, "opt_ltp")) or _safe_float(
            _get_value(candidate, "current_ltp")
        )
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
    regime = _normalize_regime(_get_value(candidate, "regime"))
    countertrend = bool(_get_value(candidate, "countertrend", False))

    if countertrend:
        return 0.35
    if regime in {"EVENT", "PANIC"}:
        return 0.45
    if regime in {"TREND", "TREND_STRONG", "VOLATILE_TREND"}:
        return 0.85
    if regime in {"RANGE", "RANGE_VOLATILE"}:
        return 0.65
    return 0.60


def _risk_adjusted_quality(candidate: Any) -> float:
    entry_price = _safe_float(
        _get_value(candidate, "execution_entry")
        or _get_value(candidate, "display_entry")
        or _get_value(candidate, "entry")
        or _get_value(candidate, "entry_price")
    )
    stop_loss = _safe_float(_get_value(candidate, "stop_loss"))
    target = _safe_float(_get_value(candidate, "target"))

    if entry_price in (None, 0.0) or stop_loss is None or target is None:
        return 0.5

    reward = abs(float(target) - float(entry_price))
    risk = max(abs(float(entry_price) - float(stop_loss)), 1e-6)
    rr = reward / risk
    return _clamp01(min(rr / 3.0, 1.0), default=0.5) or 0.5


def _regime_score_adjustments(candidate: Any) -> dict[str, float]:
    regime = _normalize_regime(_get_value(candidate, "regime"))
    countertrend = bool(_get_value(candidate, "countertrend", False))

    adjustments = {
        "builder_mult": 1.0,
        "gating_mult": 1.0,
        "confluence_mult": 1.0,
        "liquidity_mult": 1.0,
        "spread_mult": 1.0,
        "rr_mult": 1.0,
        "threshold_shift": 0.0,
    }

    if regime in {"RANGE", "RANGE_VOLATILE"}:
        adjustments.update(
            {
                "builder_mult": 0.88,
                "gating_mult": 0.92,
                "confluence_mult": 0.90,
                "rr_mult": 1.20,
                "liquidity_mult": 1.05,
                "spread_mult": 1.05,
                "threshold_shift": 0.02,
            }
        )
    elif regime in {"TREND", "TREND_STRONG", "VOLATILE_TREND"}:
        adjustments.update(
            {
                "builder_mult": 1.08,
                "gating_mult": 1.06,
                "confluence_mult": 1.08,
                "rr_mult": 1.05,
                "threshold_shift": -0.01,
            }
        )
    elif regime in {"EVENT", "PANIC"}:
        adjustments.update(
            {
                "builder_mult": 0.82,
                "gating_mult": 0.85,
                "confluence_mult": 0.85,
                "rr_mult": 0.95,
                "liquidity_mult": 0.90,
                "spread_mult": 0.85,
                "threshold_shift": 0.04,
            }
        )

    if countertrend:
        adjustments["builder_mult"] *= 0.90
        adjustments["gating_mult"] *= 0.90
        adjustments["threshold_shift"] += 0.02

    return adjustments


def assess_feed_validity(candidate: Any) -> dict[str, Any]:
    freshness = _freshness_quality(candidate)
    spread = _spread_quality(candidate)
    liquidity = _liquidity_quality(candidate)

    feed_confidence = _weighted_average(
        [
            (freshness, 0.45),
            (spread, 0.25),
            (liquidity, 0.30),
        ]
    )

    reasons: list[str] = []
    if freshness < 0.5:
        reasons.append("stale_quote")
    if spread < 0.4:
        reasons.append("wide_spread")
    if liquidity < 0.4:
        reasons.append("thin_liquidity")

    invalid_max = float(getattr(cfg, "DECISION_ENGINE_FEED_INVALID_MAX", 0.50) or 0.50)
    degraded_max = float(getattr(cfg, "DECISION_ENGINE_FEED_DEGRADED_MAX", 0.75) or 0.75)

    if feed_confidence < invalid_max:
        state = "invalid"
    elif feed_confidence < degraded_max:
        state = "degraded"
    else:
        state = "healthy"

    return {
        "feed_confidence": round(feed_confidence, 6),
        "feed_state": state,
        "feed_reasons": reasons,
        "freshness_quality": freshness,
        "spread_quality": spread,
        "liquidity_quality": liquidity,
    }


def build_decision_score(candidate: Any) -> dict[str, Any]:
    candidate_class = _infer_candidate_class(candidate)
    feed = assess_feed_validity(candidate)
    regime_adj = _regime_score_adjustments(candidate)

    builder_confidence = (
        _clamp01(
            _safe_float(_get_value(candidate, "builder_confidence"))
            or _safe_float(_get_value(candidate, "confidence_raw"))
            or _safe_float(_get_value(candidate, "confidence"))
            or _safe_float(_get_value(candidate, "gating_final_confidence"))
            or _safe_float(_get_value(candidate, "rank_score")),
            default=0.0,
        )
        or 0.0
    )
    gating_confidence = (
        _clamp01(
            _safe_float(_get_value(candidate, "gating_final_confidence"))
            or _safe_float(_get_value(candidate, "confidence_final"))
            or _safe_float(_get_value(candidate, "rank_score")),
            default=builder_confidence,
        )
        or builder_confidence
    )
    confluence_score = (
        _clamp01(
            _safe_float(_get_value(candidate, "sizing_confluence_score"))
            or _safe_float(_get_value(candidate, "trade_alignment"))
            or 0.5,
            default=0.5,
        )
        or 0.5
    )
    risk_adjusted_quality = _risk_adjusted_quality(candidate)
    regime_alignment = _regime_alignment(candidate)

    builder_confidence = (
        _clamp01(builder_confidence * regime_adj["builder_mult"], default=0.0) or 0.0
    )
    gating_confidence = (
        _clamp01(
            gating_confidence * regime_adj["gating_mult"],
            default=builder_confidence,
        )
        or builder_confidence
    )
    confluence_score = (
        _clamp01(confluence_score * regime_adj["confluence_mult"], default=0.5) or 0.5
    )
    risk_adjusted_quality = (
        _clamp01(risk_adjusted_quality * regime_adj["rr_mult"], default=0.5) or 0.5
    )

    liquidity_quality = (
        _clamp01(feed["liquidity_quality"] * regime_adj["liquidity_mult"], default=0.35)
        or 0.35
    )
    spread_quality = (
        _clamp01(feed["spread_quality"] * regime_adj["spread_mult"], default=0.0) or 0.0
    )
    freshness_quality = feed["freshness_quality"]

    raw_score = _weighted_average(
        [
            (builder_confidence, 0.26),
            (gating_confidence, 0.18),
            (confluence_score, 0.14),
            (risk_adjusted_quality, 0.12),
            (regime_alignment, 0.10),
            (liquidity_quality, 0.10),
            (spread_quality, 0.06),
            (freshness_quality, 0.04),
        ]
    )

    execution_quality = evaluate_pretrade_execution_quality(candidate)
    has_explicit_spread = (
        _safe_float(_get_value(candidate, "spread_pct")) is not None
        or (
            _safe_float(_get_value(candidate, "best_bid")) is not None
            and _safe_float(_get_value(candidate, "best_ask")) is not None
        )
    )
    spread_penalty = float(execution_quality.spread_penalty or 0.0)
    applied_penalty = min(max(spread_penalty, 0.0), 0.08) if has_explicit_spread else 0.0
    final_score = _clamp01(raw_score - applied_penalty, default=0.0) or 0.0
    final_score, class_score_cap = apply_candidate_class_score_cap(
        final_score, candidate_class
    )

    threshold_base = float(
        getattr(cfg, "DECISION_ENGINE_EXECUTE_MIN_SCORE", 0.70) or 0.70
    )
    threshold_effective = (
        _clamp01(
            threshold_base + float(regime_adj["threshold_shift"]),
            default=threshold_base,
        )
        or threshold_base
    )
    score_inflation_ratio = (
        round(final_score / max(raw_score, 1e-6), 6) if raw_score is not None else None
    )

    return {
        "candidate_class": candidate_class,
        "raw_score": round(raw_score, 6),
        "final_score": round(final_score, 6),
        "class_score_cap": class_score_cap,
        "score_inflation_ratio": score_inflation_ratio,
        "builder_confidence": round(builder_confidence, 6),
        "gating_confidence": round(gating_confidence, 6),
        "confluence_score": round(confluence_score, 6),
        "risk_adjusted_quality": round(risk_adjusted_quality, 6),
        "regime_alignment": round(regime_alignment, 6),
        "adaptive_execution_threshold": round(threshold_effective, 6),
        "regime": _normalize_regime(_get_value(candidate, "regime")),
        "regime_adjustments": regime_adj,
        "execution_ok": bool(execution_quality.execution_ok),
        "order_policy": str(execution_quality.order_policy),
        "order_policy_reason": str(execution_quality.reason_code),
        "expected_slippage": execution_quality.expected_slippage,
        "expected_slippage_bps": execution_quality.expected_slippage_bps,
        "fill_probability": float(execution_quality.fill_probability or 0.0),
        "execution_quality_score": float(execution_quality.execution_quality_score or 0.0),
        "applied_spread_penalty": applied_penalty,
        "feed": feed,
    }


def _has_invalid_geometry(candidate: Any) -> bool:
    entry = _safe_float(
        _get_value(candidate, "execution_entry")
        or _get_value(candidate, "display_entry")
        or _get_value(candidate, "entry")
    )
    stop_loss = _safe_float(_get_value(candidate, "stop_loss"))
    target = _safe_float(_get_value(candidate, "target"))

    # Geometry validation only when all levels exist; missing levels are handled upstream.
    if entry is None or stop_loss is None or target is None:
        return False

    side = str(_get_value(candidate, "side") or _get_value(candidate, "direction") or "").upper()
    if "SELL" in side:
        return not (target < entry < stop_loss)
    return not (stop_loss < entry < target)


def _is_execution_ready(
    candidate: Any, score_payload: dict[str, Any]
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if score_payload["feed"]["feed_state"] == "invalid":
        reasons.append("feed_not_healthy")
    if bool(_get_value(candidate, "execution_blocked")):
        reasons.append("execution_blocked")
    if bool(_get_value(candidate, "unresolved_contract")):
        reasons.append("unresolved_contract")
    if list(_get_value(candidate, "hard_blockers", []) or []):
        reasons.append("hard_blockers_present")
    if _has_invalid_geometry(candidate):
        reasons.append("invalid_level_geometry")
    if not bool(score_payload.get("execution_ok")):
        reason_code = str(score_payload.get("order_policy_reason") or "").strip().lower()
        hard_execution_quality_reasons = _cfg_reason_code_set(
            "DECISION_ENGINE_HARD_EXECUTION_QUALITY_REASONS",
            ("data_not_live", "fallback_driven_data", "missing_quote", "spread_breached"),
        )
        soft_execution_quality_reasons = _cfg_reason_code_set(
            "DECISION_ENGINE_SOFT_EXECUTION_QUALITY_REASONS",
            (
                "stale_quote",
                "inconsistent_quote",
                "low_data_confidence",
                "unverified_spread",
                "missing_liquidity_validation",
            ),
        )
        if reason_code in hard_execution_quality_reasons:
            reasons.append("execution_quality_reject")
        elif reason_code in soft_execution_quality_reasons:
            reasons.append("execution_quality_not_ready")
        elif reason_code:
            reasons.append(f"execution_quality_not_ready:{reason_code}")

    return (len(reasons) == 0), reasons


def evaluate_candidate_decision(candidate: dict[str, Any]) -> dict[str, Any]:
    score_payload = build_decision_score(candidate)
    execution_ready, readiness_reasons = _is_execution_ready(candidate, score_payload)

    soft_reject_execute_block_enable = bool(
        getattr(cfg, "DECISION_ENGINE_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", False)
    )
    weak_signal_execute_enable = bool(
        getattr(cfg, "DECISION_ENGINE_WEAK_SIGNAL_EXECUTE_ENABLE", False)
    )
    queue_min_score = float(getattr(cfg, "DECISION_ENGINE_QUEUE_MIN_SCORE", 0.55) or 0.55)
    execute_min_score = float(
        getattr(cfg, "DECISION_ENGINE_EXECUTE_MIN_SCORE", 0.70) or 0.70
    )
    promote_min_conf = float(getattr(cfg, "PERMISSION_PROMOTION_MIN_CONF", 0.72) or 0.72)
    promote_strong_conf = float(
        getattr(cfg, "PERMISSION_PROMOTION_STRONG_CONF", 0.80) or 0.80
    )
    min_raw_rank = float(getattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35) or 0.35)

    raw_score = float(score_payload["raw_score"])
    final_score = float(score_payload["final_score"])
    raw_rank_score = _safe_float(_get_value(candidate, "raw_rank_score"))
    effective_raw_rank = (
        float(raw_rank_score) if raw_rank_score is not None else float(raw_score)
    )
    gating_confidence = float(score_payload["gating_confidence"])
    selected_for_execution = bool(_get_value(candidate, "selected_for_execution"))
    has_rank_context = _safe_float(_get_value(candidate, "rank_global")) is not None

    decision_action = "REJECT"
    decision_reason = "insufficient_edge"

    if score_payload["candidate_class"] in {
        "synthetic",
        "fallback",
        "planning_only",
        "advisory",
    }:
        decision_reason = "non_real_candidate_class"
    elif soft_reject_execute_block_enable and _blocks_execute_due_to_soft_reject(candidate):
        if execution_ready and max(final_score, raw_score) >= queue_min_score:
            decision_action = "QUEUE"
        decision_reason = "soft_reject_weak_signal_blocks_execute"
    elif _is_weak_signal_candidate(candidate) and not weak_signal_execute_enable:
        if execution_ready and max(final_score, raw_score) >= queue_min_score:
            decision_action = "QUEUE"
            decision_reason = "weak_signal_queue_only"
        else:
            decision_reason = "weak_signal_not_executable"
    elif not execution_ready:
        decision_reason = "execution_not_ready"
    elif effective_raw_rank < min_raw_rank:
        if max(final_score, raw_score) >= queue_min_score:
            decision_action = "QUEUE"
            decision_reason = "raw_rank_below_execute_floor"
        else:
            decision_reason = "raw_rank_too_low"
    elif gating_confidence >= promote_strong_conf:
        decision_action = "EXECUTE"
        decision_reason = "strong_confidence_executable_entry"
    elif (
        gating_confidence >= promote_min_conf
        and max(final_score, raw_score) >= queue_min_score
        and (selected_for_execution or has_rank_context)
    ):
        decision_action = "EXECUTE"
        decision_reason = "ranked_top_candidate_promoted"
    elif final_score >= max(
        execute_min_score, float(score_payload["adaptive_execution_threshold"])
    ):
        decision_action = "EXECUTE"
        decision_reason = "strong_edge"
    elif final_score >= queue_min_score:
        decision_action = "QUEUE"
        decision_reason = "borderline_edge"
    else:
        decision_reason = "below_queue_threshold"

    permission = "ADVISORY_ONLY"
    final_action = "ADVISORY_ONLY"
    execution_status = "advisory_only"
    if decision_action == "QUEUE":
        permission = "QUEUE_ONLY"
        final_action = "QUEUE_ONLY"
        execution_status = "queue_only"
    elif decision_action == "EXECUTE":
        permission = "EXECUTE"
        final_action = "EXECUTE"
        execution_status = "executable"

    return {
        **score_payload,
        "execution_ready": execution_ready,
        "readiness_reasons": readiness_reasons,
        "decision_action": decision_action,
        "decision_reason": decision_reason,
        "permission": permission,
        "final_action": final_action,
        "execution_status": execution_status,
    }
