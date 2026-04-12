from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import logging
import time
from typing import Any

from config import config as cfg
from core.trade_scoring import compute_final_score
from core.thesis_model import annotate_thesis
from core.candidate_lifecycle import attach_timestamp, apply_staleness_penalty, is_candidate_stale
from core.multi_timeframe_alignment import downgrade_if_conflict
from core.key_level_engine import level_context_score
from core.event_awareness import event_risk_multiplier
from core.phase2_explainability import annotate_explainability
from core.score_calibration_tuning import tune_score, clamp01
from core.phase2_candidate_partition import partition_candidates, classify_no_trade_reason
from core.options_contract_intelligence import annotate_option_intelligence
from core.strike_optimizer import annotate_strike
from core.entry_timing_refinement import annotate_entry_timing
from core.market_breadth import annotate_breadth
from core.thesis_exit_engine_v2 import annotate_exit

logger = logging.getLogger("phase2_v2")


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _candidate_to_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return dict(candidate)
    if is_dataclass(candidate):
        return asdict(candidate)
    out: dict[str, Any] = {}
    for key in dir(candidate):
        if key.startswith("_"):
            continue
        try:
            value = getattr(candidate, key)
        except Exception:
            continue
        if callable(value):
            continue
        out[key] = value
    return out


def _normalize_selected(selected: Any) -> dict[str, Any] | None:
    if selected is None:
        return None
    selected_dict = _candidate_to_dict(selected)
    selected_dict.setdefault("score", _safe_float(selected_dict.get("final_score")) or 0.0)
    selected_dict.setdefault("symbol", str(selected_dict.get("symbol") or ""))
    selected_dict.setdefault("decision_ts_epoch", float(time.time()))
    if not str(selected_dict.get("symbol") or "").strip():
        return None
    return selected_dict


