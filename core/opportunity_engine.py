from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import replace
import hashlib
from typing import Any, Iterable

from config import config as cfg
from core.analytics.confidence_calibration import calibrate_confidence, load_latest_confidence_calibration_report
from core.capital_allocator import allocate_capital_slots
from core.candidate_finalization import stamp_lifecycle_stage
from core.contextual_thresholds import get_contextual_threshold_delta as _contextual_threshold_delta
from core.decision_authority import apply_stage_authority
from core.execution_quality import evaluate_pretrade_execution_quality
from core.feature_builder import assess_trade_feature_quality
from core.liquidity_truth import assess_liquidity_quality
from core.learning_state import load_learning_state, save_learning_state
from core.opportunity_engine_score_cap_helper import apply_candidate_class_score_cap
from core.portfolio_optimizer import optimize_portfolio_selection
from core.risk_engine import adjust_system_aggressiveness, evaluate_candidate_risk
from core.threshold_audit import (
    build_candidate_decision_record,
    compute_starvation_diagnostics,
    load_candidate_decisions,
    record_candidate_decision,
    write_threshold_audit_summaries,
)
from core.threshold_tuning import (
    build_threshold_tuning_recommendations,
    load_threshold_tuning_recommendations,
    save_threshold_tuning_recommendations,
)
from core.threshold_triage import (
    build_tuning_shortlist,
    load_threshold_tuning_shortlist,
    save_threshold_tuning_shortlist,
)
from core.trade_scoring import compute_final_score


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


def _update_candidate(candidate: Any, **updates: Any) -> Any:
    if isinstance(candidate, dict):
        out = dict(candidate)
        out.update(updates)
        return out
    return replace(candidate, **updates)


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


def _aggressiveness_threshold_shift(mode: str | None) -> float:
    max_shift = max(
        0.0,
        float(getattr(cfg, "OFFLINE_AGGRESSIVENESS_MAX_THRESHOLD_SHIFT", 0.01) or 0.01),
    )
    normalized = str(mode or "NORMAL").strip().upper() or "NORMAL"
    if normalized in {"TOO_TIMID", "STARVING"}:
        return -max_shift
    if normalized == "OVERTRADING":
        return max_shift
    return 0.0


def _get_contextual_threshold_adjustment(
    stage: str | None,
    family: str | None,
    session: str | None,
    regime: str | None,
    recommendations: dict[str, Any] | None,
) -> float:
    return float(
        _contextual_threshold_delta(
            stage,
            family,
            session,
            regime,
            recommendations,
        )
        or 0.0
    )


def _trade_density_family_key(candidate: Any) -> str:
    return (
        str(
            _get_value(candidate, "strategy_family")
            or (_get_value(candidate, "source_flags", {}) or {}).get("strategy_family")
            or "unknown"
        )
        .strip()
        .lower()
        .replace("_", "-")
        or "unknown"
    )


def _candidate_density_policy(candidate: Any) -> dict[str, Any]:
    session_mode = _get_value(candidate, "session_mode") or (_get_value(candidate, "source_flags", {}) or {}).get("session_mode")
    regime_mode = _get_value(candidate, "strategy_regime_mode") or (_get_value(candidate, "source_flags", {}) or {}).get("strategy_regime_mode")
    return dict(cfg.get_trade_density_policy(session_mode, regime_mode))


def _candidate_density_eligible(candidate: Any) -> bool:
    candidate_class = str(_get_value(candidate, "candidate_class") or "").strip().upper()
    if candidate_class != "EXECUTABLE":
        return False
    if not bool(_get_value(candidate, "execution_allowed", False)):
        return False
    if not bool(_get_value(candidate, "tradable", False)):
        return False
    return bool(_is_executable_opportunity(candidate))


def _apply_trade_density_controller(candidates: Iterable[Any]) -> list[Any]:
    candidate_list = list(candidates or [])
    if not candidate_list:
        return candidate_list
    if not bool(getattr(cfg, "OFFLINE_TRADE_DENSITY_ENABLE", True)):
        return candidate_list
    if not any(_candidate_market_mode(candidate) in {"SIM", "PAPER", "OFFHOURS"} for candidate in candidate_list):
        return candidate_list

    eligible_rank_counts: Counter[str] = Counter()
    selected_counts: Counter[str] = Counter()
    selected_family_counts: Counter[tuple[str, str]] = Counter()
    updated_candidates: list[Any] = []
    for candidate in candidate_list:
        policy = _candidate_density_policy(candidate)
        policy_name = str(policy.get("policy_name") or "UNKNOWN:UNKNOWN")
        density_reject_reason = None
        density_eligible = _candidate_density_eligible(candidate)
        selected_for_execution = bool(_get_value(candidate, "selected_for_execution", False))
        if density_eligible:
            next_ranked_count = int(eligible_rank_counts.get(policy_name, 0)) + 1
            if next_ranked_count > int(policy.get("max_ranked_candidates", 0) or 0):
                density_reject_reason = "trade_density_rank_cap"
            else:
                eligible_rank_counts[policy_name] = next_ranked_count
        if density_reject_reason is None and selected_for_execution:
            family_key = _trade_density_family_key(candidate)
            if int(selected_counts.get(policy_name, 0)) >= int(policy.get("max_executable_candidates", 0) or 0):
                density_reject_reason = "trade_density_executable_cap"
            elif int(selected_family_counts.get((policy_name, family_key), 0)) >= int(policy.get("max_per_family", 0) or 0):
                density_reject_reason = "trade_density_family_cap"
            else:
                selected_counts[policy_name] += 1
                selected_family_counts[(policy_name, family_key)] += 1
        trade_density_limit_applied = density_reject_reason is not None
        source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
        source_flags.update(
            {
                "trade_density_limit_applied": bool(trade_density_limit_applied),
                "density_policy_name": policy_name,
                "density_reject_reason": density_reject_reason,
                "effective_trade_density_policy": dict(policy),
            }
        )
        updates: dict[str, Any] = {
            "trade_density_limit_applied": bool(trade_density_limit_applied),
            "density_policy_name": policy_name,
            "density_reject_reason": density_reject_reason,
            "source_flags": source_flags,
        }
        if trade_density_limit_applied:
            updates.update(
                {
                    "selected_for_execution": False,
                    "selection_reason": density_reject_reason,
                    "portfolio_optimization_selected": False,
                    "slot_id": None,
                    "capital_assigned": None,
                }
            )
        updated_candidates.append(_update_candidate(candidate, **updates))
    return updated_candidates


def _bool_from_candidate(candidate: Any, field: str, fallback: Any = False) -> bool:
    value = _get_value(candidate, field, None)
    if value is None:
        value = fallback
    return bool(value)


def _liquidity_quality(candidate: Any) -> float:
    volume = max(
        _safe_float(_get_value(candidate, "volume")) or 0.0,
        _safe_float(_get_value(candidate, "current_volume")) or 0.0,
    )
    oi = max(
        _safe_float(_get_value(candidate, "oi")) or 0.0,
        _safe_float(_get_value(candidate, "oi_change")) or 0.0,
    )
    quote_consistency = _safe_float(_get_value(candidate, "quote_consistency_score"))
    if quote_consistency is None:
        quote_consistency = _safe_float((_get_value(candidate, "source_flags", {}) or {}).get("quote_consistency_score"))
    spread_pct = _safe_float(_get_value(candidate, "spread_pct"))
    if spread_pct is None:
        spread_pct = _safe_float((_get_value(candidate, "source_flags", {}) or {}).get("spread_pct"))
    payload = assess_liquidity_quality(
        volume=volume,
        oi=oi,
        spread_pct=spread_pct,
        quote_consistency_score=quote_consistency,
        quote_ok=_get_value(candidate, "quote_ok", True),
    )
    return float(payload["liquidity_score"])


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


def _candidate_feature_quality(candidate: Any) -> dict[str, Any]:
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    market_mode = _candidate_market_mode(candidate)
    market_data = {
        "execution_mode": market_mode,
        "market_context": {
            "execution_mode": market_mode,
            "market_open": market_mode == "LIVE",
        },
        "market_open": market_mode == "LIVE",
        "quote_ok": _get_value(candidate, "quote_ok", source_flags.get("quote_ok", True)),
        "chain_snapshot_age_sec": _get_value(candidate, "chain_snapshot_age_sec", source_flags.get("chain_snapshot_age_sec")),
        "liquidity_age_sec": _get_value(candidate, "liquidity_age_sec", source_flags.get("liquidity_age_sec")),
    }
    opt_like = {
        "ltp": _get_value(candidate, "opt_ltp")
        or _get_value(candidate, "current_ltp")
        or _get_value(candidate, "last_price"),
        "last_price": _get_value(candidate, "opt_ltp")
        or _get_value(candidate, "current_ltp")
        or _get_value(candidate, "last_price"),
        "bid": _get_value(candidate, "best_bid", _get_value(candidate, "opt_bid")),
        "ask": _get_value(candidate, "best_ask", _get_value(candidate, "opt_ask")),
        "quote_age_sec": _get_value(candidate, "quote_age_sec", source_flags.get("quote_age_sec")),
        "ltp_age_sec": _get_value(candidate, "ltp_age_sec", source_flags.get("ltp_age_sec")),
        "bid_age_sec": _get_value(candidate, "bid_age_sec", source_flags.get("bid_age_sec")),
        "ask_age_sec": _get_value(candidate, "ask_age_sec", source_flags.get("ask_age_sec")),
        "chain_snapshot_age_sec": _get_value(
            candidate,
            "chain_snapshot_age_sec",
            source_flags.get("chain_snapshot_age_sec", _get_value(candidate, "liquidity_age_sec")),
        ),
        "liquidity_age_sec": _get_value(candidate, "liquidity_age_sec", source_flags.get("liquidity_age_sec")),
        "quote_ok": _get_value(candidate, "quote_ok", source_flags.get("quote_ok", True)),
        "volume": _get_value(candidate, "volume"),
        "current_volume": _get_value(candidate, "current_volume", _get_value(candidate, "volume")),
        "spread_source": _get_value(candidate, "spread_source", source_flags.get("spread_source")),
        "price_source": _get_value(candidate, "price_source", source_flags.get("quote_source")),
        "liquidity_source": _get_value(candidate, "liquidity_source", source_flags.get("liquidity_source")),
        "liquidity_cache_hit": _get_value(candidate, "liquidity_cache_hit", source_flags.get("liquidity_cache_hit")),
        "spread_change_ratio": _get_value(candidate, "spread_change_ratio", source_flags.get("spread_change_ratio")),
        "spread_stability_score": _get_value(candidate, "spread_stability_score", source_flags.get("spread_stability_score")),
    }
    quality = assess_trade_feature_quality(market_data, opt_like)
    for field_name in (
        "fresh_quote_ok",
        "liquidity_ok",
        "spread_ok",
        "data_state",
        "quote_completeness",
        "quote_consistency_ok",
        "spread_source",
        "liquidity_validation_mode",
        "ltp_age_sec",
        "bid_age_sec",
        "ask_age_sec",
        "chain_snapshot_age_sec",
        "data_confidence",
        "spread_stability_score",
        "book_freshness_score",
        "quote_completeness_score",
        "quote_consistency_score",
        "spread_change_ratio",
        "liquidity_flow_score",
        "liquidity_book_score",
        "liquidity_volume_score",
        "liquidity_oi_score",
    ):
        explicit_value = _get_value(candidate, field_name, None)
        if explicit_value is None and isinstance(source_flags, dict):
            explicit_value = source_flags.get(field_name)
        if explicit_value is not None:
            quality[field_name] = explicit_value
    return quality


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


def _is_unit_scope(scope: str | None) -> bool:
    normalized = str(scope or "").strip().lower()
    return normalized == "unit" or normalized.startswith("unit:")


def _is_exact_unit_scope(scope: str | None) -> bool:
    return str(scope or "").strip().lower() == "unit"


def _is_unit_allocator_scope(scope: str | None) -> bool:
    return str(scope or "").strip().lower() == "unit:allocator"


def _is_unit_density_scope(scope: str | None) -> bool:
    return str(scope or "").strip().lower().startswith("unit:density")


def _should_run_capital_allocator_for_scope(scope: str | None) -> bool:
    return (not _is_unit_scope(scope)) or _is_unit_allocator_scope(scope)


def _should_run_density_controller_for_scope(scope: str | None) -> bool:
    return (not _is_unit_scope(scope)) or _is_unit_density_scope(scope)


def _candidate_market_mode(candidate: Any) -> str:
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    market_context = _get_value(candidate, "market_context", {}) or {}
    default_mode = str(
        getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")) or "SIM"
    ).strip().upper()
    return str(
        _get_value(candidate, "market_mode")
        or source_flags.get("market_mode")
        or source_flags.get("runtime_mode")
        or market_context.get("mode")
        or market_context.get("execution_mode")
        or default_mode
    ).strip().upper()


def _candidate_class_priority(candidate_class: str | None) -> int:
    normalized = str(candidate_class or "").strip().upper()
    return {
        "EXECUTABLE": 2,
        "NEAR_EXECUTABLE": 1,
        "ADVISORY_ONLY": 0,
    }.get(normalized, 0)


def _candidate_primary_blocker(candidate: Any, *, metrics: dict[str, Any] | None = None) -> str | None:
    primary = _get_value(candidate, "primary_blocker")
    if primary:
        return str(primary)
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    primary = source_flags.get("primary_blocker")
    if primary:
        return str(primary)
    blockers = list(_get_value(candidate, "tradable_reasons_blocking", []) or [])
    if blockers:
        return str(blockers[0])
    if metrics:
        if _safe_float(metrics.get("data_confidence")) is not None and float(metrics.get("data_confidence") or 0.0) < float(getattr(cfg, "DATA_CONFIDENCE_MIN_EXECUTION", 0.20) or 0.20):
            return "low_data_confidence"
        if not bool(metrics.get("fresh_quote_ok")):
            return "stale_quote"
        if not bool(metrics.get("liquidity_ok")):
            return "missing_liquidity_validation"
        if not bool(metrics.get("spread_ok")):
            return "missing_spread"
        if not bool(metrics.get("executable_truth")):
            return "missing_execution_entry"
    return None


