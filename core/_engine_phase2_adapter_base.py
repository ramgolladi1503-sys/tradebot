from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import logging
import time
from typing import Any

from config import config as cfg
from core.playbook_selector import select_playbook
from core.setup_breakout_continuation import evaluate_breakout_continuation_setup
from core.setup_profile_rejection import evaluate_profile_rejection_setup
from core.quote_truth import quote_consistency_score
from core.trade_scoring import compute_final_score

logger = logging.getLogger("phase2")


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


def _cfg_csv_set(name: str, default: str) -> set[str]:
    try:
        raw = str(getattr(cfg, name, default) or default)
    except Exception:
        raw = str(default or "")
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def _mode_for_candidate(candidate: dict[str, Any] | None = None) -> str:
    if isinstance(candidate, dict):
        text = str(
            candidate.get("execution_mode")
            or candidate.get("market_mode")
            or candidate.get("mode")
            or ""
        ).strip().upper()
        if text:
            return text
    return str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper()


def _allow_relaxed_live() -> bool:
    return bool(getattr(cfg, "PHASE2_RELAX_ALLOW_LIVE", False))


def _live_mode(mode: str) -> bool:
    return str(mode or "").strip().upper() in {"LIVE", "REAL"}


def _is_fallback_driven_candidate(candidate: dict[str, Any]) -> bool:
    if not isinstance(candidate, dict):
        return False
    if _safe_bool(candidate.get("synthetic_candidate"), default=False):
        return True
    if _safe_bool(candidate.get("forced_fallback_execution"), default=False):
        return True
    quote_source = str(candidate.get("quote_source") or "").strip().lower()
    if not quote_source or quote_source == "unknown":
        return True
    if _safe_bool(candidate.get("phase2_spread_fallback_used"), default=False):
        return True
    if _safe_bool(candidate.get("phase2_liquidity_fallback_used"), default=False):
        return True
    return False