def _initial_score(candidate: dict[str, Any]) -> float:
    existing = _safe_float(candidate.get("final_score"))
    if existing is not None and existing > 0:
        return float(existing)
    result = compute_final_score(
        candidate,
        candidate_class=str(candidate.get("candidate_class") or "ADVISORY_ONLY"),
        market_mode=str(candidate.get("market_mode") or candidate.get("execution_mode") or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper(),
        setup_quality=_safe_float(candidate.get("setup_score")) or _safe_float(candidate.get("signal_score")) or 0.0,
        confluence_score=_safe_float(candidate.get("confidence_final")) or _safe_float(candidate.get("confidence")) or 0.0,
        regime_fit=_safe_float(candidate.get("regime_fit")) or _safe_float(candidate.get("regime_score")) or 0.5,
        liquidity_quality=_safe_float(candidate.get("liquidity_score")) or 0.5,
        freshness_quality=_safe_float(candidate.get("freshness_quality")) or (1.0 if _safe_bool(candidate.get("fresh_quote_ok"), True) else 0.0),
        execution_feasibility=_safe_float(candidate.get("execution_score")) or _safe_float(candidate.get("execution_quality_score")) or 0.0,
        data_confidence=_safe_float(candidate.get("data_confidence")),
        setup_score=_safe_float(candidate.get("setup_score")),
        trigger_score=_safe_float(candidate.get("trigger_score")),
        entry_quality_score=_safe_float(candidate.get("entry_quality_score")),
        family_survival_score=_safe_float(candidate.get("family_survival_score")),
        risk_learning_adjustment=_safe_float(candidate.get("risk_learning_adjustment")),
        risk_learning_confidence=_safe_float(candidate.get("risk_learning_confidence")),
        is_fallback=_safe_bool(candidate.get("synthetic_candidate"), False),
        stale_quote=not _safe_bool(candidate.get("fresh_quote_ok"), True),
        missing_liquidity=not _safe_bool(candidate.get("liquidity_ok"), True),
        spread_uncertain=_safe_float(candidate.get("spread_pct")) is None,
    )
    return _safe_float(result.get("final_score")) or 0.0


def _enrich_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out = annotate_thesis(out)
    out = attach_timestamp(out)
    out = annotate_option_intelligence(out)
    out = annotate_strike(out)
    out = annotate_entry_timing(out)
    out = annotate_breadth(out)
    out = annotate_exit(out)

    score = _initial_score(out)
    score = apply_staleness_penalty(score, out)
    score = downgrade_if_conflict(score, out.get("mtf_context", {}))

    price = _safe_float(out.get("current_price")) or _safe_float(out.get("opt_ltp")) or _safe_float(out.get("current_ltp")) or 0.0
    score += level_context_score(float(price), out.get("level_context", {}))
    score *= event_risk_multiplier(out.get("event_calendar", []), datetime.now())
    score *= float(out.get("option_quality_score") or 1.0)
    score *= float(out.get("strike_score") or 1.0)
    score *= float(out.get("entry_timing_score") or 1.0)
    score = tune_score(score, out)
    score = clamp01(score)

    out["final_score"] = float(score)
    out["score"] = float(score)
    out["phase2_execution_valid"] = bool(
        (not is_candidate_stale(out))
        and float(out.get("option_quality_score") or 0.0) >= 0.50
        and float(out.get("entry_timing_score") or 0.0) >= 0.50
        and float(out.get("score") or 0.0) >= 0.45
        and not _safe_bool(out.get("synthetic_candidate"), False)
        and str(out.get("quote_source") or "").strip().lower() not in {"", "unknown", "none"}
        and str(out.get("max_final_action") or "").strip().upper() != "QUEUE_ONLY"
    )
    out = annotate_explainability(out)
    return out


def build_candidates_phase2(raw_candidates: list[Any] | None = None) -> list[dict[str, Any]]:
    raw_list = list(raw_candidates or [])
    if not raw_list:
        logger.warning("PHASE2_V2: No input candidates raw_count=0")
        return []

    ranked_candidates: list[dict[str, Any]] = []
    for raw in raw_list:
        candidate = _candidate_to_dict(raw)
        if not str(candidate.get("symbol") or "").strip():
            continue
        enriched = _enrich_candidate(candidate)
        if float(enriched.get("score") or 0.0) < 0.35:
            continue
        ranked_candidates.append(enriched)

    ranked_candidates.sort(
        key=lambda row: (
            float(_safe_float(row.get("final_score")) or 0.0),
            float(_safe_float(row.get("option_quality_score")) or 0.0),
            float(_safe_float(row.get("entry_timing_score")) or 0.0),
        ),
        reverse=True,
    )
    return ranked_candidates


def _active_trade_score(active_trade: dict[str, Any] | None) -> float | None:
    if not isinstance(active_trade, dict):
        return None
    for key in ("final_score", "rank_score", "opportunity_score", "score"):
        value = _safe_float(active_trade.get(key))
        if value is not None:
            return float(value)
    return None


def _should_replace(current_score: float | None, new_score: float, *, min_abs_delta: float, min_rel_delta: float) -> bool:
    if current_score is None:
        return True
    if (new_score - current_score) < float(min_abs_delta):
        return False
    baseline = max(abs(current_score), 1e-9)
    if ((new_score - current_score) / baseline) < float(min_rel_delta):
        return False
    return True


def run_engine_phase2(
    raw_candidates: list[Any] | None,
    *,
    active_trade: Any = None,
    min_enter_score: float | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    ranked = build_candidates_phase2(raw_candidates)
    top_limit = max(1, int(top_n if top_n is not None else getattr(cfg, "PHASE2_TOP_N", 3) or 3))
    min_enter = float(min_enter_score if min_enter_score is not None else getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.60))
    active_trade_dict = _candidate_to_dict(active_trade) if active_trade is not None else None

    partitions = partition_candidates(ranked)
    trusted = [c for c in partitions.get("trusted", []) if _safe_bool(c.get("phase2_execution_valid"), False)]
    near_exec = list(partitions.get("near_executable", []))
    degraded = list(partitions.get("degraded", []))

    trusted = trusted[:top_limit]
    near_exec = near_exec[:top_limit]
    degraded = degraded[:top_limit]

    if not trusted:
        reason = classify_no_trade_reason(partitions, min_enter)
        selected = _normalize_selected(near_exec[0]) if near_exec else (_normalize_selected(degraded[0]) if degraded else None)
        state = "WATCHLIST" if selected is not None else "NO_TRADE"
        return {
            "state": state,
            "reason": reason,
            "selected": selected,
            "ranked": trusted,
            "ranked_trusted": trusted,
            "ranked_near_executable": near_exec,
            "ranked_degraded": degraded,
            "next_active_trade": None,
        }

    top = trusted[0]
    top_score = float(_safe_float(top.get("final_score")) or 0.0)
    active_score = _active_trade_score(active_trade_dict)
    min_abs_delta = float(getattr(cfg, "PHASE2_REPLACE_MIN_ABS_DELTA", 0.12) or 0.12)
    min_rel_delta = float(getattr(cfg, "PHASE2_REPLACE_MIN_REL_DELTA", 0.20) or 0.20)

    if active_trade_dict is not None:
        if top_score >= min_enter and _should_replace(active_score, top_score, min_abs_delta=min_abs_delta, min_rel_delta=min_rel_delta):
            selected = _normalize_selected(top)
            return {
                "state": "REPLACE",
                "reason": "trusted_top_ranked_upgrade",
                "selected": selected,
                "ranked": trusted,
                "ranked_trusted": trusted,
                "ranked_near_executable": near_exec,
                "ranked_degraded": degraded,
                "next_active_trade": selected,
            }
        active_selected = _normalize_selected(active_trade_dict) or active_trade_dict
        return {
            "state": "HOLD",
            "reason": "no_significant_upgrade",
            "selected": active_selected,
            "ranked": trusted,
            "ranked_trusted": trusted,
            "ranked_near_executable": near_exec,
            "ranked_degraded": degraded,
            "next_active_trade": active_selected,
        }

    if top_score >= min_enter:
        selected = _normalize_selected(top)
        return {
            "state": "ENTER",
            "reason": "trusted_top_ranked",
            "selected": selected,
            "ranked": trusted,
            "ranked_trusted": trusted,
            "ranked_near_executable": near_exec,
            "ranked_degraded": degraded,
            "next_active_trade": selected,
        }

    selected = _normalize_selected(top)
    return {
        "state": "WATCHLIST",
        "reason": "trusted_top_score_below_enter_threshold",
        "selected": selected,
        "ranked": trusted,
        "ranked_trusted": trusted,
        "ranked_near_executable": near_exec,
        "ranked_degraded": degraded,
        "next_active_trade": None,
    }