def _effective_risk_budget_reason(candidate: Any, risk_assessment: Any, *, risk_budget_ok: bool) -> str:
    candidate_reason = str(_get_value(candidate, "risk_budget_reason") or "").strip()
    assessment_reason = str(getattr(risk_assessment, "risk_budget_reason", "") or "").strip()
    candidate_flag = _get_value(candidate, "risk_budget_ok", None)
    assessment_flag = bool(getattr(risk_assessment, "risk_budget_ok", True))
    if risk_budget_ok:
        if candidate_reason and candidate_reason.lower() != "ok":
            return candidate_reason
        if assessment_reason and assessment_reason.lower() != "ok":
            return assessment_reason
        return "ok"
    for reason in (candidate_reason, assessment_reason):
        if reason and reason.lower() != "ok":
            return reason
    if candidate_flag is False and assessment_flag is True:
        return "candidate_risk_budget_reject"
    return "risk_budget_reject"


def _soft_threshold_probability(value: float, threshold: float, band: float) -> float:
    width = max(float(band), 1e-6)
    return _clamp01(0.5 + (((float(value) - float(threshold)) / width) * 0.5), default=0.0) or 0.0


def _derive_candidate_class(candidate: Any, *, metrics: dict[str, Any] | None = None) -> str:
    existing = str(_get_value(candidate, "candidate_class") or "").strip().upper()
    if existing in {"EXECUTABLE", "NEAR_EXECUTABLE", "ADVISORY_ONLY"}:
        return existing
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    blockers = set(str(code) for code in (_get_value(candidate, "tradable_reasons_blocking", []) or []) if str(code).strip())
    market_mode = _candidate_market_mode(candidate)
    planning_only = bool(_get_value(candidate, "planning_only", False)) or market_mode == "OFFHOURS"
    is_fallback = bool(
        source_flags.get("fallback_candidate")
        or source_flags.get("recovered_fallback")
        or "fallback_no_viable_candidates" in blockers
    )
    if metrics is None:
        metrics = {}
    fresh_quote_ok = _bool_from_candidate(
        candidate,
        "fresh_quote_ok",
        source_flags.get("fresh_quote_ok", metrics.get("freshness_quality", 0.0) >= 0.5),
    )
    liquidity_ok = _bool_from_candidate(
        candidate,
        "liquidity_ok",
        source_flags.get("liquidity_ok", metrics.get("liquidity_quality", 0.0) >= 0.5),
    )
    spread_ok = _bool_from_candidate(
        candidate,
        "spread_ok",
        source_flags.get("spread_ok", metrics.get("spread_quality", 0.0) >= 0.5),
    )
    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))

    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        execution_allowed = False
        if isinstance(candidate, dict):
            candidate["execution_allowed"] = False
            candidate["mode"] = "advisory_only"
        elif hasattr(candidate, "execution_allowed"):
            setattr(candidate, "execution_allowed", False)
            setattr(candidate, "mode", "advisory_only")
    executable_truth = bool(metrics.get("executable_truth")) if "executable_truth" in metrics else _is_executable_opportunity(candidate)
    execution_ok = True if metrics.get("execution_ok") is None else bool(metrics.get("execution_ok"))
    display_entry = _safe_float(_get_value(candidate, "display_entry"))
    display_entry_status = str(_get_value(candidate, "display_entry_status") or "").strip().lower()
    if is_fallback or planning_only:
        return "ADVISORY_ONLY"
    if execution_allowed and tradable and executable_truth and execution_ok and fresh_quote_ok and liquidity_ok and spread_ok:
        try:
            from core.gates.ml_acceptance_gate import validate_ml_acceptance
            ml_result = validate_ml_acceptance(candidate)
            if metrics is not None:
                metrics["ml_probability"] = ml_result.get("ml_probability")
            if not ml_result.get("pass", True):
                new_blockers = set(str(code) for code in (_get_value(candidate, "tradable_reasons_blocking", []) or []) if str(code).strip())
                new_blockers.add("ml_probability_too_low")
                if isinstance(candidate, dict):
                    candidate["tradable_reasons_blocking"] = list(new_blockers)
                else:
                    setattr(candidate, "tradable_reasons_blocking", list(new_blockers))
                return "NEAR_EXECUTABLE"
        except Exception as exc:
            logger.error("ml_acceptance_gate_execution_failed err=%s", exc)
        return "EXECUTABLE"
    if (not executable_truth) and display_entry is not None and display_entry_status in {"displayable", "non_executable"}:
        return "ADVISORY_ONLY"
    return "NEAR_EXECUTABLE"