def safe_get(c: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(c.get(key, default))
    except Exception:
        return default


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


def validate_candidate(c: dict[str, Any]) -> bool:
    required_keys = ["symbol"]
    for key in required_keys:
        if key not in c or c[key] in [None, ""]:
            return False
    return True


def _candidate_hour(candidate: dict[str, Any]) -> int:
    epoch = (
        _safe_float(candidate.get("timestamp_epoch"))
        or _safe_float(candidate.get("decision_ts_epoch"))
        or _safe_float(candidate.get("ts_epoch"))
    )
    if epoch is not None and epoch > 0:
        try:
            return int(datetime.fromtimestamp(float(epoch)).hour)
        except Exception:
            pass
    return int(datetime.now().hour)


def _spread_pct(candidate: dict[str, Any]) -> float | None:
    spread_pct = _safe_float(candidate.get("spread_pct"))
    if spread_pct is not None:
        return max(0.0, spread_pct)
    bid = _safe_float(candidate.get("best_bid"))
    ask = _safe_float(candidate.get("best_ask"))
    ltp = _safe_float(candidate.get("opt_ltp")) or _safe_float(candidate.get("current_ltp"))
    if bid is None or ask is None or ltp in (None, 0.0):
        return None
    return max(0.0, float(ask - bid) / max(float(ltp), 1e-9))


def _effective_max_spread_pct(candidate: dict[str, Any]) -> float:
    base_spread = float(
        getattr(cfg, "PHASE2_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.02))
        or getattr(cfg, "MAX_SPREAD_PCT", 0.02)
    )
    high_vol_spread = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", 0.02) or 0.02)
    vol_cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
    volatility = max(
        safe_get(candidate, "volatility", 0.0),
        safe_get(candidate, "volatility_score", 0.0),
        safe_get(candidate, "vol_z", 0.0),
    )
    max_spread = high_vol_spread if volatility > vol_cutoff else base_spread
    market_start_hour = int(getattr(cfg, "PHASE2_MARKET_START_HOUR", 9) or 9)
    market_end_hour = int(getattr(cfg, "PHASE2_MARKET_END_HOUR", 15) or 15)
    offhours_mult = float(getattr(cfg, "PHASE2_SPREAD_OFFHOURS_MULT", 1.5) or 1.5)
    hour = _candidate_hour(candidate)
    if hour < market_start_hour or hour > market_end_hour:
        max_spread *= offhours_mult
    return max(float(max_spread), 1e-6)


def _liquidity_score(candidate: dict[str, Any]) -> float:
    score = _safe_float(candidate.get("liquidity_score"))
    spread_pct = _spread_pct(candidate)
    consistency_score = _safe_float(candidate.get("quote_consistency_score"))
    if consistency_score is None:
        consistency_score = quote_consistency_score(
            current_ltp=_safe_float(candidate.get("opt_ltp")) or _safe_float(candidate.get("current_ltp")),
            best_bid=_safe_float(candidate.get("best_bid")),
            best_ask=_safe_float(candidate.get("best_ask")),
        )
    if consistency_score is not None:
        consistency_score = max(0.0, min(1.0, float(consistency_score)))
        candidate["quote_consistency_score"] = float(consistency_score)
    if score is not None:
        bounded = max(0.0, min(1.0, score))
        if consistency_score is not None and bool(getattr(cfg, "PHASE2_CAP_LIQUIDITY_WITH_QUOTE_CONSISTENCY", True)):
            bounded = min(bounded, float(consistency_score))
        return bounded
    if spread_pct is not None:
        max_spread = _effective_max_spread_pct(candidate)
        spread_quality = max(0.0, 1.0 - min(float(spread_pct) / max_spread, 1.0))
        if consistency_score is not None:
            spread_quality = min(spread_quality, float(consistency_score))
        return spread_quality
    liquidity_ok = candidate.get("liquidity_ok")
    if liquidity_ok is not None:
        bounded = 1.0 if _safe_bool(liquidity_ok, default=False) else 0.0
        if consistency_score is not None and bool(getattr(cfg, "PHASE2_CAP_LIQUIDITY_WITH_QUOTE_CONSISTENCY", True)):
            bounded = min(bounded, float(consistency_score))
        return bounded
    volume = _safe_float(candidate.get("volume")) or _safe_float(candidate.get("current_volume")) or 0.0
    min_volume = max(float(getattr(cfg, "MIN_VOLUME_FILTER", 1.0) or 1.0), 1.0)
    bounded = max(0.0, min(1.0, float(volume) / min_volume))
    if consistency_score is not None and bool(getattr(cfg, "PHASE2_CAP_LIQUIDITY_WITH_QUOTE_CONSISTENCY", True)):
        bounded = min(bounded, float(consistency_score))
    return bounded


def _execution_quality_score(candidate: dict[str, Any]) -> float:
    for key in (
        "execution_quality_score",
        "execution_score",
        "fill_probability",
        "selection_probability",
    ):
        value = _safe_float(candidate.get(key))
        if value is not None:
            return max(0.0, min(1.0, value))
    execution_allowed = _safe_bool(candidate.get("execution_allowed"), default=True)
    tradable = _safe_bool(candidate.get("tradable"), default=True)
    return 1.0 if (execution_allowed and tradable) else 0.0


def _reason_codes(candidate: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("reject_reason", "reason", "execution_block_reason"):
        text = str(candidate.get(key) or "").strip()
        if text:
            out.append(text.upper())
    for key in (
        "gate_reasons",
        "blockers",
        "hard_blockers",
        "execution_blockers",
        "penalty_reasons",
        "confidence_penalty_reasons",
    ):
        for value in list(candidate.get(key) or []):
            text = str(value or "").strip()
            if text:
                out.append(text.upper())
    return out


def _execution_not_ready_reason_codes(candidate: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for key in (
        "order_policy_reason",
        "execution_block_reason",
        "quote_validation_status",
        "execution_quality_reason",
        "execution_quality_reason_code",
    ):
        text = str(candidate.get(key) or "").strip().upper()
        if text:
            codes.add(text)
    source_flags = candidate.get("source_flags")
    if isinstance(source_flags, dict):
        for key in ("order_policy_reason", "execution_quality_reason", "execution_quality_reason_code"):
            text = str(source_flags.get(key) or "").strip().upper()
            if text:
                codes.add(text)
    return codes


def _is_no_signal_candidate(candidate: dict[str, Any]) -> bool:
    return any("NO_SIGNAL" in code for code in _reason_codes(candidate))


def _is_latency_only_block(candidate: dict[str, Any]) -> bool:
    codes = _reason_codes(candidate)
    if not codes:
        return False
    has_latency = any("LATENCY_GUARD" in code or "LATENCY" in code for code in codes)
    if not has_latency:
        return False
    disallowed = {
        "FEED_STALE",
        "NO_LIVE_OPTION_FEED",
        "UNRESOLVED_CONTRACT",
        "MISSING_CONTRACT_FIELDS",
        "MISSING_OPTION_TOKEN",
        "NO_TOKEN",
    }
    return not any(code in disallowed for code in codes)


def _is_borderline_execution_candidate(candidate: dict[str, Any]) -> bool:
    candidate_status = str(candidate.get("candidate_status") or "").strip().lower()
    execution_status = str(candidate.get("execution_status") or "").strip().lower()
    candidate_origin = str(candidate.get("candidate_origin") or "").strip().lower()
    if candidate_status in {"near_executable", "queue_only", "scored"}:
        return True
    if execution_status in {"queue_only", "scored"}:
        return True
    if "softened_builder_path" in candidate_origin:
        return True
    return bool(candidate.get("soft_blockers"))


def _strict_placeholder_candidate(candidate: dict[str, Any]) -> bool:
    trade_id = str(candidate.get("trade_id") or "").strip().lower()
    candidate_origin = str(candidate.get("candidate_origin") or "").strip().lower()
    strategy_family = str(candidate.get("strategy_family") or "").strip().lower()
    source_flags = candidate.get("source_flags")
    recoverable_soft_reject = False
    if isinstance(source_flags, dict):
        recoverable_soft_reject = _safe_bool(source_flags.get("recoverable_soft_reject"), default=False)
    if trade_id.startswith("tbsoft_") or trade_id.startswith("softrej_"):
        return True
    if candidate_origin in {"softened_builder_path", "softened", "fallback_min_breadth", "fallback"}:
        return True
    if strategy_family in {"synthetic_advisory", "builder_soft_reject"}:
        return True
    return recoverable_soft_reject


def _strict_mode_drop_reason(candidate: dict[str, Any]) -> str | None:
    if not bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
        return None
    if _strict_placeholder_candidate(candidate):
        return "strict_placeholder_candidate"
    reason_codes = set(_reason_codes(candidate))
    strict_codes = _cfg_csv_set(
        "PHASE2_STRICT_DROP_REASON_CODES",
        "weak_signal,no_signal,rr_estimated_context,missing_rr_context,missing_liquidity_context,missing_spread_context,missing_timing_context,missing_live_timing_context,unknown_quote_source,execution_context_degraded",
    )
    if reason_codes & strict_codes:
        return "strict_degraded_context"
    quote_source = str(candidate.get("quote_source") or "").strip().lower()
    if quote_source in {"", "unknown", "none"}:
        return "strict_unknown_quote_source"
    entry = (
        _safe_float(candidate.get("execution_entry"))
        or _safe_float(candidate.get("display_entry"))
        or _safe_float(candidate.get("entry"))
    )
    stop_loss = _safe_float(candidate.get("stop_loss"))
    target = _safe_float(candidate.get("target"))
    if entry is None or stop_loss is None or target is None:
        return "strict_missing_trade_levels"
    return None


def _soft_reject_reason(candidate: dict[str, Any]) -> str:
    source_flags = candidate.get("source_flags")
    if isinstance(source_flags, dict):
        reason = str(source_flags.get("soft_reject_reason") or "").strip().lower()
        if reason:
            return reason
    return str(
        candidate.get("entry_block_code")
        or candidate.get("reject_reason")
        or ""
    ).strip().lower()


def _blocks_execute_due_to_soft_reject(candidate: dict[str, Any]) -> bool:
    soft_reason = _soft_reject_reason(candidate)
    if soft_reason in {"weak_signal", "no_signal", "signal_score_below_min"}:
        return True
    source_flags = candidate.get("source_flags")
    candidate_origin = ""
    if isinstance(source_flags, dict):
        candidate_origin = str(source_flags.get("candidate_origin") or "").strip().lower()
    if not candidate_origin:
        candidate_origin = str(candidate.get("candidate_origin") or "").strip().lower()
    if candidate_origin in {"softened_builder_path", "softened"} and bool(soft_reason):
        return True
    return False


def _soft_execution_not_ready_liquidity_fallback(candidate: dict[str, Any]) -> bool:
    if not bool(getattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True)):
        return False
    if not bool(
        getattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_FALLBACK_ENABLE", True)
    ):
        return False
    candidate_status = str(candidate.get("candidate_status") or "").strip().lower()
    if candidate_status not in {"executable", "near_executable"}:
        return False
    if not _safe_bool(candidate.get("execution_allowed"), default=True):
        return False
    if not _safe_bool(candidate.get("tradable"), default=True):
        return False
    if _safe_bool(candidate.get("execution_blocked"), default=False):
        return False
    if candidate.get("execution_ok") is not False:
        return False
    if bool(_soft_reject_reason(candidate)):
        return False
    min_liquidity_score = float(
        getattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_MIN", 0.50) or 0.50
    )
    return float(_liquidity_score(candidate)) >= float(min_liquidity_score)


def _hard_filter_reasons(candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    soft_penalties: list[str] = list(candidate.get("phase2_soft_penalties") or [])
    mode = _mode_for_candidate(candidate)
    allow_relax = not _live_mode(mode) or _allow_relaxed_live()
    no_signal_relax = bool(getattr(cfg, "PHASE2_RELAX_NO_SIGNAL", True)) and allow_relax
    latency_relax = bool(getattr(cfg, "PHASE2_DISABLE_LATENCY_BLOCK", True)) and allow_relax

    max_spread = _effective_max_spread_pct(candidate)
    spread_pct = _spread_pct(candidate)
    if spread_pct is not None and spread_pct >= max_spread:
        reasons.append("hard_spread")

    execution_allowed = _safe_bool(candidate.get("execution_allowed"), default=True)
    tradable = _safe_bool(candidate.get("tradable"), default=True)
    execution_ok = candidate.get("execution_ok")
    execution_blocked = _safe_bool(candidate.get("execution_blocked"), default=False)
    min_execution_score = float(getattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.50) or 0.50)
    min_execution_quality_score = float(
        getattr(cfg, "PHASE2_MIN_EXECUTION_QUALITY_SCORE", 0.30) or 0.30
    )
    allow_soft_degrade = bool(getattr(cfg, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", True))
    allow_soft_execution_not_ready = bool(
        getattr(cfg, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", True)
    )
    execution_quality_score = _safe_float(candidate.get("execution_quality_score"))
    execution_quality_low = (
        execution_quality_score is not None
        and execution_quality_score < min_execution_quality_score
    )
    weak_soft_reject_candidate = _blocks_execute_due_to_soft_reject(candidate)
    soft_reject_execute_block_enable = bool(
        getattr(cfg, "PHASE2_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", False)
    )
    weak_soft_reject_execute_block = weak_soft_reject_candidate and soft_reject_execute_block_enable
    if weak_soft_reject_execute_block:
        candidate["max_final_action"] = "QUEUE_ONLY"
        candidate["execution_allowed"] = False
        candidate["truth_allows_execution"] = False
    elif allow_soft_degrade and weak_soft_reject_candidate:
        soft_penalties.append("weak_signal_penalty")
        candidate["phase2_soft_degrade_reason"] = "weak_signal_soft_penalty"
        candidate["execution_context_degraded"] = True
        weak_signal_penalty = float(
            getattr(cfg, "PHASE2_WEAK_SIGNAL_SOFT_PENALTY", 0.06) or 0.06
        )
        existing_penalty = _safe_float(candidate.get("phase2_execution_penalty")) or 0.0
        candidate["phase2_execution_penalty"] = max(existing_penalty, weak_signal_penalty)
        if bool(getattr(cfg, "PHASE2_WEAK_SIGNAL_QUEUE_CAP_ENABLE", False)):
            candidate["max_final_action"] = "QUEUE_ONLY"
    execution_score = _execution_quality_score(candidate)
    no_signal_candidate = _is_no_signal_candidate(candidate)
    latency_only_block = _is_latency_only_block(candidate)
    liquidity_soft_fallback = _soft_execution_not_ready_liquidity_fallback(candidate)
    if no_signal_relax and no_signal_candidate:
        execution_allowed = True
        tradable = True
        if execution_ok is False:
            execution_ok = True
    if latency_relax and latency_only_block:
        execution_blocked = False
        if execution_ok is False:
            execution_ok = True
    execution_failure = (
        (not execution_allowed)
        or (not tradable)
        or execution_blocked
        or execution_ok is False
        or execution_score < min_execution_score
    )
    if execution_failure:
        reason_codes = set(_reason_codes(candidate))
        execution_not_ready_reason_codes = _execution_not_ready_reason_codes(candidate)
        critical_codes = _cfg_csv_set(
            "PHASE2_CRITICAL_EXECUTION_REASON_CODES",
            "feed_stale,no_live_option_feed,unresolved_contract,missing_contract_fields,missing_option_token,no_token,missing_entry,invalid_level_geometry,hard_spread_too_wide,spread_breached,execution_quality_reject",
        )
        soft_context_codes = _cfg_csv_set(
            "PHASE2_SOFT_CONTEXT_REASON_CODES",
            "missing_rr_context,rr_estimated_context,missing_liquidity_context,missing_spread_context,missing_timing_context,missing_live_timing_context,low_data_confidence,unknown_quote_source",
        )
        soft_execution_not_ready_codes = _cfg_csv_set(
            "PHASE2_SOFT_EXECUTION_NOT_READY_REASON_CODES",
            "stale_quote,inconsistent_quote,low_data_confidence,unverified_spread,missing_liquidity_validation",
        )
        hard_execution_not_ready_codes = _cfg_csv_set(
            "PHASE2_HARD_EXECUTION_NOT_READY_REASON_CODES",
            "data_not_live,fallback_driven_data,missing_quote,spread_breached",
        )
        has_critical = (
            bool(reason_codes & critical_codes)
            or bool(execution_not_ready_reason_codes & hard_execution_not_ready_codes)
            or any(code.startswith("HARD_") for code in reason_codes)
        )
        only_soft_context = bool(reason_codes) and not has_critical and not bool(reason_codes - soft_context_codes)
        soft_execution_not_ready_reason = bool(
            execution_not_ready_reason_codes & soft_execution_not_ready_codes
        )
        if not reason_codes and str(candidate.get("quote_source") or "").strip().lower() in {"", "unknown", "none"}:
            reason_codes.add("UNKNOWN_QUOTE_SOURCE")
            only_soft_context = True
        execution_not_ready_soft_failure = (
            allow_soft_execution_not_ready
            and execution_allowed
            and tradable
            and execution_ok is False
            and (not execution_blocked)
            and (not has_critical)
            and (
                soft_execution_not_ready_reason
                or execution_quality_low
                or execution_score >= min_execution_score
                or _is_borderline_execution_candidate(candidate)
                or only_soft_context
                or liquidity_soft_fallback
            )
        )
        quality_only_failure = (
            execution_allowed
            and tradable
            and (execution_ok is not False)
            and (not execution_blocked)
            and (not has_critical)
            and execution_quality_low
        )
        execution_degrade_penalty = float(
            getattr(cfg, "PHASE2_SOFT_EXECUTION_DEGRADE_PENALTY", 0.10) or 0.10
        )
        if has_critical:
            reasons.append("hard_execution")
        elif execution_not_ready_soft_failure:
            soft_penalties.append("soft_execution_not_ready")
            candidate["phase2_soft_degrade_reason"] = "execution_not_ready_noncritical"
            candidate["execution_context_degraded"] = True
            candidate["phase2_execution_penalty"] = max(
                float(getattr(cfg, "PHASE2_LIQUIDITY_SOFT_PENALTY", 0.08) or 0.08),
                float(min_execution_score - max(execution_score, 0.0)),
            )
            candidate["max_final_action"] = "QUEUE_ONLY"
        elif allow_soft_degrade and quality_only_failure:
            soft_penalties.append("soft_execution_degraded")
            candidate["phase2_soft_degrade_reason"] = "execution_quality_low"
            candidate["execution_context_degraded"] = True
            candidate["phase2_execution_penalty"] = max(
                execution_degrade_penalty,
                float(min_execution_quality_score - float(execution_quality_score or 0.0)),
            )
            candidate["max_final_action"] = "QUEUE_ONLY"
        elif allow_soft_degrade and _is_borderline_execution_candidate(candidate) and (
            only_soft_context or str(candidate.get("quote_source") or "").strip().lower() in {"", "unknown", "none"}
        ):
            soft_penalties.append("execution_context_degraded")
            candidate["phase2_soft_degrade_reason"] = "execution_context_low"
            candidate["execution_context_degraded"] = True
            candidate["phase2_execution_penalty"] = max(
                float(getattr(cfg, "PHASE2_LIQUIDITY_SOFT_PENALTY", 0.08) or 0.08),
                float(min_execution_score - max(execution_score, 0.0)),
            )
            candidate["max_final_action"] = "QUEUE_ONLY"
        else:
            reasons.append("hard_execution")

    min_liq_score = float(getattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35) or 0.35)
    liquidity_score = _liquidity_score(candidate)
    if liquidity_score < min_liq_score:
        if _is_borderline_execution_candidate(candidate):
            soft_penalties.append("liquidity_penalty")
            candidate["phase2_liquidity_penalty"] = float(min_liq_score - liquidity_score)
        else:
            reasons.append("hard_liquidity")

    candidate["phase2_soft_penalties"] = soft_penalties

    return reasons


def _compute_phase2_final_score(candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    existing = _safe_float(candidate.get("final_score"))
    score_origin = str(
        candidate.get("score_origin")
        or candidate.get("final_score_source")
        or ""
    ).strip().lower()
    authoritative_existing = (
        existing is not None
        and (
            bool(candidate.get("phase2_score_detail"))
            or score_origin in {"phase2", "decision_engine", "review_queue_terminal"}
            or float(existing) > 0.0
        )
    )
    result: dict[str, Any] = {}
    final_score: float

    if authoritative_existing:
        final_score = float(existing)
        result["phase2_reused_final_score"] = True
    else:
        market_mode = str(
            candidate.get("market_mode")
            or candidate.get("execution_mode")
            or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).strip().upper()
        candidate_class = str(candidate.get("candidate_class") or "").strip().upper()
        if not candidate_class:
            if _safe_bool(candidate.get("execution_allowed"), True) and _safe_bool(candidate.get("tradable"), True):
                candidate_class = "EXECUTABLE"
            else:
                candidate_class = "ADVISORY_ONLY"

        signal_score = safe_get(candidate, "signal_score", 0.0)
        execution_score = safe_get(candidate, "execution_score", 0.0)
        liquidity_score = safe_get(candidate, "liquidity_score", 0.0)

        setup_score = _safe_float(candidate.get("setup_score"))
        trigger_score = _safe_float(candidate.get("trigger_score"))
        entry_quality_score = _safe_float(candidate.get("entry_quality_score"))
        family_survival_score = _safe_float(candidate.get("family_survival_score"))
        setup_quality = setup_score
        if setup_quality is None:
            setup_quality = signal_score
        if setup_quality is None:
            setup_quality = _safe_float(candidate.get("trade_score"))
            if setup_quality is not None and setup_quality > 1.0:
                setup_quality = max(0.0, min(1.0, setup_quality / 100.0))
        confluence_score = (
            _safe_float(candidate.get("confidence_final"))
            or _safe_float(candidate.get("gating_final_confidence"))
            or _safe_float(candidate.get("confidence"))
            or _safe_float(candidate.get("signal_score"))
            or 0.0
        )
        regime_fit = (
            _safe_float(candidate.get("regime_fit"))
            or _safe_float(candidate.get("regime_score"))
            or _safe_float(candidate.get("trade_alignment"))
            or 0.5
        )

        result = compute_final_score(
            candidate,
            candidate_class=candidate_class,
            market_mode=market_mode or "SIM",
            setup_quality=setup_quality,
            confluence_score=confluence_score,
            regime_fit=regime_fit,
            liquidity_quality=max(_liquidity_score(candidate), liquidity_score),
            freshness_quality=(
                _safe_float(candidate.get("freshness_quality"))
                or (1.0 if _safe_bool(candidate.get("fresh_quote_ok"), default=True) else 0.0)
            ),
            execution_feasibility=max(_execution_quality_score(candidate), execution_score),
            data_confidence=_safe_float(candidate.get("data_confidence")),
            setup_score=setup_score,
            trigger_score=trigger_score,
            entry_quality_score=entry_quality_score,
            family_survival_score=family_survival_score,
            risk_learning_adjustment=_safe_float(candidate.get("risk_learning_adjustment")),
            risk_learning_confidence=_safe_float(candidate.get("risk_learning_confidence")),
            is_fallback=_safe_bool(candidate.get("synthetic_candidate"), default=False),
            stale_quote=not _safe_bool(candidate.get("fresh_quote_ok"), default=True),
            missing_liquidity=not _safe_bool(candidate.get("liquidity_ok"), default=True),
            spread_uncertain=_safe_float(candidate.get("spread_pct")) is None,
        )
        final_score = _safe_float(result.get("final_score")) or 0.0
    soft_penalties = list(candidate.get("phase2_soft_penalties") or [])
    if "liquidity_penalty" in soft_penalties:
        liquidity_penalty = float(getattr(cfg, "PHASE2_LIQUIDITY_SOFT_PENALTY", 0.08) or 0.08)
        final_score = max(0.0, float(final_score) - float(liquidity_penalty))
        result["phase2_liquidity_soft_penalty"] = float(liquidity_penalty)
    execution_penalty = _safe_float(candidate.get("phase2_execution_penalty"))
    if execution_penalty is not None and execution_penalty > 0.0:
        final_score = max(0.0, float(final_score) - float(execution_penalty))
        result["phase2_execution_soft_penalty"] = float(execution_penalty)
    if soft_penalties:
        result["phase2_soft_penalties"] = soft_penalties
    if not authoritative_existing:
        result["phase2_recomputed_final_score"] = True
    return float(final_score), dict(result or {})


def _apply_data_fallbacks(candidate: dict[str, Any]) -> None:
    mode = _mode_for_candidate(candidate)
    live_mode = _live_mode(mode)
    if _safe_float(candidate.get("quote_age_sec")) is None:
        if live_mode:
            candidate["phase2_missing_quote_age_sec"] = True
            candidate.setdefault("gate_reasons", [])
            if "missing_live_timing_context" not in candidate["gate_reasons"]:
                candidate["gate_reasons"].append("missing_live_timing_context")
            candidate["execution_ok"] = False
            candidate["execution_quality_reason_code"] = "missing_live_timing_context"
        else:
            candidate["quote_age_sec"] = 1.0
            candidate["phase2_quote_age_fallback_used"] = True
    if _safe_float(candidate.get("spread_pct")) is None:
        if live_mode:
            candidate["phase2_missing_spread_context"] = True
            candidate.setdefault("gate_reasons", [])
            if "missing_spread_context" not in candidate["gate_reasons"]:
                candidate["gate_reasons"].append("missing_spread_context")
            candidate["execution_ok"] = False
            candidate["execution_quality_reason_code"] = "missing_spread_context"
        else:
            candidate["spread_pct"] = float(getattr(cfg, "PHASE2_SPREAD_FALLBACK_PCT", 0.003) or 0.003)
            candidate["phase2_spread_fallback_used"] = True
    if _safe_float(candidate.get("liquidity_score")) is None:
        derived_liquidity_score = _liquidity_score(candidate)
        if _safe_float(candidate.get("best_bid")) is not None and _safe_float(candidate.get("best_ask")) is not None:
            candidate["liquidity_score"] = float(derived_liquidity_score)
            candidate["phase2_liquidity_derived_from_book"] = True
        else:
            if live_mode:
                candidate["phase2_missing_liquidity_validation"] = True
                candidate.setdefault("gate_reasons", [])
                if "missing_liquidity_validation" not in candidate["gate_reasons"]:
                    candidate["gate_reasons"].append("missing_liquidity_validation")
                candidate["execution_ok"] = False
                candidate["execution_quality_reason_code"] = "missing_liquidity_validation"
            else:
                candidate["liquidity_score"] = float(getattr(cfg, "PHASE2_LIQUIDITY_FALLBACK_SCORE", 0.5) or 0.5)
                candidate["phase2_liquidity_fallback_used"] = True
    quote_source = str(candidate.get("quote_source") or "").strip().lower()
    if not quote_source:
        if live_mode:
            candidate["quote_source"] = "unknown"
            quote_source = "unknown"
            candidate.setdefault("gate_reasons", [])
            if "unknown_quote_source" not in candidate["gate_reasons"]:
                candidate["gate_reasons"].append("unknown_quote_source")
            candidate["execution_ok"] = False
            candidate["execution_quality_reason_code"] = "unknown_quote_source"
        else:
            candidate["quote_source"] = "unknown"
            quote_source = "unknown"
    if quote_source == "unknown":
        phase2_soft_penalties = list(candidate.get("phase2_soft_penalties") or [])
        if "unknown_quote_source" not in phase2_soft_penalties:
            phase2_soft_penalties.append("unknown_quote_source")
        candidate["phase2_soft_penalties"] = phase2_soft_penalties
    depth_score = _safe_float(candidate.get("depth_score"))
    if depth_score is not None and float(depth_score) == 0.0:
        candidate["depth_score"] = 0.5
    if _safe_float(candidate.get("tick_volume")) is None:
        candidate["tick_volume"] = 1.0


def _apply_profile_rejection_setup(candidate: dict[str, Any]) -> None:
    try:
        setup = evaluate_profile_rejection_setup(candidate)
    except Exception:
        return

    telemetry = dict(setup.telemetry or {})

    candidate["profile_rejection_detected"] = bool(setup.detected)
    candidate["profile_rejection_telemetry"] = telemetry

    source_flags = candidate.get("source_flags")
    if not isinstance(source_flags, dict):
        source_flags = {}

    source_flags["profile_rejection_detected"] = bool(setup.detected)

    if telemetry:
        source_flags["profile_rejection_telemetry"] = telemetry

    if not setup.detected:
        candidate["source_flags"] = source_flags
        return

    candidate.setdefault("strategy_family", "profile_rejection")
    candidate["setup_name"] = "mean_reversion_profile_rejection"
    candidate["decision_playbook"] = "profile_rejection"
    candidate["setup_direction"] = setup.direction

    candidate["setup_score"] = max(
        float(candidate.get("setup_score") or 0.0),
        float(setup.setup_score),
    )
    candidate["profile_rejection_setup_score"] = float(setup.setup_score)
    candidate["trigger_score"] = max(
        float(candidate.get("trigger_score") or 0.0),
        float(setup.trigger_score),
    )
    candidate["profile_rejection_trigger_score"] = float(setup.trigger_score)
    candidate["entry_quality_score"] = max(
        float(candidate.get("entry_quality_score") or 0.0),
        float(setup.entry_quality_score),
    )
    candidate["profile_rejection_entry_quality_score"] = float(setup.entry_quality_score)

    candidate["profile_rejection_rr"] = float(setup.rr)

    if candidate.get("entry") is None:
        candidate["entry"] = float(setup.entry)

    if candidate.get("execution_entry") is None:
        candidate["execution_entry"] = float(setup.entry)

    if candidate.get("display_entry") is None:
        candidate["display_entry"] = float(setup.entry)

    if candidate.get("stop_loss") is None:
        candidate["stop_loss"] = float(setup.stop)

    if candidate.get("target") is None:
        candidate["target"] = float(setup.target)

    source_flags["setup_name"] = "mean_reversion_profile_rejection"
    source_flags["profile_rejection_rr"] = float(setup.rr)

    candidate["source_flags"] = source_flags


def _apply_breakout_setup(candidate: dict[str, Any]) -> None:
    try:
        setup = evaluate_breakout_continuation_setup(candidate)
    except Exception:
        return

    telemetry = dict(setup.telemetry or {})
    candidate["breakout_detected"] = bool(setup.detected)
    candidate["breakout_telemetry"] = telemetry

    source_flags = candidate.get("source_flags")
    if not isinstance(source_flags, dict):
        source_flags = {}
    source_flags["breakout_detected"] = bool(setup.detected)
    if telemetry:
        source_flags["breakout_telemetry"] = telemetry

    if not setup.detected:
        candidate["source_flags"] = source_flags
        return

    candidate.setdefault("strategy_family", "breakout_continuation")
    candidate["breakout_setup_score"] = float(setup.setup_score)
    candidate["breakout_trigger_score"] = float(setup.trigger_score)
    candidate["breakout_entry_quality_score"] = float(setup.entry_quality_score)
    candidate["setup_name"] = "trend_breakout_continuation"
    candidate["setup_direction"] = setup.direction
    candidate["breakout_rr"] = float(setup.rr)

    candidate["setup_score"] = max(
        float(candidate.get("setup_score") or 0.0),
        float(setup.setup_score),
    )
    candidate["trigger_score"] = max(
        float(candidate.get("trigger_score") or 0.0),
        float(setup.trigger_score),
    )
    candidate["entry_quality_score"] = max(
        float(candidate.get("entry_quality_score") or 0.0),
        float(setup.entry_quality_score),
    )

    if candidate.get("entry") is None:
        candidate["entry"] = float(setup.entry)
    if candidate.get("execution_entry") is None:
        candidate["execution_entry"] = float(setup.entry)
    if candidate.get("display_entry") is None:
        candidate["display_entry"] = float(setup.entry)
    if candidate.get("stop_loss") is None:
        candidate["stop_loss"] = float(setup.stop)
    if candidate.get("target") is None:
        candidate["target"] = float(setup.target)

    source_flags["breakout_rr"] = float(setup.rr)
    source_flags["setup_name"] = "trend_breakout_continuation"
    candidate["source_flags"] = source_flags


def build_candidates_phase2(raw_candidates: list[Any] | None = None) -> list[dict[str, Any]]:
    raw_list = list(raw_candidates or [])
    if not raw_list:
        logger.warning("PHASE2: No input candidates for phase2 raw_count=0")
        return []
    ranked_candidates: list[dict[str, Any]] = []
    drop_reason_counts: dict[str, int] = {}
    drop_debug_samples: list[dict[str, Any]] = []
    invalid_candidate_count = 0
    invalid_candidate_samples: list[dict[str, Any]] = []
    invalid_sample_limit = max(
        0,
        int(getattr(cfg, "PHASE2_INVALID_CANDIDATE_LOG_SAMPLE_LIMIT", 5) or 5),
    )
    drop_debug_budget = int(getattr(cfg, "PHASE2_FILTER_DROP_DEBUG_LIMIT", 25) or 25)
    drop_sample_limit = max(
        0,
        int(getattr(cfg, "PHASE2_FILTER_DROP_DEBUG_SAMPLE_LIMIT", 5) or 5),
    )
    for raw in raw_list:
        candidate = _candidate_to_dict(raw)
        if not validate_candidate(candidate):
            invalid_candidate_count += 1
            if len(invalid_candidate_samples) < invalid_sample_limit:
                invalid_candidate_samples.append(
                    {
                        "trade_id": candidate.get("trade_id"),
                        "symbol": candidate.get("symbol"),
                    }
                )
            continue
        strict_drop_reason = _strict_mode_drop_reason(candidate)
        if strict_drop_reason:
            drop_reason_counts[strict_drop_reason] = int(drop_reason_counts.get(strict_drop_reason, 0)) + 1
            if drop_debug_budget > 0:
                if len(drop_debug_samples) < drop_sample_limit:
                    drop_debug_samples.append(
                        {
                            "trade_id": candidate.get("trade_id"),
                            "symbol": candidate.get("symbol"),
                            "reasons": [strict_drop_reason],
                            "candidate_status": candidate.get("candidate_status"),
                            "execution_status": candidate.get("execution_status"),
                            "candidate_origin": candidate.get("candidate_origin"),
                        }
                    )
                drop_debug_budget -= 1
            continue
        _apply_data_fallbacks(candidate)
        # LIVE strict contract: missing/fallback-driven RR context must never be executable.
        mode = _mode_for_candidate(candidate)
        if _live_mode(mode):
            reason_codes = set(_reason_codes(candidate))
            if "RR_ESTIMATED_CONTEXT" in reason_codes or "MISSING_RR_CONTEXT" in reason_codes:
                candidate.setdefault("gate_reasons", [])
                if "RR_ESTIMATED_CONTEXT" in reason_codes and "rr_estimated_context" not in candidate["gate_reasons"]:
                    candidate["gate_reasons"].append("rr_estimated_context")
                if "MISSING_RR_CONTEXT" in reason_codes and "missing_rr_context" not in candidate["gate_reasons"]:
                    candidate["gate_reasons"].append("missing_rr_context")
                candidate["execution_ok"] = False
                candidate["execution_quality_reason_code"] = "rr_estimated_context" if "RR_ESTIMATED_CONTEXT" in reason_codes else "missing_rr_context"
        candidate["liquidity_score"] = float(_liquidity_score(candidate))
        _apply_profile_rejection_setup(candidate)
        if bool(getattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False)):
            _apply_breakout_setup(candidate)
            selected_playbook = select_playbook(candidate)
            candidate["selected_playbook"] = selected_playbook
            source_flags = candidate.get("source_flags")
            if not isinstance(source_flags, dict):
                source_flags = {}
            source_flags["selected_playbook"] = selected_playbook
            candidate["source_flags"] = source_flags

            playbook_drop_reason: str | None = None
            if selected_playbook == "none":
                playbook_drop_reason = "playbook_none_selected"
            elif selected_playbook == "profile_rejection" and not bool(candidate.get("profile_rejection_detected")):
                playbook_drop_reason = "playbook_profile_rejection_not_detected"
            elif selected_playbook == "breakout_continuation" and not bool(candidate.get("breakout_detected")):
                playbook_drop_reason = "playbook_breakout_not_detected"

            if playbook_drop_reason is not None:
                drop_reason_counts[playbook_drop_reason] = int(drop_reason_counts.get(playbook_drop_reason, 0)) + 1
                if drop_debug_budget > 0:
                    if len(drop_debug_samples) < drop_sample_limit:
                        drop_debug_samples.append(
                            {
                                "trade_id": candidate.get("trade_id"),
                                "symbol": candidate.get("symbol"),
                                "reasons": [playbook_drop_reason],
                                "selected_playbook": selected_playbook,
                                "profile_rejection_detected": candidate.get("profile_rejection_detected"),
                                "breakout_detected": candidate.get("breakout_detected"),
                            }
                        )
                    drop_debug_budget -= 1
                continue

            candidate["decision_playbook"] = selected_playbook
        hard_reasons = _hard_filter_reasons(candidate)
        if hard_reasons:
            for reason in hard_reasons:
                drop_reason_counts[reason] = int(drop_reason_counts.get(reason, 0)) + 1
            if drop_debug_budget > 0:
                if len(drop_debug_samples) < drop_sample_limit:
                    drop_debug_samples.append(
                        {
                            "trade_id": candidate.get("trade_id"),
                            "symbol": candidate.get("symbol"),
                            "reasons": hard_reasons,
                            "execution_allowed": candidate.get("execution_allowed"),
                            "execution_ok": candidate.get("execution_ok"),
                            "liquidity_score": candidate.get("liquidity_score"),
                            "candidate_status": candidate.get("candidate_status"),
                            "execution_status": candidate.get("execution_status"),
                            "candidate_origin": candidate.get("candidate_origin"),
                        }
                    )
                drop_debug_budget -= 1
            continue
        final_score, score_detail = _compute_phase2_final_score(candidate)
        candidate["final_score"] = float(final_score)
        candidate["score"] = float(final_score)
        candidate["phase2_score_detail"] = score_detail
        candidate["phase2_hard_filters"] = {
            "spread_ok": "hard_spread" not in hard_reasons,
            "execution_ok": "hard_execution" not in hard_reasons,
            "liquidity_ok": "hard_liquidity" not in hard_reasons,
        }
        ranked_candidates.append(candidate)

    if invalid_candidate_count:
        logger.warning(
            "PHASE2: invalid candidates skipped count=%s sample=%s",
            invalid_candidate_count,
            invalid_candidate_samples,
        )
    if drop_reason_counts and drop_debug_samples:
        logger.info(
            "PHASE2_FILTER_DROP_SUMMARY count=%s reasons=%s sample=%s",
            sum(int(v or 0) for v in drop_reason_counts.values()),
            drop_reason_counts,
            drop_debug_samples,
        )

    if not ranked_candidates:
        logger.warning(
            "PHASE2: No valid candidates after filtering raw_count=%s drop_counts=%s",
            len(raw_list),
            drop_reason_counts,
        )
        return []

    ranked_candidates.sort(
        key=lambda row: (
            float(_safe_float(row.get("final_score")) or 0.0),
            float(_safe_float(row.get("execution_score")) or 0.0),
            float(_safe_float(row.get("confidence_final")) or _safe_float(row.get("confidence")) or 0.0),
        ),
        reverse=True,
    )
    return ranked_candidates


def _active_trade_score(active_trade: dict[str, Any] | None) -> float | None:
    if not isinstance(active_trade, dict):
        return None
    for key in ("final_score", "rank_score", "opportunity_score"):
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


def _should_clear_trade(active_trade: dict[str, Any] | None) -> bool:
    if not isinstance(active_trade, dict) or not active_trade:
        return False
    max_age = float(getattr(cfg, "PHASE2_ACTIVE_TRADE_MAX_AGE_SEC", 30.0) or 30.0)
    if max_age <= 0.0:
        return False
    anchor_epoch = (
        _safe_float(active_trade.get("decision_ts_epoch"))
        or _safe_float(active_trade.get("timestamp_epoch"))
        or _safe_float(active_trade.get("ts_epoch"))
    )
    if anchor_epoch is None or anchor_epoch <= 0:
        return False
    return (time.time() - float(anchor_epoch)) > float(max_age)


def _queue_only_capped(candidate: dict[str, Any] | None) -> bool:
    if not isinstance(candidate, dict):
        return False
    return str(candidate.get("max_final_action") or "").strip().upper() == "QUEUE_ONLY"


def run_engine_phase2(
    raw_candidates: list[Any] | None,
    *,
    active_trade: Any = None,
    min_enter_score: float | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    def _normalize_selected(selected: Any) -> dict[str, Any] | None:
        if selected is None:
            return None
        selected_dict = _candidate_to_dict(selected)
        selected_dict.setdefault("score", _safe_float(selected_dict.get("final_score")) or 0.0)
        selected_dict.setdefault("symbol", str(selected_dict.get("symbol") or ""))
        selected_dict.setdefault("decision_ts_epoch", float(time.time()))
        if not str(selected_dict.get("symbol") or "").strip():
            return None
        if _safe_float(selected_dict.get("score")) is None:
            return None
        return selected_dict

    def _log_state(state: str, selected: dict[str, Any] | None, ranked_count: int) -> None:
        symbol = selected.get("symbol") if isinstance(selected, dict) else None
        score = (
            _safe_float(selected.get("score"))
            if isinstance(selected, dict)
            else None
        )
        logger.info(
            "PHASE2_DECISION | state=%s | ranked_count=%s | top_score=%s | symbol=%s",
            state,
            int(ranked_count),
            score,
            symbol,
        )

    ranked = build_candidates_phase2(raw_candidates)
    top_limit = max(1, int(top_n if top_n is not None else getattr(cfg, "PHASE2_TOP_N", 3) or 3))
    min_enter = float(
        min_enter_score
        if min_enter_score is not None
        else getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.70)
    )
    strict_real_only = bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False))
    force_fallback = bool(getattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", True))
    if strict_real_only:
        force_fallback = False
    force_fallback_min_score = float(getattr(cfg, "PHASE2_FORCE_FALLBACK_MIN_SCORE", 0.05) or 0.05)
    allow_fallback_live = bool(getattr(cfg, "PHASE2_FORCE_FALLBACK_ALLOW_LIVE", False))
    ranked_top = list(ranked[:top_limit])
    active_trade_dict = _candidate_to_dict(active_trade) if active_trade is not None else None
    if _should_clear_trade(active_trade_dict):
        logger.info(
            "PHASE2: clearing stale active_trade trade_id=%s",
            (active_trade_dict or {}).get("trade_id"),
        )
        active_trade_dict = None

    if not ranked_top:
        _log_state("NO_TRADE", None, ranked_count=0)
        return {
            "state": "NO_TRADE",
            "reason": "no_rankable_candidates",
            "selected": None,
            "ranked": [],
            "next_active_trade": None,
        }

    top = ranked_top[0]
    top_score = float(_safe_float(top.get("final_score")) or 0.0)
    active_score = _active_trade_score(active_trade_dict)
    min_abs_delta = float(getattr(cfg, "PHASE2_REPLACE_MIN_ABS_DELTA", 0.12) or 0.12)
    min_rel_delta = float(getattr(cfg, "PHASE2_REPLACE_MIN_REL_DELTA", 0.20) or 0.20)

    if active_trade_dict is not None:
        if (
            top_score >= min_enter
            and not _queue_only_capped(top)
            and _should_replace(
            active_score,
            top_score,
            min_abs_delta=min_abs_delta,
            min_rel_delta=min_rel_delta,
            )
        ):
            selected = _normalize_selected(top)
            if selected is None:
                _log_state("NO_TRADE", None, ranked_count=len(ranked_top))
                return {
                    "state": "NO_TRADE",
                    "reason": "invalid_selected_payload",
                    "selected": None,
                    "ranked": ranked_top,
                    "next_active_trade": active_trade_dict,
                }
            _log_state("REPLACE", selected, ranked_count=len(ranked_top))
            return {
                "state": "REPLACE",
                "reason": "top_ranked_upgrade",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": selected,
            }
        active_selected = _normalize_selected(active_trade_dict) or active_trade_dict
        _log_state("HOLD", active_selected if isinstance(active_selected, dict) else None, ranked_count=len(ranked_top))
        return {
            "state": "HOLD",
            "reason": "no_significant_upgrade",
            "selected": active_selected,
            "ranked": ranked_top,
            "next_active_trade": active_selected,
        }

    if top_score >= min_enter:
        mode = _mode_for_candidate(top)
        if _live_mode(mode) and _is_fallback_driven_candidate(top):
            selected = _normalize_selected(top)
            if selected is not None:
                selected["execution_status"] = "not_executable"
                selected["candidate_status"] = "watchlist"
                selected["execution_block_reason"] = "live_fallback_candidate_blocked"
                selected["live_fallback_execution_blocked"] = True
            _log_state("WATCHLIST", selected, ranked_count=len(ranked_top))
            return {
                "state": "WATCHLIST",
                "reason": "live_fallback_candidate_blocked",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": None,
            }
        if _queue_only_capped(top):
            selected = _normalize_selected(top)
            _log_state("WATCHLIST", selected, ranked_count=len(ranked_top))
            return {
                "state": "WATCHLIST",
                "reason": "queue_only_cap",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": None,
            }
        selected = _normalize_selected(top)
        if selected is None:
            _log_state("NO_TRADE", None, ranked_count=len(ranked_top))
            return {
                "state": "NO_TRADE",
                "reason": "invalid_selected_payload",
                "selected": None,
                "ranked": ranked_top,
                "next_active_trade": None,
            }
        _log_state("ENTER", selected, ranked_count=len(ranked_top))
        return {
            "state": "ENTER",
            "reason": "top_ranked",
            "selected": selected,
            "ranked": ranked_top,
            "next_active_trade": selected,
        }

    selected = _normalize_selected(top)

    if force_fallback and selected is not None:
        if _queue_only_capped(selected):
            _log_state("WATCHLIST", selected, ranked_count=len(ranked_top))
            return {
                "state": "WATCHLIST",
                "reason": "queue_only_cap",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": None,
            }
        mode = _mode_for_candidate(selected)
        allow_mode = (not _live_mode(mode)) or allow_fallback_live
        if _live_mode(mode):
            allow_mode = False
        if allow_mode and top_score >= force_fallback_min_score:
            logger.warning(
                "FORCED_EXECUTION_FALLBACK trade_id=%s symbol=%s score=%.4f mode=%s",
                selected.get("trade_id"),
                selected.get("symbol"),
                top_score,
                mode,
            )
            selected["execution_status"] = "executable"
            selected["candidate_status"] = "executable"
            selected["forced_fallback_execution"] = True
            _log_state("ENTER", selected, ranked_count=len(ranked_top))
            return {
                "state": "ENTER",
                "reason": "forced_fallback_execution",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": selected,
            }
        if _live_mode(mode) and top_score >= force_fallback_min_score:
            selected["execution_status"] = "not_executable"
            selected["candidate_status"] = "watchlist"
            selected["execution_block_reason"] = "live_forced_fallback_disabled"
            selected["live_fallback_execution_blocked"] = True

    _log_state("WATCHLIST", selected, ranked_count=len(ranked_top))
    return {
        "state": "WATCHLIST",
        "reason": "top_score_below_enter_threshold",
        "selected": selected,
        "ranked": ranked_top,
        "next_active_trade": None,
    }


# Preserve a stable reference to the original Phase2 builder so adapter wrappers
# can safely delegate even after module-level monkeypatching or reloads.
_BASE_BUILD_CANDIDATES_PHASE2 = build_candidates_phase2