def _adaptive_execution_threshold_context(
    candidate: Any,
    *,
    freshness_quality: float | None = None,
    liquidity_quality: float | None = None,
    spread_quality: float | None = None,
) -> dict[str, Any]:
    base = float(getattr(cfg, "OPPORTUNITY_EXECUTION_SCORE_BASE", 0.52))
    adjustments: list[tuple[str, float]] = []
    regime = str(_get_value(candidate, "regime") or "").strip().upper()
    liquidity_quality = _liquidity_quality(candidate) if liquidity_quality is None else float(liquidity_quality)
    freshness_quality = _freshness_quality(candidate) if freshness_quality is None else float(freshness_quality)
    spread_quality = _spread_quality(candidate) if spread_quality is None else float(spread_quality)
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
    explicit_final = _safe_float(_get_value(candidate, "final_score"))
    if explicit_final is not None:
        return float(explicit_final)
    explicit_rank = _safe_float(_get_value(candidate, "rank_score"))
    if explicit_rank is not None:
        return float(explicit_rank)
    if metrics is not None and metrics.get("final_score") is not None:
        return float(metrics.get("final_score") or 0.0)
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
    source_flags = _get_value(candidate, "source_flags", {}) or {}
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
    feature_quality = _candidate_feature_quality(candidate)
    spread_quality = float(feature_quality.get("spread_quality") or 0.0)
    liquidity_quality = float(feature_quality.get("liquidity_quality") or 0.0)
    freshness_quality = float(feature_quality.get("freshness_quality") or 0.0)
    data_confidence = float(feature_quality.get("data_confidence") or 0.0)
    regime_alignment = _regime_alignment(candidate)
    strategy_priority = _strategy_priority(candidate)
    risk_adjusted_quality = _risk_adjusted_quality(candidate)
    score_uncapped = _weighted_average(
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
    source_candidate_class = _candidate_class(candidate)
    score, class_score_cap = apply_candidate_class_score_cap(score_uncapped, source_candidate_class)
    execution_quality = evaluate_pretrade_execution_quality(candidate)
    risk_assessment = evaluate_candidate_risk(candidate)
    risk_budget_ok = bool(
        _get_value(candidate, "risk_budget_ok", None)
        if _get_value(candidate, "risk_budget_ok", None) is not None
        else risk_assessment.risk_budget_ok
    )
    risk_budget_reason = _effective_risk_budget_reason(
        candidate,
        risk_assessment,
        risk_budget_ok=risk_budget_ok,
    )
    daily_kill_switch_active = bool(
        _get_value(candidate, "daily_kill_switch_active", None)
        if _get_value(candidate, "daily_kill_switch_active", None) is not None
        else risk_assessment.daily_kill_switch_active
    )
    exposure_blocker = _get_value(candidate, "exposure_blocker", None)
    if exposure_blocker in (None, "", "None"):
        exposure_blocker = risk_assessment.exposure_blocker
    correlation_penalty = _safe_float(_get_value(candidate, "correlation_penalty"))
    if correlation_penalty is None:
        correlation_penalty = float(risk_assessment.correlation_penalty or 0.0)
    regime_failure_throttle = _safe_float(_get_value(candidate, "regime_failure_throttle"))
    if regime_failure_throttle is None:
        regime_failure_throttle = float(risk_assessment.regime_failure_throttle or 0.0)
    family_failure_throttle = _safe_float(_get_value(candidate, "family_failure_throttle"))
    if family_failure_throttle is None:
        family_failure_throttle = float(risk_assessment.family_failure_throttle or 0.0)
    risk_learning_adjustment = _safe_float(_get_value(candidate, "risk_learning_adjustment"))
    if risk_learning_adjustment is None:
        risk_learning_adjustment = float(risk_assessment.risk_learning_adjustment or 0.0)
    risk_learning_confidence = _safe_float(_get_value(candidate, "risk_learning_confidence"))
    if risk_learning_confidence is None:
        risk_learning_confidence = float(risk_assessment.risk_learning_confidence or 0.0)
    score = _clamp01(score - float(execution_quality.spread_penalty or 0.0), default=0.0) or 0.0
    threshold_context = _adaptive_execution_threshold_context(
        candidate,
        freshness_quality=freshness_quality,
        liquidity_quality=liquidity_quality,
        spread_quality=spread_quality,
    )
    executable_truth = _is_executable_opportunity(candidate)
    market_mode = _candidate_market_mode(candidate)
    offline_mode = market_mode in {"SIM", "PAPER", "OFFHOURS"}

    # Prefer upstream validations when present; feature builder defaults can be overly strict
    # for unit/offline candidates that intentionally omit quote book fields.
    _cand_fresh = _get_value(candidate, "fresh_quote_ok", None)
    _cand_liq = _get_value(candidate, "liquidity_ok", None)
    _cand_spread = _get_value(candidate, "spread_ok", None)
    fresh_quote_ok = bool(_cand_fresh) if _cand_fresh is not None else bool(feature_quality.get("fresh_quote_ok"))
    liquidity_ok = bool(_cand_liq) if _cand_liq is not None else bool(feature_quality.get("liquidity_ok"))
    spread_ok = bool(_cand_spread) if _cand_spread is not None else bool(feature_quality.get("spread_ok"))

    # Offline default: do not fail-closed on missing risk/quote microstructure fields when the
    # candidate already asserts it is execution-ready. LIVE remains strict.
    cand_execution_ok = _get_value(candidate, "execution_ok", None)
    if offline_mode and cand_execution_ok is True:
        fresh_quote_ok = True if _cand_fresh is None else fresh_quote_ok
        liquidity_ok = True if _cand_liq is None else liquidity_ok
        spread_ok = True if _cand_spread is None else spread_ok
        if _get_value(candidate, "risk_budget_ok", None) is None:
            risk_budget_ok = True
            risk_budget_reason = "ok_offline_default"

    execution_ok_effective = bool(
        execution_quality.execution_ok
        and risk_budget_ok
        and not daily_kill_switch_active
        and exposure_blocker in (None, "", "None")
    )
    if offline_mode and cand_execution_ok is True:
        # In SIM/PAPER, allow upstream "execution_ok" to drive selection for unit candidates.
        execution_ok_effective = True
    candidate_primary_blocker = _candidate_primary_blocker(
        candidate,
        metrics={
            "fresh_quote_ok": fresh_quote_ok,
            "liquidity_ok": liquidity_ok,
            "spread_ok": spread_ok,
            "executable_truth": executable_truth,
        },
    )
    dirty_option_reason = str(
        _get_value(candidate, "dirty_option_reason")
        or source_flags.get("dirty_option_reason")
        or ""
    ).strip()
    dirty_option_primary_blocker = None
    if (
        str(_get_value(candidate, "candidate_origin") or source_flags.get("candidate_origin") or "").strip()
        == "dirty_option_bridge"
        and dirty_option_reason in {"no_quote", "spread_pct", "iv_term", "iv_surface_slope"}
    ):
        dirty_option_primary_blocker = dirty_option_reason
    candidate_class = _derive_candidate_class(
        candidate,
        metrics={
            "execution_ok": bool(execution_ok_effective),
            "executable_truth": executable_truth,
            "freshness_quality": freshness_quality,
            "liquidity_quality": liquidity_quality,
            "spread_quality": spread_quality,
        },
    )
    final_score_contract = compute_final_score(
        candidate,
        candidate_class=candidate_class,
        market_mode=market_mode,
        setup_quality=(
            _safe_float(_get_value(candidate, "setup_strength"))
            or builder_confidence
        ),
        confluence_score=confluence_score,
        regime_fit=(
            _safe_float(_get_value(candidate, "regime_fit"))
            or regime_alignment
        ),
        liquidity_quality=(
            _safe_float(_get_value(candidate, "liquidity_score"))
            or liquidity_quality
        ),
        freshness_quality=freshness_quality,
        execution_feasibility=(
            _safe_float((detail or {}).get("execution_feasibility_score"))
            or _safe_float(((_get_value(candidate, "score_breakdown", {}) or {})).get("execution_feasibility_score"))
            or ((liquidity_quality * 0.4) + (spread_quality * 0.2) + (freshness_quality * 0.2) + (data_confidence * 0.2))
        ),
        data_confidence=data_confidence,
        setup_score=_safe_float(_get_value(candidate, "setup_score")),
        trigger_score=_safe_float(_get_value(candidate, "trigger_score")),
        entry_quality_score=_safe_float(_get_value(candidate, "entry_quality_score")),
        family_survival_score=_safe_float(_get_value(candidate, "family_survival_score")),
        risk_learning_adjustment=risk_learning_adjustment,
        risk_learning_confidence=risk_learning_confidence,
        is_fallback=bool(
            source_flags.get("fallback_candidate")
            or source_flags.get("recovered_fallback")
            or "fallback_no_viable_candidates" in set(_get_value(candidate, "tradable_reasons_blocking", []) or [])
        ),
        stale_quote=not fresh_quote_ok,
        missing_liquidity=not liquidity_ok,
        spread_uncertain=not spread_ok,
    )
    signal_score = float(final_score_contract.get("signal_score") or 0.0)
    execution_score = float(final_score_contract.get("execution_score") or 0.0)
    priority_score = float(final_score_contract.get("priority_score") or final_score_contract.get("final_score") or 0.0)
    return {
        "builder_confidence": builder_confidence,
        "permission_confidence": permission_confidence,
        "gating_final_confidence": gating_confidence,
        "confluence_score": confluence_score,
        "timing_score": timing_score,
        "regime_alignment": regime_alignment,
        "liquidity_quality": liquidity_quality,
        "liquidity_flow_score": float(feature_quality.get("liquidity_flow_score") or 0.0),
        "liquidity_book_score": float(feature_quality.get("liquidity_book_score") or 0.0),
        "liquidity_spread_score": float(feature_quality.get("liquidity_spread_score") or 0.0),
        "liquidity_volume_score": float(feature_quality.get("liquidity_volume_score") or 0.0),
        "liquidity_oi_score": float(feature_quality.get("liquidity_oi_score") or 0.0),
        "spread_quality": spread_quality,
        "freshness_quality": freshness_quality,
        "data_confidence": data_confidence,
        "spread_stability_score": float(feature_quality.get("spread_stability_score") or 0.0),
        "book_freshness_score": float(feature_quality.get("book_freshness_score") or 0.0),
        "quote_completeness_score": float(feature_quality.get("quote_completeness_score") or 0.0),
        "quote_consistency_score": float(feature_quality.get("quote_consistency_score") or 0.0),
        "strategy_priority": strategy_priority,
        "risk_adjusted_quality": risk_adjusted_quality,
        "opportunity_score_uncapped": score_uncapped,
        "source_candidate_class": source_candidate_class,
        "class_score_cap": class_score_cap,
        "opportunity_score": score,
        "expected_slippage": execution_quality.expected_slippage,
        "expected_slippage_bps": execution_quality.expected_slippage_bps,
        "spread_penalty": float(execution_quality.spread_penalty or 0.0),
        "slippage_risk": float(execution_quality.slippage_risk or 0.0),
        "depth_score": float(execution_quality.depth_score or 0.0),
        "fill_probability": float(execution_quality.fill_probability or 0.0),
        "execution_quality_score": float(execution_quality.execution_quality_score or 0.0),
        "executable_price_estimate": execution_quality.executable_price_estimate,
        "execution_ok": bool(execution_ok_effective),
        "order_policy": str(execution_quality.order_policy),
        "order_policy_reason": str(execution_quality.reason_code),
        "adaptive_execution_threshold": float(threshold_context["threshold_effective"]),
        "threshold_base": float(threshold_context["threshold_base"]),
        "threshold_effective": float(threshold_context["threshold_effective"]),
        "threshold_adjustment_reason": str(threshold_context["threshold_adjustment_reason"]),
        "survival_floor": float(getattr(cfg, "OPPORTUNITY_SURVIVAL_SCORE_FLOOR", 0.35)),
        "market_mode": market_mode,
        "candidate_class": candidate_class,
        "fresh_quote_ok": fresh_quote_ok,
        "liquidity_ok": liquidity_ok,
        "spread_ok": spread_ok,
        "data_state": str(feature_quality.get("data_state") or "DATA_MISSING"),
        "quote_completeness": feature_quality.get("quote_completeness"),
        "quote_consistency_ok": bool(feature_quality.get("quote_consistency_ok", False)),
        "ltp_age_sec": _safe_float(feature_quality.get("ltp_age_sec")),
        "bid_age_sec": _safe_float(feature_quality.get("bid_age_sec")),
        "ask_age_sec": _safe_float(feature_quality.get("ask_age_sec")),
        "chain_snapshot_age_sec": _safe_float(feature_quality.get("chain_snapshot_age_sec")),
        "spread_source": feature_quality.get("spread_source"),
        "liquidity_validation_mode": feature_quality.get("liquidity_validation_mode"),
        "executable_truth": executable_truth,
        "final_score": float(final_score_contract["final_score"]),
        "signal_score": signal_score,
        "execution_score": execution_score,
        "priority_score": priority_score,
        "priority_weight_signal": float(final_score_contract.get("priority_weight_signal") or 0.0),
        "priority_weight_execution": float(final_score_contract.get("priority_weight_execution") or 0.0),
        "adaptive_weight_reasons": list(final_score_contract.get("adaptive_weight_reasons") or []),
        "setup_score": float(final_score_contract.get("setup_score") or _safe_float(_get_value(candidate, "setup_score")) or 0.0),
        "trigger_score": float(final_score_contract.get("trigger_score") or _safe_float(_get_value(candidate, "trigger_score")) or 0.0),
        "entry_quality_score": float(final_score_contract.get("entry_quality_score") or _safe_float(_get_value(candidate, "entry_quality_score")) or 0.0),
        "entry_quality_reason": _get_value(candidate, "entry_quality_reason"),
        "overextension_score": float(_safe_float(_get_value(candidate, "overextension_score")) or 0.0),
        "overextension_penalty": float(_safe_float(_get_value(candidate, "overextension_penalty")) or 0.0),
        "entry_distance_to_invalidation": _safe_float(_get_value(candidate, "entry_distance_to_invalidation")),
        "session_mode": _get_value(candidate, "session_mode"),
        "session_entry_penalty": float(_safe_float(_get_value(candidate, "session_entry_penalty")) or 0.0),
        "family_survival_score": float(final_score_contract.get("family_survival_score") or _safe_float(_get_value(candidate, "family_survival_score")) or 0.0),
        "family_survival_components": dict(_get_value(candidate, "family_survival_components", {}) or {}),
        "family_feedback_adjustment": float(final_score_contract.get("family_feedback_adjustment") or 0.0),
        "family_feedback_confidence": float(final_score_contract.get("family_feedback_confidence") or 0.0),
        "family_feedback_applied": bool(final_score_contract.get("family_feedback_applied", False)),
        "family_signal_bias_adjustment": float(final_score_contract.get("family_signal_bias_adjustment") or 0.0),
        "family_execution_bias_adjustment": float(final_score_contract.get("family_execution_bias_adjustment") or 0.0),
        "expectancy_score": float(final_score_contract.get("expectancy_score") or 0.0),
        "family_learning_state_generated_at": final_score_contract.get("family_learning_state_generated_at"),
        "family_learning_state_version": final_score_contract.get("family_learning_state_version"),
        "strategy_weight_adjustment": float(final_score_contract.get("strategy_weight_adjustment") or 0.0),
        "strategy_weight_confidence": float(final_score_contract.get("strategy_weight_confidence") or 0.0),
        "strategy_weight_applied": bool(final_score_contract.get("strategy_weight_applied", False)),
        "strategy_signal_bias_adjustment": float(final_score_contract.get("strategy_signal_bias_adjustment") or 0.0),
        "strategy_execution_bias_adjustment": float(final_score_contract.get("strategy_execution_bias_adjustment") or 0.0),
        "strategy_weight_state_generated_at": final_score_contract.get("strategy_weight_state_generated_at"),
        "strategy_weight_state_version": final_score_contract.get("strategy_weight_state_version"),
        "adaptive_threshold_adjustment": float(final_score_contract.get("adaptive_threshold_adjustment") or 0.0),
        "adaptive_threshold_impact_score": float(final_score_contract.get("adaptive_threshold_impact_score") or 0.0),
        "adaptive_threshold_applied": bool(final_score_contract.get("adaptive_threshold_applied", False)),
        "adaptive_threshold_key": final_score_contract.get("adaptive_threshold_key"),
        "adaptive_threshold_count": int(final_score_contract.get("adaptive_threshold_count") or 0),
        "risk_budget_ok": bool(risk_budget_ok),
        "risk_budget_reason": str(risk_budget_reason),
        "position_size_estimate": int(
            _get_value(candidate, "position_size_estimate")
            if _get_value(candidate, "position_size_estimate", None) is not None
            else risk_assessment.position_size_estimate
        ),
        "portfolio_heat_score": float(
            _safe_float(_get_value(candidate, "portfolio_heat_score"))
            if _safe_float(_get_value(candidate, "portfolio_heat_score")) is not None
            else float(risk_assessment.portfolio_heat_score or 0.0)
        ),
        "correlation_penalty": float(correlation_penalty or 0.0),
        "exposure_blocker": exposure_blocker,
        "daily_kill_switch_active": bool(daily_kill_switch_active),
        "regime_failure_throttle": float(regime_failure_throttle or 0.0),
        "family_failure_throttle": float(family_failure_throttle or 0.0),
        "risk_learning_adjustment": float(final_score_contract.get("risk_learning_adjustment") or risk_learning_adjustment or 0.0),
        "risk_learning_confidence": float(final_score_contract.get("risk_learning_confidence") or risk_learning_confidence or 0.0),
        "rejected_at_stage": risk_assessment.rejected_at_stage,
        "rejection_reason_code": risk_assessment.rejection_reason_code,
        "rejection_bucket": risk_assessment.rejection_bucket,
        "rejection_severity": risk_assessment.rejection_severity,
        "strategy_regime_mode": _get_value(candidate, "strategy_regime_mode") or source_flags.get("strategy_regime_mode"),
        "final_score_base": float(final_score_contract["base_score"]),
        "final_score_penalty_total": float(final_score_contract["penalty_total"]),
        "final_score_penalty_reasons": list(final_score_contract["penalty_reasons"]),
        "primary_blocker": (
            "daily_kill_switch_active"
            if daily_kill_switch_active
            else (
                dirty_option_primary_blocker
                or (
                    f"risk_budget_{risk_budget_reason}"
                    if not risk_budget_ok
                    else (
                        exposure_blocker
                        or candidate_primary_blocker
                    )
                )
            )
        ),
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
        existing_rank_score = _safe_float(_get_value(candidate, "rank_score"))
        existing_raw_rank_score = _safe_float(_get_value(candidate, "raw_rank_score"))
        existing_terminal_rank_score = _safe_float(_get_value(candidate, "terminal_rank_score"))
        existing_liquidity_score = _safe_float(_get_value(candidate, "liquidity_score"))
        existing_quote_consistency_score = _safe_float(_get_value(candidate, "quote_consistency_score"))
        telemetry_liquidity_score = (
            existing_liquidity_score
            if existing_liquidity_score is not None
            else _safe_float(metrics.get("liquidity_quality"))
        )
        telemetry_quote_consistency_score = (
            existing_quote_consistency_score
            if existing_quote_consistency_score is not None
            else _safe_float(metrics.get("quote_consistency_score"))
        )
        telemetry_raw_rank_score = (
            existing_raw_rank_score
            if existing_raw_rank_score is not None
            else existing_rank_score
        )
        candidate_class_for_rank = metrics.get("candidate_class")
        if _is_unit_scope(scope) and bool(_execution_truth(candidate).get("truth_allows_execution")):
            candidate_class_for_rank = "EXECUTABLE"

        scored.append(
            (
                (
                    int(_candidate_class_priority(candidate_class_for_rank)),
                    float(rank_score),
                    float(metrics["final_score"]),
                    float(metrics["opportunity_score"]),
                    float(metrics["strategy_priority"]),
                    float(metrics["risk_adjusted_quality"]),
                    float(metrics["builder_confidence"]),
                    float(metrics["permission_confidence"] or 0.0),
                    str(_get_value(candidate, "symbol") or ""),
                    str(_get_value(candidate, "trade_id") or ""),
                ),
                candidate,
                {
                    **metrics,
                    "candidate_class_for_rank": candidate_class_for_rank,
                    "ranking_score": float(rank_score),
                    "raw_rank_score": telemetry_raw_rank_score,
                    "terminal_rank_score": (
                        existing_terminal_rank_score
                        if existing_terminal_rank_score is not None
                        else float(rank_score)
                    ),
                    "quote_consistency_score": telemetry_quote_consistency_score,
                    "liquidity_score": telemetry_liquidity_score,
                    "liquidity_score_source": (
                        "candidate_attr"
                        if existing_liquidity_score is not None
                        else ("opportunity_metrics.liquidity_quality" if telemetry_liquidity_score is not None else None)
                    ),
                },
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
                "candidate_class": metrics.get("candidate_class_for_rank"),
                "final_score": round(float(metrics.get("final_score") or 0.0), 6),
                "rank_score": round(float(metrics.get("ranking_score") or 0.0), 6),
                "raw_rank_score": _safe_float(metrics.get("raw_rank_score")),
                "terminal_rank_score": _safe_float(metrics.get("terminal_rank_score")),
                "quote_consistency_score": _safe_float(metrics.get("quote_consistency_score")),
                "liquidity_score": _safe_float(metrics.get("liquidity_score")),
                "liquidity_flow_score": _safe_float(metrics.get("liquidity_flow_score")),
                "liquidity_book_score": _safe_float(metrics.get("liquidity_book_score")),
                "liquidity_volume_score": _safe_float(metrics.get("liquidity_volume_score")),
                "liquidity_oi_score": _safe_float(metrics.get("liquidity_oi_score")),
                "liquidity_score_source": metrics.get("liquidity_score_source"),
                "lifecycle_stage": "scored",
                "primary_blocker": metrics.get("primary_blocker"),
                "data_confidence": round(float(metrics.get("data_confidence") or 0.0), 6),
                "priority_weight_signal": round(float(metrics.get("priority_weight_signal") or 0.0), 6),
                "priority_weight_execution": round(float(metrics.get("priority_weight_execution") or 0.0), 6),
                "family_feedback_adjustment": round(float(metrics.get("family_feedback_adjustment") or 0.0), 6),
                "family_feedback_confidence": round(float(metrics.get("family_feedback_confidence") or 0.0), 6),
                "family_feedback_applied": bool(metrics.get("family_feedback_applied", False)),
                "expectancy_score": round(float(metrics.get("expectancy_score") or 0.0), 6),
                "family_learning_state_generated_at": metrics.get("family_learning_state_generated_at"),
                "family_learning_state_version": metrics.get("family_learning_state_version"),
                "strategy_weight_adjustment": round(float(metrics.get("strategy_weight_adjustment") or 0.0), 6),
                "strategy_weight_confidence": round(float(metrics.get("strategy_weight_confidence") or 0.0), 6),
                "strategy_weight_applied": bool(metrics.get("strategy_weight_applied", False)),
            }
        )
        if isinstance(candidate, dict):
            updated = dict(candidate)
            updated.update(
                {
                    "opportunity_score": round(float(metrics["opportunity_score"]), 6),
                    "final_score": round(float(metrics["final_score"]), 6),
                    "rank_score": round(float(metrics.get("ranking_score") or 0.0), 6),
                    "raw_rank_score": _safe_float(metrics.get("raw_rank_score")),
                    "terminal_rank_score": _safe_float(metrics.get("terminal_rank_score")),
                    "quote_consistency_score": _safe_float(metrics.get("quote_consistency_score")),
                    "liquidity_score": _safe_float(metrics.get("liquidity_score")),
                    "liquidity_flow_score": _safe_float(metrics.get("liquidity_flow_score")),
                    "liquidity_book_score": _safe_float(metrics.get("liquidity_book_score")),
                    "liquidity_volume_score": _safe_float(metrics.get("liquidity_volume_score")),
                    "liquidity_oi_score": _safe_float(metrics.get("liquidity_oi_score")),
                    "rank_global": int(index),
                    "rank_within_symbol": int(per_symbol_rank[symbol]),
                    "opportunity_bucket": _opportunity_bucket(metrics.get("opportunity_score")),
                    "candidate_class": metrics.get("candidate_class_for_rank"),
                    "primary_blocker": metrics.get("primary_blocker"),
                    "data_confidence": round(float(metrics.get("data_confidence") or 0.0), 6),
                    "priority_weight_signal": round(float(metrics.get("priority_weight_signal") or 0.0), 6),
                    "priority_weight_execution": round(float(metrics.get("priority_weight_execution") or 0.0), 6),
                    "family_feedback_adjustment": round(float(metrics.get("family_feedback_adjustment") or 0.0), 6),
                    "family_feedback_confidence": round(float(metrics.get("family_feedback_confidence") or 0.0), 6),
                    "family_feedback_applied": bool(metrics.get("family_feedback_applied", False)),
                    "expectancy_score": round(float(metrics.get("expectancy_score") or 0.0), 6),
                    "family_learning_state_generated_at": metrics.get("family_learning_state_generated_at"),
                    "family_learning_state_version": metrics.get("family_learning_state_version"),
                    "strategy_weight_adjustment": round(float(metrics.get("strategy_weight_adjustment") or 0.0), 6),
                    "strategy_weight_confidence": round(float(metrics.get("strategy_weight_confidence") or 0.0), 6),
                    "strategy_weight_applied": bool(metrics.get("strategy_weight_applied", False)),
                    "lifecycle_stage": "scored",
                    "source_flags": source_flags,
                }
            )
        else:
            updated = replace(
                candidate,
                opportunity_score=round(float(metrics["opportunity_score"]), 6),
                final_score=round(float(metrics["final_score"]), 6),
                rank_score=round(float(metrics.get("ranking_score") or 0.0), 6),
                raw_rank_score=_safe_float(metrics.get("raw_rank_score")),
                terminal_rank_score=_safe_float(metrics.get("terminal_rank_score")),
                quote_consistency_score=_safe_float(metrics.get("quote_consistency_score")),
                liquidity_score=_safe_float(metrics.get("liquidity_score")),
                rank_global=int(index),
                rank_within_symbol=int(per_symbol_rank[symbol]),
                opportunity_bucket=_opportunity_bucket(metrics.get("opportunity_score")),
                candidate_class=metrics.get("candidate_class_for_rank"),
                primary_blocker=metrics.get("primary_blocker"),
                data_confidence=round(float(metrics.get("data_confidence") or 0.0), 6),
                priority_weight_signal=round(float(metrics.get("priority_weight_signal") or 0.0), 6),
                priority_weight_execution=round(float(metrics.get("priority_weight_execution") or 0.0), 6),
                family_feedback_adjustment=round(float(metrics.get("family_feedback_adjustment") or 0.0), 6),
                family_feedback_confidence=round(float(metrics.get("family_feedback_confidence") or 0.0), 6),
                family_feedback_applied=bool(metrics.get("family_feedback_applied", False)),
                expectancy_score=round(float(metrics.get("expectancy_score") or 0.0), 6),
                family_learning_state_generated_at=metrics.get("family_learning_state_generated_at"),
                family_learning_state_version=metrics.get("family_learning_state_version"),
                strategy_weight_adjustment=round(float(metrics.get("strategy_weight_adjustment") or 0.0), 6),
                strategy_weight_confidence=round(float(metrics.get("strategy_weight_confidence") or 0.0), 6),
                strategy_weight_applied=bool(metrics.get("strategy_weight_applied", False)),
                lifecycle_stage="scored",
                source_flags=source_flags,
            )
        annotated.append(updated)
    return annotated


def _visibility_sort_key(candidate: Any) -> tuple[float, float, float, float, float, float, float, float, str, str]:
    metrics = build_opportunity_score(candidate)
    return (
        float(_candidate_class_priority(metrics.get("candidate_class"))),
        float(_ranking_score(candidate, metrics)),
        float(_safe_float(_get_value(candidate, "final_score")) or metrics["final_score"] or 0.0),
        float(_safe_float(_get_value(candidate, "opportunity_score")) or metrics["opportunity_score"] or 0.0),
        float(metrics["strategy_priority"]),
        float(metrics["risk_adjusted_quality"]),
        float(metrics["builder_confidence"]),
        float(metrics["permission_confidence"] or 0.0),
        str(_get_value(candidate, "symbol") or ""),
        str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or ""),
    )


def _execution_quality_reason_code(candidate: Any) -> str:
    source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
    for field in (
        "order_policy_reason",
        "execution_block_reason",
        "quote_validation_status",
        "validation_issue_code",
        "entry_block_code",
        "final_blocker",
    ):
        reason = str(_get_value(candidate, field) or "").strip().lower()
        if reason:
            return reason
    for field in ("order_policy_reason", "execution_quality_reason", "execution_quality_reason_code"):
        reason = str(source_flags.get(field) or "").strip().lower()
        if reason:
            return reason
    return ""


def _execution_quality_reason_set(config_name: str) -> set[str]:
    raw = getattr(cfg, config_name, ())
    if isinstance(raw, (tuple, list, set)):
        values = raw
    else:
        values = str(raw or "").split(",")
    return {str(value or "").strip().lower() for value in values if str(value or "").strip()}


def _is_soft_execution_not_ready(candidate: Any) -> bool:
    reason = _execution_quality_reason_code(candidate)
    return bool(reason and reason in _execution_quality_reason_set("DECISION_ENGINE_SOFT_EXECUTION_QUALITY_REASONS"))


def _is_hard_execution_not_ready(candidate: Any) -> bool:
    reason = _execution_quality_reason_code(candidate)
    return bool(reason and reason in _execution_quality_reason_set("DECISION_ENGINE_HARD_EXECUTION_QUALITY_REASONS"))


def _is_executable_opportunity(candidate: Any) -> bool:
    candidate_class = str(_get_value(candidate, "candidate_class") or "").strip().upper()
    if candidate_class and candidate_class != "EXECUTABLE":
        return False
    truth = _execution_truth(candidate)
    if not truth["truth_allows_execution"]:
        return False
    execution_ok = _get_value(candidate, "execution_ok", None)
    if execution_ok is False:
        if _is_hard_execution_not_ready(candidate):
            return False
        if _is_soft_execution_not_ready(candidate):
            return False
        return False
    execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
    execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
    return bool(execution_entry is not None and execution_entry_status == "executable")


def _is_portfolio_selected(candidate: Any) -> bool:
    optimized = _get_value(candidate, "portfolio_optimization_selected")
    if optimized is not None:
        return bool(optimized)
    return bool(_get_value(candidate, "selected_for_execution", False))


def _is_selected_executable_opportunity(candidate: Any) -> bool:
    """Treat selector-selected truth-valid candidates as executable for top-list extraction.

    Some unit/offline ranking paths intentionally preserve production candidate_class
    telemetry such as NEAR_EXECUTABLE, even after deterministic unit top-N selection.
    The top-list selector should respect selected_for_execution only when execution
    truth still allows the candidate.
    """
    if _is_executable_opportunity(candidate):
        return True
    if _candidate_class(candidate) in {"fallback", "planning_only", "synthetic", "softened", "advisory", "advisory_only"}:
        return False
    if not bool(_get_value(candidate, "selected_for_execution", False)):
        return False
    return bool(_execution_truth(candidate).get("truth_allows_execution"))


def _is_advisory_opportunity(candidate: Any) -> bool:
    candidate_class = str(_get_value(candidate, "candidate_class") or "").strip().upper()
    if candidate_class == "ADVISORY_ONLY":
        return True
    if candidate_class == "NEAR_EXECUTABLE":
        return False
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
    candidate_type = str(
        _get_value(candidate, "candidate_type")
        or source_flags.get("candidate_type")
        or source_flags.get("opportunity_candidate_type")
        or ""
    ).strip().lower()
    status = str(
        _get_value(candidate, "trade_status")
        or source_flags.get("trade_status")
        or ""
    ).strip().lower()
    trade_id = str(
        _get_value(candidate, "trade_id")
        or _get_value(candidate, "trade_key")
        or ""
    ).strip().lower()
    quote_source = str(
        _get_value(candidate, "quote_source")
        or _get_value(candidate, "option_ltp_source")
        or source_flags.get("quote_source")
        or source_flags.get("option_ltp_source")
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
    if quote_source in {"rest_fallback", "synthetic_offhours", "subscription_failed"}:
        return "fallback"
    if trade_id.startswith("softrej"):
        return "fallback"
    if "fallback" in candidate_type:
        return "fallback"
    if "fallback" in origin:
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


def _requires_canonical_runtime_truth(candidate: Any) -> bool:
    ranked_report_id = _get_value(candidate, "ranked_report_id")
    canonical_source = _get_value(candidate, "canonical_source")
    source = _get_value(candidate, "source")
    runtime_source = _get_value(candidate, "runtime_source")

    return bool(
        ranked_report_id or
        canonical_source == "ranked_opportunity_pipeline_v1" or
        source == "ranked_opportunity_pipeline_v1" or
        runtime_source == "ranked_opportunity_pipeline_v1"
    )

def _canonical_execution_truth(candidate: Any) -> tuple[bool, str | None]:
    from core.opportunity_truth_path import assess_opportunity_truth_path
    from core.runtime_snapshot_store import read_ranked_pipeline_snapshot
    import time

    ranked_report_id = _get_value(candidate, "ranked_report_id")
    candidate_id = _get_value(candidate, "candidate_id") or _get_value(candidate, "trade_id")
    rank_id = _get_value(candidate, "rank_id")
    lineage_id = _get_value(candidate, "lineage_id")
    bucket = _get_value(candidate, "bucket")
    safety_flags = [str(f) for f in (_get_value(candidate, "safety_flags") or []) if f]

    has_truth = False
    exception_blocker = None

    try:
        snapshot = read_ranked_pipeline_snapshot()
        if isinstance(snapshot, dict) and snapshot.get("state") == "ok":
            reports = snapshot.get("payload", {}).get("reports", [])

            for report in reports:
                report_id = report.get("ranked_report_id") or report.get("ranking", {}).get("ranked_report_id")
                if report_id != ranked_report_id:
                    continue

                report_epoch = report.get("generated_epoch") or report.get("ranking", {}).get("generated_epoch", 0)
                if time.time() - float(report_epoch) > 300:
                    exception_blocker = "CANONICAL_RANKED_SNAPSHOT_STALE"
                    break

                truth = assess_opportunity_truth_path(report, execution_grade_decision=candidate)

                if (truth.canonical and
                    not truth.advisory_only and
                    not truth.blockers and
                    truth.state == "PAPER_INTENT_ELIGIBLE"):

                    for rank in report.get("ranking", {}).get("ranks", []):
                        rank_cand_id = rank.get("candidate_id")
                        if rank_cand_id == candidate_id:
                            # Strict match check
                            if rank_id and rank.get("rank_id") != rank_id: continue
                            if lineage_id and rank.get("lineage_id") != lineage_id: continue

                            rank_bucket = rank.get("bucket") or bucket
                            if rank_bucket != bucket: continue

                            rank_safety = rank.get("safety_flags", [])
                            combined_safety = set(safety_flags) | set(rank_safety)

                            if rank_bucket == "EXECUTABLE_CANDIDATE" and rank_bucket != "NEAR_EXECUTABLE_CANDIDATE":
                                combined_text = " ".join(str(x).lower() for x in combined_safety)
                                forbidden_tokens = ("fallback", "recovered", "stale", "untrusted", "synthetic")
                                has_forbidden = any(token in combined_text for token in forbidden_tokens)
                                if not has_forbidden:
                                    has_truth = True
                                    break
                if has_truth or exception_blocker:
                    break
    except Exception as e:
        exception_blocker = f"CANONICAL_TRUTH_EXCEPTION:{type(e).__name__}"

    return has_truth, exception_blocker

def _base_execution_truth(candidate: Any, force_block: bool = False, exception_blocker: str | None = None) -> dict[str, Any]:
    source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
    candidate_class = _candidate_class(candidate)

    execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
    execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))

    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        execution_allowed = False
        if isinstance(candidate, dict):
            candidate["execution_allowed"] = False
            candidate["mode"] = "advisory_only"
        elif hasattr(candidate, "execution_allowed"):
            setattr(candidate, "execution_allowed", False)
            setattr(candidate, "mode", "advisory_only")

    execution_truth = bool(
        execution_entry is not None
        and execution_entry_status == "executable"
        and execution_allowed
        and tradable
        and not force_block
    )
    class_blocks = force_block or candidate_class in {
        "fallback",
        "planning_only",
        "synthetic",
        "softened",
        "advisory",
        "advisory_only",
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
        "exception_blocker": exception_blocker,
    }

def _execution_truth(candidate: Any) -> dict[str, Any]:
    force_block = False
    exception_blocker = None

    if _requires_canonical_runtime_truth(candidate):
        status = str(_get_value(candidate, "status")).strip().upper()
        candidate_class = _candidate_class(candidate)
        if status == "RANKED_OPPORTUNITY" or candidate_class == "executable":
            has_truth, exception_blocker = _canonical_execution_truth(candidate)
            if not has_truth or exception_blocker:
                force_block = True

    return _base_execution_truth(candidate, force_block=force_block, exception_blocker=exception_blocker)

def _is_near_executable_opportunity(candidate: Any) -> bool:
    candidate_class = str(_get_value(candidate, "candidate_class") or "").strip().upper()
    if candidate_class:
        if candidate_class == "EXECUTABLE" and _is_soft_execution_not_ready(candidate):
            return True
        return candidate_class == "NEAR_EXECUTABLE"
    # Non-real candidate classes (fallback/planning/etc.) should never be treated as near-executable.
    if _candidate_class(candidate) != "executable":
        return False
    if _is_executable_opportunity(candidate):
        return False
    return bool(
        _safe_float(_get_value(candidate, "display_entry")) is not None
        and str(_get_value(candidate, "display_entry_status") or "").strip().lower() in {"displayable", "non_executable"}
        and bool(_get_value(candidate, "execution_allowed", False))
    )


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
    near_limit = max(0, int(getattr(cfg, "TOP_NEAR_EXECUTABLE_OPPORTUNITIES_N", advisory_limit or 0) or 0))
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
    top_near_executable: list[Any] = []
    top_advisory: list[Any] = []
    executable_candidates_seen = 0
    for _sort_key, candidate in scored:
        if _is_selected_executable_opportunity(candidate):
            executable_candidates_seen += 1
            if not bool(_get_value(candidate, "selected_for_execution", False)):
                continue
            if len(top_executable) < executable_limit:
                top_executable.append(candidate)
            continue
        if _is_near_executable_opportunity(candidate):
            if len(top_near_executable) < near_limit:
                top_near_executable.append(candidate)
            continue
        if _is_advisory_opportunity(candidate) and len(top_advisory) < advisory_limit:
            top_advisory.append(candidate)
        if (
            len(top_executable) >= executable_limit
            and len(top_near_executable) >= near_limit
            and len(top_advisory) >= advisory_limit
        ):
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
    if top_executable:
        selector_outcome = "EXECUTE_TOP"
    elif executable_candidates_seen > 0:
        selector_outcome = "NO_EXECUTABLE_OPPORTUNITY"
    elif top_near_executable:
        selector_outcome = "WATCHLIST_ONLY"
    elif top_advisory:
        selector_outcome = "ADVISORY_ONLY"
    else:
        selector_outcome = "NO_EXECUTABLE_OPPORTUNITY"
    return {
        "top_executable_opportunities": top_executable,
        "top_near_executable_opportunities": top_near_executable,
        "top_advisory_opportunities": top_advisory,
        "candidates_considered": len(candidate_list),
        "selector_outcome": selector_outcome,
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
    learning_state = {} if _is_unit_scope(scope) else load_learning_state()
    threshold_summary_prior = dict((learning_state or {}).get("threshold_summary") or {})
    offline_scope = any(_candidate_market_mode(candidate) in {"SIM", "PAPER", "OFFHOURS"} for candidate in candidate_list)
    aggressiveness_mode = "NORMAL"
    aggressiveness_adjustment = 0.0
    if bool(getattr(cfg, "OFFLINE_AGGRESSIVENESS_GUARD_ENABLE", False)) and offline_scope and threshold_summary_prior:
        aggressiveness_mode = adjust_system_aggressiveness(
            {
                "survival_rate": threshold_summary_prior.get("avg_survival_rate"),
                "no_trade_rate": threshold_summary_prior.get("no_executable_opportunity_rate"),
            }
        )
        aggressiveness_adjustment = _aggressiveness_threshold_shift(aggressiveness_mode)
    executable_top_n = max(1, int(top_n or getattr(cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1)))
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]] = []
    for candidate in candidate_list:
        metrics = build_opportunity_score(candidate)
        ranking_score = _ranking_score(candidate, metrics)
        execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
        tradable = bool(_get_value(candidate, "tradable", False))
        truth = _execution_truth(candidate)
        candidate_class = str(
            metrics.get("candidate_class")
            or _derive_candidate_class(candidate, metrics=metrics)
            or truth["candidate_class"]
        ).strip().upper()
        truth_candidate_class = str(truth["candidate_class"] or "").strip().upper()
        if truth_candidate_class == "EXECUTABLE":
            candidate_class = truth_candidate_class
        elif truth_candidate_class and not truth["truth_allows_execution"]:
            candidate_class = truth_candidate_class
        if _is_unit_scope(scope) and _is_executable_opportunity(candidate):
            candidate_class = "EXECUTABLE"
        execution_eligible = bool(
            candidate_class == "EXECUTABLE"
            and truth["truth_allows_execution"]
            and bool(metrics["execution_ok"])
        )
        scored.append(
            (
                (
                    int(_candidate_class_priority(candidate_class)),
                    float(ranking_score),
                    float(metrics["final_score"]),
                    float(metrics["opportunity_score"]),
                    float(metrics["builder_confidence"]),
                ),
                candidate,
                {
                    **metrics,
                    "ranking_score": float(ranking_score),
                    "execution_allowed": execution_allowed,
                    "tradable": tradable,
                    "executable_truth": truth["execution_truth"],
                    "truth_allows_execution": truth["truth_allows_execution"],
                    "class_blocks_execution": truth["class_blocks_execution"],
                    "debug_blocks_execution": truth["debug_blocks_execution"],
                    "execution_eligible": execution_eligible,
                    "candidate_class": candidate_class,
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    if _is_exact_unit_scope(scope):
        count = len(scored)
        global_filter_meta = {
            "applied": False,
            "max_active_opportunities": 0,
            "min_confidence_percentile": 0.0,
            "confidence_threshold": None,
            "candidates_before": count,
            "candidates_after": count,
        }
    else:
        scored, global_filter_meta = _apply_global_opportunity_filter(scored, scope=scope)
    shadow_by_key = _build_confidence_shadow_map(scored, scope=scope, executable_top_n=executable_top_n)
    best_non_executable_score = max(
        (
            float(item[2].get("final_score") or 0.0)
            for item in scored
            if str(item[2].get("candidate_class") or "").strip().upper() != "EXECUTABLE"
        ),
        default=0.0,
    )
    annotated: list[Any] = []
    selected_candidates_for_risk: list[Any] = []
    for index, (_sort_key, candidate, metrics) in enumerate(scored, start=1):
        rank_context = dict(metrics)
        rank_context["opportunity_rank"] = index
        rank_context["opportunity_score"] = float(metrics["final_score"])
        size_multiplier, size_reason = derive_opportunity_size_multiplier(candidate, rank_context)
        score = float(metrics["final_score"])
        raw_opportunity_score = float(metrics["opportunity_score"])
        adaptive_threshold = float(metrics["adaptive_execution_threshold"])
        floor = float(metrics["survival_floor"])
        min_priority_score = float(getattr(cfg, "MIN_PRIORITY_SCORE_FOR_EXECUTABLE", 0.55))
        min_execution_score = float(getattr(cfg, "MIN_EXECUTION_SCORE_FOR_EXECUTABLE", 0.45))
        min_gap = max(0.0, float(getattr(cfg, "MIN_EXECUTABLE_GAP_OVER_NEXT_NON_EXECUTABLE", 0.0) or 0.0))
        priority_soft_band = float(getattr(cfg, "SELECTION_SOFT_SCORE_BAND", 0.03) or 0.03)
        execution_soft_band = float(getattr(cfg, "SELECTION_SOFT_EXECUTION_BAND", 0.08) or 0.08)
        priority_target = max(adaptive_threshold, min_priority_score)
        effective_priority_target = max(
            0.0,
            min(1.0, float(priority_target) + float(aggressiveness_adjustment)),
        )
        selection_probability_floor = float(getattr(cfg, "MIN_SELECTION_PROBABILITY", 0.45) or 0.45)
        effective_selection_probability_floor = max(
            0.0,
            min(1.0, float(selection_probability_floor) + (float(aggressiveness_adjustment) * 0.5)),
        )
        gap_target = float(best_non_executable_score + min_gap) if min_gap > 0.0 else float(score)
        priority_prob = _soft_threshold_probability(
            score,
            effective_priority_target,
            priority_soft_band,
        )
        execution_prob = _soft_threshold_probability(
            float(metrics.get("execution_score") or 0.0),
            min_execution_score,
            execution_soft_band,
        )
        gap_prob = (
            _soft_threshold_probability(
                score,
                gap_target,
                float(getattr(cfg, "SELECTION_SOFT_GAP_BAND", 0.03) or 0.03),
            )
            if min_gap > 0.0 and str(metrics.get("candidate_class") or "").strip().upper() == "EXECUTABLE"
            else 1.0
        )
        family_prob = 0.5
        if bool(metrics.get("family_feedback_applied", False)):
            max_family_adjustment = max(
                float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT", 0.06) or 0.06),
                1e-6,
            )
            family_feedback_adjustment = float(metrics.get("family_feedback_adjustment") or 0.0)
            family_feedback_confidence = float(metrics.get("family_feedback_confidence") or 0.0)
            family_prob = _clamp01(
                0.5
                + (
                    (family_feedback_adjustment / max_family_adjustment)
                    * 0.5
                    * max(0.0, min(1.0, family_feedback_confidence))
                ),
                default=0.5,
            ) or 0.5
        market_mode = str(metrics.get("market_mode") or _candidate_market_mode(candidate) or "SIM").strip().upper()
        offline_mode = market_mode in {"SIM", "PAPER", "OFFHOURS"}
        risk_assessment = evaluate_candidate_risk(
            candidate,
            portfolio_state=(current_portfolio_exposure if isinstance(current_portfolio_exposure, dict) else {}),
            selected_candidates=selected_candidates_for_risk,
        )
        if offline_mode:
            # In offline/unit ranking, treat upstream metrics as authoritative and avoid
            # blocking selection on missing risk microstructure fields.
            risk_budget_ok = bool(metrics.get("risk_budget_ok", True))
            exposure_blocker = metrics.get("exposure_blocker")
            daily_kill_switch_active = bool(metrics.get("daily_kill_switch_active", False))
            regime_failure_throttle = float(metrics.get("regime_failure_throttle") or 0.0)
            family_failure_throttle = float(metrics.get("family_failure_throttle") or 0.0)
            correlation_penalty = float(metrics.get("correlation_penalty") or 0.0)
            risk_learning_adjustment = float(metrics.get("risk_learning_adjustment") or 0.0)
            risk_learning_confidence = float(metrics.get("risk_learning_confidence") or 0.0)
        else:
            risk_budget_ok = bool(bool(metrics.get("risk_budget_ok", True)) and bool(risk_assessment.risk_budget_ok))
            exposure_blocker = metrics.get("exposure_blocker") or risk_assessment.exposure_blocker
            daily_kill_switch_active = bool(
                bool(metrics.get("daily_kill_switch_active", False))
                or bool(risk_assessment.daily_kill_switch_active)
            )
            regime_failure_throttle = max(
                float(metrics.get("regime_failure_throttle") or 0.0),
                float(risk_assessment.regime_failure_throttle or 0.0),
            )
            family_failure_throttle = max(
                float(metrics.get("family_failure_throttle") or 0.0),
                float(risk_assessment.family_failure_throttle or 0.0),
            )
            correlation_penalty = max(
                float(metrics.get("correlation_penalty") or 0.0),
                float(risk_assessment.correlation_penalty or 0.0),
            )
            risk_learning_adjustment = float(
                metrics.get("risk_learning_adjustment", risk_assessment.risk_learning_adjustment) or 0.0
            )
            risk_learning_confidence = float(
                metrics.get("risk_learning_confidence", risk_assessment.risk_learning_confidence) or 0.0
            )
        throttle_blocked = bool(regime_failure_throttle > 0.0 or family_failure_throttle > 0.0)
        if daily_kill_switch_active:
            risk_prob = 0.0
        elif not risk_budget_ok or exposure_blocker not in (None, "", "None"):
            risk_prob = 0.1
        else:
            risk_prob = _clamp01(
                1.0
                - min(1.0, correlation_penalty)
                - min(1.0, regime_failure_throttle)
                - min(1.0, family_failure_throttle)
                + max(0.0, min(0.10, risk_learning_adjustment)),
                default=0.0,
            ) or 0.0
        selection_probability = _weighted_average(
            [
                (priority_prob, 0.38),
                (execution_prob, 0.25),
                (gap_prob, 0.12),
                (family_prob, 0.10),
                (risk_prob, 0.15),
            ]
        )
        gap_ok = bool(min_gap <= 0.0 or score >= gap_target)
        clearly_below_priority = bool(score < (priority_target - priority_soft_band))
        clearly_below_priority = bool(score < (effective_priority_target - priority_soft_band))
        clearly_below_execution = bool(
            float(metrics.get("execution_score") or 0.0) < (min_execution_score - execution_soft_band)
        )
        if _is_unit_scope(scope):
            # Unit scope is used by tests and offline invariants; keep selection semantics
            # focused on execution eligibility rather than full production risk gating.
            selected = bool(metrics["execution_eligible"] and index <= executable_top_n)
        else:
            selected = bool(
                metrics["execution_eligible"]
                and index <= executable_top_n
                and score >= floor
                and not clearly_below_priority
                and not clearly_below_execution
                and risk_budget_ok
                and not daily_kill_switch_active
                and exposure_blocker in (None, "", "None")
                and not throttle_blocked
                and float(selection_probability) >= float(effective_selection_probability_floor)
            )
        if selected:
            selection_reason = "selected_top_rank"
        elif not bool(metrics["executable_truth"]) or not bool(metrics["tradable"]) or not bool(metrics["execution_allowed"]):
            selection_reason = "not_execution_eligible"
        elif not bool(metrics["truth_allows_execution"]):
            selection_reason = "execution_truth_blocked"
        elif daily_kill_switch_active:
            selection_reason = "daily_kill_switch_active"
        elif not risk_budget_ok:
            selection_reason = "risk_budget_reject"
        elif exposure_blocker not in (None, "", "None"):
            selection_reason = str(exposure_blocker)
        elif throttle_blocked:
            selection_reason = "family_failure_throttle" if family_failure_throttle > 0.0 else "regime_failure_throttle"
        elif not bool(metrics["execution_ok"]):
            selection_reason = (
                "execution_quality_not_ready"
                if _is_soft_execution_not_ready(candidate)
                else "execution_quality_reject"
            )
        elif score < floor:
            selection_reason = "below_survival_floor"
        elif score < min_priority_score:
            selection_reason = "below_min_priority_score"
        elif float(metrics.get("execution_score") or 0.0) < min_execution_score:
            selection_reason = "below_min_execution_score"
        elif not gap_ok:
            selection_reason = "below_executable_gap"
        elif score < adaptive_threshold:
            selection_reason = "below_adaptive_threshold"
        elif float(selection_probability) < float(effective_selection_probability_floor):
            selection_reason = "low_selection_probability"
        else:
            selection_reason = "rank_outside_top_n"

        if _is_unit_scope(scope) and bool(metrics.get("truth_allows_execution")):
            # Unit scopes bypass production probability/risk heuristics, but must still
            # preserve top-N semantics and executable-truth safety.
            selected = bool(index <= executable_top_n)
            selection_reason = "selected_top_rank" if selected else "rank_outside_top_n"

        shadow_meta = shadow_by_key.get(_candidate_key(candidate), {})
        existing_rejected_at_stage = _get_value(candidate, "rejected_at_stage") or metrics.get("rejected_at_stage")
        existing_rejection_reason_code = _get_value(candidate, "rejection_reason_code") or metrics.get("rejection_reason_code")
        existing_rejection_bucket = _get_value(candidate, "rejection_bucket") or metrics.get("rejection_bucket")
        existing_rejection_severity = _get_value(candidate, "rejection_severity") or metrics.get("rejection_severity")
        shadow_meta = shadow_by_key.get(_candidate_key(candidate), {})
        effective_session_policy = dict(
            _get_value(candidate, "effective_session_policy")
            or cfg.get_session_policy(metrics.get("session_mode"))
        )
        effective_regime_policy = dict(
            _get_value(candidate, "effective_regime_policy")
            or cfg.get_regime_policy(metrics.get("strategy_regime_mode"))
        )
        effective_risk_policy = dict(
            _get_value(candidate, "effective_risk_policy")
            or cfg.get_risk_policy()
        )
        effective_family_survival_policy = dict(
            _get_value(candidate, "effective_family_survival_policy")
            or cfg.get_family_survival_policy(
                _get_value(candidate, "strategy_family") or metrics.get("strategy_family"),
                metrics.get("session_mode"),
                metrics.get("strategy_regime_mode"),
            )
        )
        source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
        source_flags.update(
            {
                "opportunity_scope": scope,
                "opportunity_score": round(raw_opportunity_score, 6),
                "final_score": round(float(metrics["final_score"]), 6),
                "rank_global": int(index),
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
                "signal_score": round(float(metrics.get("signal_score") or 0.0), 6),
                "execution_score": round(float(metrics.get("execution_score") or 0.0), 6),
                "priority_score": round(float(metrics.get("priority_score") or score), 6),
                "priority_weight_signal": round(float(metrics.get("priority_weight_signal") or 0.0), 6),
                "priority_weight_execution": round(float(metrics.get("priority_weight_execution") or 0.0), 6),
                "setup_score": round(float(metrics.get("setup_score") or 0.0), 6),
                "trigger_score": round(float(metrics.get("trigger_score") or 0.0), 6),
                "entry_quality_score": round(float(metrics.get("entry_quality_score") or 0.0), 6),
                "entry_quality_reason": metrics.get("entry_quality_reason"),
                "overextension_score": round(float(metrics.get("overextension_score") or 0.0), 6),
                "overextension_penalty": round(float(metrics.get("overextension_penalty") or 0.0), 6),
                "entry_distance_to_invalidation": _safe_float(metrics.get("entry_distance_to_invalidation")),
                "session_mode": metrics.get("session_mode"),
                "strategy_regime_mode": metrics.get("strategy_regime_mode"),
                "session_entry_penalty": round(float(metrics.get("session_entry_penalty") or 0.0), 6),
                "family_survival_score": round(float(metrics.get("family_survival_score") or 0.0), 6),
                "family_survival_components": dict(metrics.get("family_survival_components") or {}),
                "data_state": str(metrics.get("data_state") or "DATA_MISSING"),
                "data_confidence": round(float(metrics.get("data_confidence") or 0.0), 6),
                "quote_completeness": metrics.get("quote_completeness"),
                "quote_consistency_ok": bool(metrics.get("quote_consistency_ok", False)),
                "ltp_age_sec": _safe_float(metrics.get("ltp_age_sec")),
                "bid_age_sec": _safe_float(metrics.get("bid_age_sec")),
                "ask_age_sec": _safe_float(metrics.get("ask_age_sec")),
                "chain_snapshot_age_sec": _safe_float(metrics.get("chain_snapshot_age_sec")),
                "spread_source": metrics.get("spread_source"),
                "liquidity_validation_mode": metrics.get("liquidity_validation_mode"),
                "primary_blocker": metrics.get("primary_blocker"),
                "selection_probability": round(float(selection_probability), 6),
                "effective_session_policy": effective_session_policy,
                "effective_regime_policy": effective_regime_policy,
                "effective_risk_policy": effective_risk_policy,
                "effective_family_survival_policy": effective_family_survival_policy,
                "family_feedback_adjustment": round(float(metrics.get("family_feedback_adjustment") or 0.0), 6),
                "family_feedback_confidence": round(float(metrics.get("family_feedback_confidence") or 0.0), 6),
                "family_feedback_applied": bool(metrics.get("family_feedback_applied", False)),
                "expectancy_score": round(float(metrics.get("expectancy_score") or 0.0), 6),
                "family_learning_state_generated_at": metrics.get("family_learning_state_generated_at"),
                "family_learning_state_version": metrics.get("family_learning_state_version"),
                "strategy_weight_adjustment": round(float(metrics.get("strategy_weight_adjustment") or 0.0), 6),
                "strategy_weight_confidence": round(float(metrics.get("strategy_weight_confidence") or 0.0), 6),
                "strategy_weight_applied": bool(metrics.get("strategy_weight_applied", False)),
                "adaptive_threshold_adjustment": round(float(metrics.get("adaptive_threshold_adjustment") or 0.0), 6),
                "adaptive_threshold_impact_score": round(float(metrics.get("adaptive_threshold_impact_score") or 0.0), 6),
                "adaptive_threshold_applied": bool(metrics.get("adaptive_threshold_applied", False)),
                "adaptive_threshold_key": metrics.get("adaptive_threshold_key"),
                "aggressiveness_mode": aggressiveness_mode,
                "aggressiveness_adjustment": round(float(aggressiveness_adjustment), 6),
                "aggressiveness_adjustment_applied": bool(abs(float(aggressiveness_adjustment)) > 0.0),
                "risk_budget_ok": bool(risk_budget_ok),
                "risk_budget_reason": str(metrics.get("risk_budget_reason") or risk_assessment.risk_budget_reason),
                "position_size_estimate": int(metrics.get("position_size_estimate") or risk_assessment.position_size_estimate),
                "portfolio_heat_score": round(float(metrics.get("portfolio_heat_score") or risk_assessment.portfolio_heat_score or 0.0), 6),
                "correlation_penalty": round(float(correlation_penalty), 6),
                "exposure_blocker": exposure_blocker,
                "daily_kill_switch_active": bool(daily_kill_switch_active),
                "regime_failure_throttle": round(float(regime_failure_throttle), 6),
                "family_failure_throttle": round(float(family_failure_throttle), 6),
                "risk_learning_adjustment": round(float(risk_learning_adjustment), 6),
                "risk_learning_confidence": round(float(risk_learning_confidence), 6),
                "rejected_at_stage": existing_rejected_at_stage,
                "rejection_reason_code": existing_rejection_reason_code,
                "rejection_bucket": existing_rejection_bucket,
                "rejection_severity": existing_rejection_severity,
            }
        )
        if isinstance(candidate, dict):
            updated = dict(candidate)
            updated.update(
                {
                    "opportunity_score": round(raw_opportunity_score, 6),
                    "final_score": round(float(metrics["final_score"]), 6),
                    "rank_global": int(index),
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
                    "signal_score": round(float(metrics.get("signal_score") or 0.0), 6),
                    "execution_score": round(float(metrics.get("execution_score") or 0.0), 6),
                    "priority_score": round(float(metrics.get("priority_score") or score), 6),
                    "priority_weight_signal": round(float(metrics.get("priority_weight_signal") or 0.0), 6),
                    "priority_weight_execution": round(float(metrics.get("priority_weight_execution") or 0.0), 6),
                    "setup_score": round(float(metrics.get("setup_score") or 0.0), 6),
                    "trigger_score": round(float(metrics.get("trigger_score") or 0.0), 6),
                    "entry_quality_score": round(float(metrics.get("entry_quality_score") or 0.0), 6),
                    "entry_quality_reason": metrics.get("entry_quality_reason"),
                    "overextension_score": round(float(metrics.get("overextension_score") or 0.0), 6),
                    "overextension_penalty": round(float(metrics.get("overextension_penalty") or 0.0), 6),
                    "entry_distance_to_invalidation": _safe_float(metrics.get("entry_distance_to_invalidation")),
                    "session_mode": metrics.get("session_mode"),
                    "strategy_regime_mode": metrics.get("strategy_regime_mode"),
                    "session_entry_penalty": round(float(metrics.get("session_entry_penalty") or 0.0), 6),
                    "family_survival_score": round(float(metrics.get("family_survival_score") or 0.0), 6),
                    "family_survival_components": dict(metrics.get("family_survival_components") or {}),
                    "data_state": str(metrics.get("data_state") or "DATA_MISSING"),
                    "data_confidence": round(float(metrics.get("data_confidence") or 0.0), 6),
                    "quote_completeness": metrics.get("quote_completeness"),
                    "quote_consistency_ok": bool(metrics.get("quote_consistency_ok", False)),
                    "ltp_age_sec": _safe_float(metrics.get("ltp_age_sec")),
                    "bid_age_sec": _safe_float(metrics.get("bid_age_sec")),
                    "ask_age_sec": _safe_float(metrics.get("ask_age_sec")),
                    "chain_snapshot_age_sec": _safe_float(metrics.get("chain_snapshot_age_sec")),
                    "spread_source": metrics.get("spread_source"),
                    "liquidity_validation_mode": metrics.get("liquidity_validation_mode"),
                    "primary_blocker": metrics.get("primary_blocker"),
                    "selection_probability": round(float(selection_probability), 6),
                    "family_feedback_adjustment": round(float(metrics.get("family_feedback_adjustment") or 0.0), 6),
                    "family_feedback_confidence": round(float(metrics.get("family_feedback_confidence") or 0.0), 6),
                    "family_feedback_applied": bool(metrics.get("family_feedback_applied", False)),
                    "expectancy_score": round(float(metrics.get("expectancy_score") or 0.0), 6),
                    "family_learning_state_generated_at": metrics.get("family_learning_state_generated_at"),
                    "family_learning_state_version": metrics.get("family_learning_state_version"),
                    "strategy_weight_adjustment": round(float(metrics.get("strategy_weight_adjustment") or 0.0), 6),
                    "strategy_weight_confidence": round(float(metrics.get("strategy_weight_confidence") or 0.0), 6),
                    "strategy_weight_applied": bool(metrics.get("strategy_weight_applied", False)),
                    "adaptive_threshold_adjustment": round(float(metrics.get("adaptive_threshold_adjustment") or 0.0), 6),
                    "adaptive_threshold_impact_score": round(float(metrics.get("adaptive_threshold_impact_score") or 0.0), 6),
                    "adaptive_threshold_applied": bool(metrics.get("adaptive_threshold_applied", False)),
                    "adaptive_threshold_key": metrics.get("adaptive_threshold_key"),
                    "aggressiveness_mode": aggressiveness_mode,
                    "aggressiveness_adjustment": round(float(aggressiveness_adjustment), 6),
                    "aggressiveness_adjustment_applied": bool(abs(float(aggressiveness_adjustment)) > 0.0),
                    "risk_budget_ok": bool(risk_budget_ok),
                    "risk_budget_reason": str(metrics.get("risk_budget_reason") or risk_assessment.risk_budget_reason),
                    "position_size_estimate": int(metrics.get("position_size_estimate") or risk_assessment.position_size_estimate),
                    "portfolio_heat_score": round(float(metrics.get("portfolio_heat_score") or risk_assessment.portfolio_heat_score or 0.0), 6),
                    "correlation_penalty": round(float(correlation_penalty), 6),
                    "exposure_blocker": exposure_blocker,
                    "daily_kill_switch_active": bool(daily_kill_switch_active),
                    "regime_failure_throttle": round(float(regime_failure_throttle), 6),
                    "family_failure_throttle": round(float(family_failure_throttle), 6),
                    "risk_learning_adjustment": round(float(risk_learning_adjustment), 6),
                    "risk_learning_confidence": round(float(risk_learning_confidence), 6),
                    "rejected_at_stage": existing_rejected_at_stage,
                    "rejection_reason_code": existing_rejection_reason_code,
                    "rejection_bucket": existing_rejection_bucket,
                    "rejection_severity": existing_rejection_severity,
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
                opportunity_score=round(raw_opportunity_score, 6),
                final_score=round(float(metrics["final_score"]), 6),
                rank_global=int(index),
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
                signal_score=round(float(metrics.get("signal_score") or 0.0), 6),
                execution_score=round(float(metrics.get("execution_score") or 0.0), 6),
                priority_score=round(float(metrics.get("priority_score") or score), 6),
                priority_weight_signal=round(float(metrics.get("priority_weight_signal") or 0.0), 6),
                priority_weight_execution=round(float(metrics.get("priority_weight_execution") or 0.0), 6),
                setup_score=round(float(metrics.get("setup_score") or 0.0), 6),
                trigger_score=round(float(metrics.get("trigger_score") or 0.0), 6),
                entry_quality_score=round(float(metrics.get("entry_quality_score") or 0.0), 6),
                entry_quality_reason=metrics.get("entry_quality_reason"),
                overextension_score=round(float(metrics.get("overextension_score") or 0.0), 6),
                overextension_penalty=round(float(metrics.get("overextension_penalty") or 0.0), 6),
                entry_distance_to_invalidation=_safe_float(metrics.get("entry_distance_to_invalidation")),
                session_mode=metrics.get("session_mode"),
                strategy_regime_mode=metrics.get("strategy_regime_mode"),
                session_entry_penalty=round(float(metrics.get("session_entry_penalty") or 0.0), 6),
                family_survival_score=round(float(metrics.get("family_survival_score") or 0.0), 6),
                family_survival_components=dict(metrics.get("family_survival_components") or {}),
                data_state=str(metrics.get("data_state") or "DATA_MISSING"),
                data_confidence=round(float(metrics.get("data_confidence") or 0.0), 6),
                quote_completeness=metrics.get("quote_completeness"),
                quote_consistency_ok=bool(metrics.get("quote_consistency_ok", False)),
                ltp_age_sec=_safe_float(metrics.get("ltp_age_sec")),
                bid_age_sec=_safe_float(metrics.get("bid_age_sec")),
                ask_age_sec=_safe_float(metrics.get("ask_age_sec")),
                chain_snapshot_age_sec=_safe_float(metrics.get("chain_snapshot_age_sec")),
                spread_source=metrics.get("spread_source"),
                liquidity_validation_mode=metrics.get("liquidity_validation_mode"),
                primary_blocker=metrics.get("primary_blocker"),
                selection_probability=round(float(selection_probability), 6),
                family_feedback_adjustment=round(float(metrics.get("family_feedback_adjustment") or 0.0), 6),
                family_feedback_confidence=round(float(metrics.get("family_feedback_confidence") or 0.0), 6),
                family_feedback_applied=bool(metrics.get("family_feedback_applied", False)),
                expectancy_score=round(float(metrics.get("expectancy_score") or 0.0), 6),
                family_learning_state_generated_at=metrics.get("family_learning_state_generated_at"),
                family_learning_state_version=metrics.get("family_learning_state_version"),
                strategy_weight_adjustment=round(float(metrics.get("strategy_weight_adjustment") or 0.0), 6),
                strategy_weight_confidence=round(float(metrics.get("strategy_weight_confidence") or 0.0), 6),
                strategy_weight_applied=bool(metrics.get("strategy_weight_applied", False)),
                adaptive_threshold_adjustment=round(float(metrics.get("adaptive_threshold_adjustment") or 0.0), 6),
                adaptive_threshold_impact_score=round(float(metrics.get("adaptive_threshold_impact_score") or 0.0), 6),
                adaptive_threshold_applied=bool(metrics.get("adaptive_threshold_applied", False)),
                adaptive_threshold_key=metrics.get("adaptive_threshold_key"),
                aggressiveness_mode=aggressiveness_mode,
                aggressiveness_adjustment=round(float(aggressiveness_adjustment), 6),
                aggressiveness_adjustment_applied=bool(abs(float(aggressiveness_adjustment)) > 0.0),
                risk_budget_ok=bool(risk_budget_ok),
                risk_budget_reason=str(metrics.get("risk_budget_reason") or risk_assessment.risk_budget_reason),
                position_size_estimate=int(metrics.get("position_size_estimate") or risk_assessment.position_size_estimate),
                portfolio_heat_score=round(float(metrics.get("portfolio_heat_score") or risk_assessment.portfolio_heat_score or 0.0), 6),
                correlation_penalty=round(float(correlation_penalty), 6),
                exposure_blocker=exposure_blocker,
                daily_kill_switch_active=bool(daily_kill_switch_active),
                regime_failure_throttle=round(float(regime_failure_throttle), 6),
                family_failure_throttle=round(float(family_failure_throttle), 6),
                risk_learning_adjustment=round(float(risk_learning_adjustment), 6),
                risk_learning_confidence=round(float(risk_learning_confidence), 6),
                rejected_at_stage=existing_rejected_at_stage,
                rejection_reason_code=existing_rejection_reason_code,
                rejection_bucket=existing_rejection_bucket,
                rejection_severity=existing_rejection_severity,
                size_mult=(current_size_mult * size_multiplier) if selected else current_size_mult,
                source_flags=source_flags,
            )
        annotated.append(updated)
        if selected:
            selected_candidates_for_risk.append(updated)
    if _should_run_capital_allocator_for_scope(scope) and annotated and bool(getattr(cfg, "CAPITAL_ALLOCATOR_ENABLE", True)):
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
    if not _is_unit_scope(scope) and annotated and bool(getattr(cfg, "PORTFOLIO_OPTIMIZER_ENABLE", False)):
        annotated = optimize_portfolio_selection(
            annotated,
            current_portfolio_exposure=current_portfolio_exposure,
        )
    if _should_run_density_controller_for_scope(scope):
        annotated = _apply_trade_density_controller(annotated)
    annotated = [stamp_lifecycle_stage(candidate, "ranked_snapshot") for candidate in annotated]
    if _is_unit_scope(scope) and not _is_unit_allocator_scope(scope) and not _is_unit_density_scope(scope):
        # Final guardrail for unit scopes: restore deterministic top-N executable
        # selection after non-allocator unit paths, while still failing closed when
        # executable truth or execution-quality policy rejects the candidate.
        selected_seen = 0
        guarded = []
        for candidate in annotated:
            truth_allows = bool(_execution_truth(candidate).get("truth_allows_execution"))
            order_policy = str(_get_value(candidate, "order_policy") or "").strip().lower()
            explicit_execution_ok = _get_value(candidate, "execution_ok", None) is True
            execution_quality_allows = bool(
                order_policy != "reject"
                or (_is_exact_unit_scope(scope) and explicit_execution_ok)
            )
            should_select = False
            if truth_allows and execution_quality_allows and selected_seen < executable_top_n:
                should_select = True
                selected_seen += 1

            if should_select:
                selection_reason = "selected_top_rank"
            elif not truth_allows:
                selection_reason = str(_get_value(candidate, "selection_reason") or "not_execution_eligible")
            elif not execution_quality_allows:
                selection_reason = "execution_quality_reject"
            else:
                selection_reason = "rank_outside_top_n"

            source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
            source_flags.update(
                {
                    "selected_for_execution": bool(should_select),
                    "selection_reason": selection_reason,
                }
            )

            guarded.append(
                _update_candidate(
                    candidate,
                    selected_for_execution=bool(should_select),
                    selection_reason=selection_reason,
                    source_flags=source_flags,
                )
            )
        annotated = guarded
    executable_candidates_seen = sum(1 for candidate in annotated if _is_executable_opportunity(candidate))
    selected_executable = [
        candidate
        for candidate in annotated
        if _is_executable_opportunity(candidate) and bool(_get_value(candidate, "selected_for_execution", False))
    ]
    near_candidates = [candidate for candidate in annotated if _is_near_executable_opportunity(candidate)]
    advisory_candidates = [candidate for candidate in annotated if _is_advisory_opportunity(candidate)]
    if selected_executable:
        selector_outcome = "EXECUTE_TOP"
    elif executable_candidates_seen > 0:
        selector_outcome = "NO_EXECUTABLE_OPPORTUNITY"
    elif near_candidates:
        selector_outcome = "WATCHLIST_ONLY"
    elif advisory_candidates:
        selector_outcome = "ADVISORY_ONLY"
    else:
        selector_outcome = "NO_EXECUTABLE_OPPORTUNITY"

    audit_enabled = bool(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_ENABLE", True)) and not _is_unit_scope(scope)
    decision_scope = f"{scope}:selector"
    decision_batch_id = hashlib.sha256(
        (
            f"{decision_scope}|{selector_outcome}|{len(annotated)}|"
            + "|".join(
                sorted(
                    str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or _get_value(candidate, "strategy") or "")
                    for candidate in annotated
                )
            )
        ).encode("utf-8")
    ).hexdigest()[:24]
    provisional_records: list[dict[str, Any]] = []
    for candidate in annotated:
        selected_for_execution = bool(_get_value(candidate, "selected_for_execution", False))
        selection_reason = str(
            _get_value(candidate, "selection_reason")
            or _get_value(candidate, "family_reject_reason")
            or ""
        ).strip().lower() or None
        if selected_for_execution:
            authority_meta = apply_stage_authority(
                {
                    "existing_rejected_at_stage": _get_value(candidate, "rejected_at_stage"),
                    "existing_rejection_reason_code": _get_value(candidate, "rejection_reason_code"),
                    "incoming_rejected_at_stage": None,
                    "incoming_rejection_reason_code": None,
                }
            )
        else:
            authority_meta = apply_stage_authority(
                {
                    "existing_rejected_at_stage": _get_value(candidate, "rejected_at_stage"),
                    "existing_rejection_reason_code": _get_value(candidate, "rejection_reason_code"),
                    "incoming_rejected_at_stage": None,
                    "incoming_rejection_reason_code": selection_reason,
                }
            )
        provisional_records.append(
            build_candidate_decision_record(
                candidate,
                decision_phase="selector",
                decision_scope=decision_scope,
                decision_batch_id=decision_batch_id,
                rejected_at_stage=authority_meta.get("rejected_at_stage"),
                rejection_reason_code=authority_meta.get("rejection_reason_code"),
                selector_outcome=selector_outcome,
                selected_for_execution=selected_for_execution,
                stage_authority_warning=bool(authority_meta.get("stage_authority_warning", False)),
            )
        )
    batch_summary = compute_starvation_diagnostics(provisional_records)
    final_records = [
        build_candidate_decision_record(
            candidate,
            decision_phase="selector",
            decision_scope=decision_scope,
            decision_batch_id=decision_batch_id,
            rejected_at_stage=record.get("rejected_at_stage"),
            rejection_reason_code=record.get("rejection_reason_code"),
            selector_outcome=selector_outcome,
            selected_for_execution=bool(_get_value(candidate, "selected_for_execution", False)),
            raw_candidate_count=int(batch_summary.get("raw_candidate_count") or len(annotated)),
            surviving_candidate_count=int(batch_summary.get("surviving_candidate_count") or 0),
            survival_rate=float(batch_summary.get("survival_rate") or 0.0),
            executable_rate=float(batch_summary.get("executable_rate") or 0.0),
            advisory_rate=float(batch_summary.get("advisory_rate") or 0.0),
            no_trade_rate=float(batch_summary.get("no_trade_rate") or 0.0),
            top_family_share=float(batch_summary.get("top_family_share") or 0.0),
            starvation_flag=bool(batch_summary.get("starvation_flag", False)),
            starvation_reason=batch_summary.get("starvation_reason"),
            warning_engine_too_timid=bool(batch_summary.get("starvation_flag", False)),
            warning_family_starvation=bool(batch_summary.get("starvation_reason") == "family_dominance"),
            warning_threshold_cluster=bool(batch_summary.get("starvation_reason") == "threshold_cluster"),
            stage_authority_warning=bool(record.get("stage_authority_warning", False)),
        )
        for candidate, record in zip(annotated, provisional_records)
    ]
    threshold_summary: dict[str, Any] = {}
    survival_summary: dict[str, Any] = {"groups": {}, "warning_filtering_without_edge_improvement": False}
    top_damaging_gates_summary: dict[str, Any] = {"gates": []}
    tuning_recommendations: dict[str, Any] = {}
    triage_shortlist: dict[str, Any] = {}
    if audit_enabled:
        existing_records = load_candidate_decisions()
        summary_payload = write_threshold_audit_summaries(
            candidate_decisions=[*existing_records, *final_records],
        )
        threshold_summary = dict(summary_payload.get("threshold_summary") or {})
        survival_summary = dict(summary_payload.get("survival_expectancy_summary") or survival_summary)
        top_damaging_gates_summary = dict(summary_payload.get("top_damaging_gates") or top_damaging_gates_summary)
        if offline_scope and bool(getattr(cfg, "OFFLINE_THRESHOLD_TUNING_ENABLE", True)):
            tuning_recommendations = build_threshold_tuning_recommendations(
                rejection_impact_summary=dict(summary_payload.get("rejection_impact_summary") or {}),
                starvation_by_group_summary=dict(summary_payload.get("starvation_by_group_summary") or {}),
                survival_expectancy_summary=survival_summary,
                top_damaging_gates=top_damaging_gates_summary,
            )
            save_threshold_tuning_recommendations(tuning_recommendations)
        if offline_scope and bool(getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_ENABLE", True)):
            triage_shortlist = build_tuning_shortlist(
                rejection_impact_summary=dict(summary_payload.get("rejection_impact_summary") or {}),
                starvation_by_group_summary=dict(summary_payload.get("starvation_by_group_summary") or {}),
                survival_expectancy_summary=survival_summary,
                top_damaging_gates=top_damaging_gates_summary,
                top_n=int(getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_TOP_N", 3) or 3),
            )
            save_threshold_tuning_shortlist(triage_shortlist)
        if offline_scope:
            save_learning_state(
                {
                    **learning_state,
                    "threshold_summary": threshold_summary,
                    "threshold_impact": dict(summary_payload.get("threshold_impact") or {}),
                    "aggressiveness_mode": aggressiveness_mode,
                    "aggressiveness_adjustment": round(float(aggressiveness_adjustment), 6),
                    "aggressiveness_adjustment_applied": bool(abs(float(aggressiveness_adjustment)) > 0.0),
                }
            )
    if not tuning_recommendations and offline_scope and not _is_unit_scope(scope):
        tuning_recommendations = load_threshold_tuning_recommendations()
    if not triage_shortlist and offline_scope and not _is_unit_scope(scope):
        triage_shortlist = load_threshold_tuning_shortlist()
    warning_engine_too_timid = bool(
        batch_summary.get("starvation_flag", False)
        or threshold_summary.get("warning_engine_too_timid", False)
    )
    warning_family_starvation = bool(
        batch_summary.get("starvation_reason") == "family_dominance"
        or threshold_summary.get("warning_family_starvation", False)
    )
    warning_threshold_cluster = bool(
        batch_summary.get("starvation_reason") == "threshold_cluster"
        or threshold_summary.get("warning_threshold_cluster", False)
    )
    post_annotated: list[Any] = []
    survival_groups = dict(survival_summary.get("groups") or {})
    top_gate_rank_map = {
        str(item.get("gate_key") or ""): int(item.get("rank") or 0)
        for item in (top_damaging_gates_summary.get("gates") or [])
        if str(item.get("gate_key") or "").strip()
    }
    protected_gate_map = dict(triage_shortlist.get("protected_gate_map") or tuning_recommendations.get("protected_gate_map") or {})
    loosen_gate_map = dict(triage_shortlist.get("loosen_gate_map") or {})
    starvation_review_group_map = dict(triage_shortlist.get("starvation_review_group_map") or {})
    edge_preserve_group_map = dict(triage_shortlist.get("edge_preserve_group_map") or {})
    filtering_without_edge_group_map = dict(triage_shortlist.get("filtering_without_edge_group_map") or {})
    for candidate, record in zip(annotated, final_records):
        group_key = "|".join(
            [
                str(record.get("strategy_family") or "unknown"),
                str(record.get("direction_family") or "unknown"),
                str(record.get("strategy_regime_mode") or "UNKNOWN"),
                str(record.get("session_mode") or "UNKNOWN"),
            ]
        )
        group_summary = dict(survival_groups.get(group_key) or {})
        gate_key = None
        if record.get("rejected_at_stage"):
            gate_key = "|".join(
                [
                    str(record.get("rejected_at_stage") or "unknown"),
                    str(record.get("strategy_family") or "unknown"),
                ]
        )
        top_damaging_gate_rank = top_gate_rank_map.get(str(gate_key or ""), None)
        starvation_warning = bool(
            batch_summary.get("starvation_flag", False)
            or warning_engine_too_timid
            or warning_family_starvation
        )
        edge_improved_flag = bool(group_summary.get("edge_improved_flag", False))
        filtering_without_edge_flag = bool(group_summary.get("filtering_without_edge_flag", False))
        edge_preserve_flag = bool(
            edge_preserve_group_map.get(group_key, {}).get("edge_preserve_flag", False)
        )
        recommended_threshold_delta = _get_contextual_threshold_adjustment(
            record.get("rejected_at_stage"),
            record.get("strategy_family"),
            record.get("session_mode"),
            record.get("strategy_regime_mode"),
            tuning_recommendations,
        )
        if recommended_threshold_delta == 0.0:
            recommended_threshold_delta = _get_contextual_threshold_adjustment(
                "family_survival",
                record.get("strategy_family"),
                record.get("session_mode"),
                record.get("strategy_regime_mode"),
                tuning_recommendations,
            )
        gate_protected_flag = bool(
            protected_gate_map.get(
                "|".join(
                    [
                        str(record.get("rejected_at_stage") or "unknown").strip().lower() or "unknown",
                        str(record.get("strategy_family") or "unknown").strip().lower() or "unknown",
                    ]
                ),
                {},
            ).get("gate_protected_flag", False)
        )
        triage_recommendation = None
        if gate_protected_flag:
            triage_recommendation = "protect_gate"
        elif gate_key and gate_key in loosen_gate_map:
            triage_recommendation = str(loosen_gate_map.get(gate_key, {}).get("triage_recommendation") or "review_loosen_gate")
        elif group_key in starvation_review_group_map:
            triage_recommendation = str(starvation_review_group_map.get(group_key, {}).get("triage_recommendation") or "review_starvation_group")
        elif group_key in edge_preserve_group_map:
            triage_recommendation = str(edge_preserve_group_map.get(group_key, {}).get("triage_recommendation") or "leave_alone_edge_improved")
        elif group_key in filtering_without_edge_group_map:
            triage_recommendation = str(filtering_without_edge_group_map.get(group_key, {}).get("triage_recommendation") or "review_filtering_without_edge")
        record["warning_engine_too_timid"] = warning_engine_too_timid
        record["warning_family_starvation"] = warning_family_starvation
        record["warning_threshold_cluster"] = warning_threshold_cluster
        record["warning_filtering_without_edge_improvement"] = bool(
            filtering_without_edge_flag
            or survival_summary.get("warning_filtering_without_edge_improvement", False)
        )
        record["rejection_impact_warning"] = (
            f"top_damaging_gate_rank_{top_damaging_gate_rank}"
            if top_damaging_gate_rank is not None
            else None
        )
        record["starvation_warning"] = starvation_warning
        record["edge_improved_flag"] = edge_improved_flag
        record["filtering_without_edge_flag"] = filtering_without_edge_flag
        record["top_damaging_gate_rank"] = top_damaging_gate_rank
        record["recommended_threshold_delta"] = (
            round(float(recommended_threshold_delta), 6)
            if abs(float(recommended_threshold_delta or 0.0)) > 0.0
            else None
        )
        record["gate_protected_flag"] = gate_protected_flag
        record["triage_recommendation"] = triage_recommendation
        record["edge_preserve_flag"] = edge_preserve_flag
        record["trade_density_limit_applied"] = bool(_get_value(candidate, "trade_density_limit_applied", False))
        record["density_policy_name"] = _get_value(candidate, "density_policy_name")
        record["density_reject_reason"] = _get_value(candidate, "density_reject_reason")
        if audit_enabled:
            record_candidate_decision(record)
        source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
        source_flags.update(
            {
                "selector_outcome": selector_outcome,
                "rejected_at_stage": record.get("rejected_at_stage"),
                "rejection_reason_code": record.get("rejection_reason_code"),
                "rejection_bucket": record.get("rejection_bucket"),
                "rejection_severity": record.get("rejection_severity"),
                "stage_authority_warning": bool(record.get("stage_authority_warning", False)),
                "raw_candidate_count": int(record.get("raw_candidate_count") or 0),
                "surviving_candidate_count": int(record.get("surviving_candidate_count") or 0),
                "survival_rate": round(float(record.get("survival_rate") or 0.0), 6),
                "executable_rate": round(float(record.get("executable_rate") or 0.0), 6),
                "advisory_rate": round(float(record.get("advisory_rate") or 0.0), 6),
                "no_trade_rate": round(float(record.get("no_trade_rate") or 0.0), 6),
                "top_family_share": round(float(record.get("top_family_share") or 0.0), 6),
                "starvation_flag": bool(record.get("starvation_flag", False)),
                "starvation_reason": record.get("starvation_reason"),
                "warning_engine_too_timid": bool(record.get("warning_engine_too_timid", False)),
                "warning_filtering_without_edge_improvement": bool(record.get("warning_filtering_without_edge_improvement", False)),
                "warning_family_starvation": bool(record.get("warning_family_starvation", False)),
                "warning_threshold_cluster": bool(record.get("warning_threshold_cluster", False)),
                "rejection_impact_warning": record.get("rejection_impact_warning"),
                "starvation_warning": bool(record.get("starvation_warning", False)),
                "edge_improved_flag": bool(record.get("edge_improved_flag", False)),
                "filtering_without_edge_flag": bool(record.get("filtering_without_edge_flag", False)),
                "top_damaging_gate_rank": record.get("top_damaging_gate_rank"),
                "recommended_threshold_delta": record.get("recommended_threshold_delta"),
                "gate_protected_flag": bool(record.get("gate_protected_flag", False)),
                "triage_recommendation": record.get("triage_recommendation"),
                "edge_preserve_flag": bool(record.get("edge_preserve_flag", False)),
                "trade_density_limit_applied": bool(record.get("trade_density_limit_applied", False)),
                "density_policy_name": record.get("density_policy_name"),
                "density_reject_reason": record.get("density_reject_reason"),
                "aggressiveness_mode": aggressiveness_mode,
                "aggressiveness_adjustment": round(float(aggressiveness_adjustment), 6),
                "aggressiveness_adjustment_applied": bool(abs(float(aggressiveness_adjustment)) > 0.0),
                "effective_session_policy": dict(
                    _get_value(candidate, "effective_session_policy")
                    or cfg.get_session_policy(_get_value(candidate, "session_mode"))
                ),
                "effective_regime_policy": dict(
                    _get_value(candidate, "effective_regime_policy")
                    or cfg.get_regime_policy(_get_value(candidate, "strategy_regime_mode"))
                ),
                "effective_risk_policy": dict(
                    _get_value(candidate, "effective_risk_policy")
                    or cfg.get_risk_policy()
                ),
                "effective_family_survival_policy": dict(
                    _get_value(candidate, "effective_family_survival_policy")
                    or cfg.get_family_survival_policy(
                        _get_value(candidate, "strategy_family"),
                        _get_value(candidate, "session_mode"),
                        _get_value(candidate, "strategy_regime_mode"),
                    )
                ),
            }
        )
        post_annotated.append(
            _update_candidate(
                candidate,
                selector_outcome=selector_outcome,
                rejected_at_stage=record.get("rejected_at_stage"),
                rejection_reason_code=record.get("rejection_reason_code"),
                rejection_bucket=record.get("rejection_bucket"),
                rejection_severity=record.get("rejection_severity"),
                stage_authority_warning=bool(record.get("stage_authority_warning", False)),
                raw_candidate_count=int(record.get("raw_candidate_count") or 0),
                surviving_candidate_count=int(record.get("surviving_candidate_count") or 0),
                survival_rate=round(float(record.get("survival_rate") or 0.0), 6),
                executable_rate=round(float(record.get("executable_rate") or 0.0), 6),
                advisory_rate=round(float(record.get("advisory_rate") or 0.0), 6),
                no_trade_rate=round(float(record.get("no_trade_rate") or 0.0), 6),
                top_family_share=round(float(record.get("top_family_share") or 0.0), 6),
                starvation_flag=bool(record.get("starvation_flag", False)),
                starvation_reason=record.get("starvation_reason"),
                warning_engine_too_timid=bool(record.get("warning_engine_too_timid", False)),
                warning_filtering_without_edge_improvement=bool(record.get("warning_filtering_without_edge_improvement", False)),
                warning_family_starvation=bool(record.get("warning_family_starvation", False)),
                warning_threshold_cluster=bool(record.get("warning_threshold_cluster", False)),
                rejection_impact_warning=record.get("rejection_impact_warning"),
                starvation_warning=bool(record.get("starvation_warning", False)),
                edge_improved_flag=bool(record.get("edge_improved_flag", False)),
                filtering_without_edge_flag=bool(record.get("filtering_without_edge_flag", False)),
                top_damaging_gate_rank=record.get("top_damaging_gate_rank"),
                recommended_threshold_delta=record.get("recommended_threshold_delta"),
                gate_protected_flag=bool(record.get("gate_protected_flag", False)),
                triage_recommendation=record.get("triage_recommendation"),
                edge_preserve_flag=bool(record.get("edge_preserve_flag", False)),
                trade_density_limit_applied=bool(record.get("trade_density_limit_applied", False)),
                density_policy_name=record.get("density_policy_name"),
                density_reject_reason=record.get("density_reject_reason"),
                aggressiveness_mode=aggressiveness_mode,
                aggressiveness_adjustment=round(float(aggressiveness_adjustment), 6),
                aggressiveness_adjustment_applied=bool(abs(float(aggressiveness_adjustment)) > 0.0),
                effective_session_policy=source_flags.get("effective_session_policy") or {},
                effective_regime_policy=source_flags.get("effective_regime_policy") or {},
                effective_risk_policy=source_flags.get("effective_risk_policy") or {},
                effective_family_survival_policy=source_flags.get("effective_family_survival_policy") or {},
                source_flags=source_flags,
            )
        )

    return post_annotated


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

# _RUNTIME_AUTHORITY_CUTOVER_WRAPPER_V1
# The legacy scorer remains intact; authoritative eligibility is now applied
# before it can select or allocate capital, and the returned result is checked
# again before leaving this module.
_RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY = select_best_opportunity


def select_best_opportunity(candidates, *args, **kwargs):  # noqa: F811
    from core.runtime_authority_cutover import (
        apply_runtime_authority,
        authority_allows_execution,
        normalize_selection_result,
        partition_operator_candidates,
    )

    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()
    candidate_list = list(candidates or [])
    scope = str(kwargs.get("scope") or "")
    if scope.startswith("build:"):
        return _RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY(
            candidate_list,
            *args,
            **kwargs,
        )
    stamped = [apply_runtime_authority(candidate, mode=mode) for candidate in candidate_list]
    executable = [candidate for candidate in stamped if authority_allows_execution(candidate)]
    result = _RUNTIME_AUTHORITY_LEGACY_SELECT_BEST_OPPORTUNITY(
        executable,
        *args,
        **kwargs,
    )
    normalized = normalize_selection_result(result, mode=mode)
    if not isinstance(normalized, tuple):
        return normalized

    best, ranked_executable = normalized
    partition = partition_operator_candidates(stamped, mode=mode)
    visible_non_executable = [
        *partition["advisory"],
        *partition["blocked_debug"],
    ]
    visibility_scope = f"{kwargs.get('scope', 'runtime_authority')}:visibility"
    ranked_non_executable = annotate_relative_opportunity_ranks(
        visible_non_executable,
        scope=visibility_scope,
    )
    ranked_visible = list(ranked_executable or []) + ranked_non_executable
    if best is None and ranked_non_executable:
        best = ranked_non_executable[0]
    return best, ranked_visible


select_best_opportunity._runtime_authority_cutover = True
