from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg
from core.candidate_quote_freshness import classify_candidate_quote_freshness
from core.option_spread_truth import classify_option_spread_truth
from core.strategy_signal_quality import classify_strategy_signal_quality

EXECUTABLE_TRUTH_FIREBREAK_CODE = "EXECUTABLE_TRUTH_FIREBREAK_FAILED"
FALLBACK_DRIVEN_REASON = "fallback_driven_data"
DEGRADED_DATA_REASON = "degraded_data"
DATA_NOT_LIVE_REASON = "data_not_live"
PRICE_MISMATCH_REASON = "price_mismatch_quote"
STALE_OPTION_LTP_REASON = "stale_option_ltp"
SUBSCRIPTION_FAILED_REASON = "subscription_failed_quote"

_FALLBACK_CHAIN_SOURCES = {
    "synthetic_chain",
    "close_fallback",
    "quote_fallback",
    "recovered_fallback",
    "fallback_close",
    "fallback_last_atm",
    "rest_fallback",
    "fallback",
    "fallback_recovered",
}

_FALLBACK_RR_SOURCES = {
    "fallback_estimated",
    "estimated_fallback",
    "fallback",
}

_PRICE_MISMATCH_STATUSES = {
    "PRICE_MISMATCH",
    "QUOTE_PRICE_MISMATCH",
}

_STALE_QUOTE_STATUSES = {
    "STALE_OPTION_LTP",
    "STALE_QUOTE",
    "QUOTE_EXCEEDS_THRESHOLD",
    "QUOTE_EXCEEDS_SLA",
}

_SUBSCRIPTION_FAILED_STATUSES = {
    "SUBSCRIPTION_FAILED",
    "OPTION_SUBSCRIPTION_FAILED",
}


@dataclass(frozen=True)
class ExecutableTruthDecision:
    execution_allowed: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    return candidate.get(field, default) if isinstance(candidate, dict) else getattr(candidate, field, default)


def _source_flags(candidate: Any) -> dict[str, Any]:
    flags = _candidate_get(candidate, "source_flags", {}) or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def _append_unique(reasons: list[str], reason: str | None) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_lower(value: Any) -> str:
    return _normalized_text(value).lower()


def _normalized_upper(value: Any) -> str:
    return _normalized_text(value).upper()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _configured_mode() -> str:
    return str(_coalesce(getattr(cfg, "EXECUTION_MODE", None), getattr(cfg, "TRADING_MODE", None)) or "").strip().upper()


def _advisory_reason(candidate: Any, flags: dict[str, Any]) -> str:
    if _configured_mode() == "LIVE":
        return DATA_NOT_LIVE_REASON
    runtime_mode = str(
        _coalesce(
            flags.get("runtime_mode"),
            _candidate_get(candidate, "execution_mode"),
            _candidate_get(candidate, "mode"),
            flags.get("market_mode"),
        )
        or ""
    ).strip().upper()
    if runtime_mode == "LIVE":
        return DATA_NOT_LIVE_REASON
    return DEGRADED_DATA_REASON


def _quote_truth_maps(candidate: Any, flags: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    quote_truth = _mapping(flags.get("quote_truth"))
    quote_truth_snapshot = _mapping(flags.get("quote_truth_snapshot"))
    return quote_truth, quote_truth_snapshot


def _quote_sources(candidate: Any, flags: dict[str, Any]) -> set[str]:
    quote_truth, quote_truth_snapshot = _quote_truth_maps(candidate, flags)
    values = {
        _candidate_get(candidate, "chain_source"),
        flags.get("chain_source"),
        _candidate_get(candidate, "price_source"),
        flags.get("price_source"),
        _candidate_get(candidate, "quote_source"),
        flags.get("quote_source"),
        _candidate_get(candidate, "option_ltp_source"),
        flags.get("option_ltp_source"),
        quote_truth.get("quote_source"),
        quote_truth.get("option_ltp_source"),
        quote_truth_snapshot.get("quote_source"),
        quote_truth_snapshot.get("option_ltp_source"),
    }
    return {_normalized_lower(value) for value in values if _normalized_text(value)}


def _quote_validation_statuses(candidate: Any, flags: dict[str, Any]) -> set[str]:
    quote_truth, quote_truth_snapshot = _quote_truth_maps(candidate, flags)
    values = {
        _candidate_get(candidate, "quote_validation_status"),
        flags.get("quote_validation_status"),
        _candidate_get(candidate, "validation_issue_code"),
        flags.get("validation_issue_code"),
        quote_truth.get("quote_validation_status"),
        quote_truth_snapshot.get("quote_validation_status"),
    }
    return {_normalized_upper(value) for value in values if _normalized_text(value)}


def _score_inputs(candidate: Any, flags: dict[str, Any]) -> dict[str, Any]:
    direct = _mapping(_candidate_get(candidate, "score_inputs_used"))
    flagged = _mapping(flags.get("score_inputs_used"))
    merged = dict(flagged)
    merged.update(direct)
    return merged


def _fallback_execution_reasons(candidate: Any, flags: dict[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    quote_sources = _quote_sources(candidate, flags)
    validation_statuses = _quote_validation_statuses(candidate, flags)
    score_inputs = _score_inputs(candidate, flags)

    if any(
        _truthy(_coalesce(_candidate_get(candidate, field), flags.get(field)))
        for field in (
            "fallback_candidate",
            "recovered_fallback",
            "fallback_used",
            "contract_resolution_fallback_used",
        )
    ):
        _append_unique(reasons, FALLBACK_DRIVEN_REASON)

    if _normalized_lower(_candidate_get(candidate, "fallback_state")) in {"recovered_fallback", "fallback_recovered"}:
        _append_unique(reasons, FALLBACK_DRIVEN_REASON)
    if _normalized_lower(flags.get("fallback_state")) in {"recovered_fallback", "fallback_recovered"}:
        _append_unique(reasons, FALLBACK_DRIVEN_REASON)

    if quote_sources.intersection(_FALLBACK_CHAIN_SOURCES):
        _append_unique(reasons, FALLBACK_DRIVEN_REASON)

    rr_source = _normalized_lower(score_inputs.get("rr_source"))
    if rr_source in _FALLBACK_RR_SOURCES:
        _append_unique(reasons, FALLBACK_DRIVEN_REASON)

    if validation_statuses.intersection(_PRICE_MISMATCH_STATUSES):
        _append_unique(reasons, PRICE_MISMATCH_REASON)
    if validation_statuses.intersection(_STALE_QUOTE_STATUSES):
        _append_unique(reasons, STALE_OPTION_LTP_REASON)
    if validation_statuses.intersection(_SUBSCRIPTION_FAILED_STATUSES):
        _append_unique(reasons, SUBSCRIPTION_FAILED_REASON)

    if "subscription_failed" in quote_sources:
        _append_unique(reasons, SUBSCRIPTION_FAILED_REASON)

    for blocker in _candidate_get(candidate, "tradable_reasons_blocking", []) or []:
        text = _normalized_lower(blocker)
        if "fallback" in text:
            _append_unique(reasons, FALLBACK_DRIVEN_REASON)
        if "price_mismatch" in text:
            _append_unique(reasons, PRICE_MISMATCH_REASON)
        if "stale" in text:
            _append_unique(reasons, STALE_OPTION_LTP_REASON)
        if "subscription_failed" in text:
            _append_unique(reasons, SUBSCRIPTION_FAILED_REASON)

    return tuple(reasons)


def classify_executable_truth(
    candidate: Any,
    *,
    data_state: str | None = None,
    fresh_quote_ok: Any = None,
    liquidity_ok: Any = None,
    spread_ok: Any = None,
    data_confidence: float | None = None,
) -> ExecutableTruthDecision:
    flags = _source_flags(candidate)
    reasons: list[str] = []
    context: dict[str, Any] = {}
    quote_sources = _quote_sources(candidate, flags)
    validation_statuses = _quote_validation_statuses(candidate, flags)
    chain_source = sorted(quote_sources)[0] if quote_sources else ""

    for fallback_reason in _fallback_execution_reasons(candidate, flags):
        _append_unique(reasons, fallback_reason)

    execution_block_type = str(flags.get("execution_block_type") or "").strip().lower()
    if execution_block_type == "advisory":
        _append_unique(reasons, _advisory_reason(candidate, flags))

    if _truthy(_coalesce(_candidate_get(candidate, "planning_only"), flags.get("planning_only"))):
        _append_unique(reasons, "planning_only")
    if _truthy(_coalesce(_candidate_get(candidate, "advisory_only"), flags.get("advisory_only"))):
        _append_unique(reasons, "advisory_only")
    if _truthy(_coalesce(_candidate_get(candidate, "debug_candidate"), flags.get("debug_candidate"))):
        _append_unique(reasons, "debug_candidate")

    state = str(_coalesce(data_state, _candidate_get(candidate, "data_state"), flags.get("data_state")) or "").strip().upper()
    if state == "DATA_STALE":
        _append_unique(reasons, "stale_quote")
    elif state == "DATA_INCONSISTENT":
        _append_unique(reasons, "inconsistent_quote")
    elif state == "DATA_MISSING":
        _append_unique(reasons, "missing_quote")

    if fresh_quote_ok is None:
        fresh_quote_ok = _coalesce(_candidate_get(candidate, "fresh_quote_ok"), flags.get("fresh_quote_ok"))
    if fresh_quote_ok is False:
        _append_unique(reasons, "stale_quote")
    if spread_ok is None:
        spread_ok = _coalesce(_candidate_get(candidate, "spread_ok"), flags.get("spread_ok"))
    if spread_ok is False:
        _append_unique(reasons, "unverified_spread")
    if liquidity_ok is None:
        liquidity_ok = _coalesce(_candidate_get(candidate, "liquidity_ok"), flags.get("liquidity_ok"))
    if liquidity_ok is False:
        _append_unique(reasons, "missing_liquidity_validation")

    signal_quality = classify_strategy_signal_quality(candidate)
    context["strategy_signal_quality"] = dict(signal_quality.context or {})
    if not signal_quality.signal_ok:
        _append_unique(reasons, signal_quality.reason_code)
        for signal_reason in signal_quality.reasons:
            _append_unique(reasons, signal_reason)

    freshness = classify_candidate_quote_freshness(candidate)
    context["quote_freshness"] = dict(freshness.context or {})
    if not freshness.freshness_ok:
        _append_unique(reasons, freshness.reason_code)
        for freshness_reason in freshness.reasons:
            _append_unique(reasons, freshness_reason)

    spread_truth = classify_option_spread_truth(candidate)
    context["spread_truth"] = dict(spread_truth.context or {})
    if not spread_truth.spread_ok:
        _append_unique(reasons, spread_truth.reason_code)
        for spread_reason in spread_truth.reasons:
            _append_unique(reasons, spread_reason)

    confidence = _safe_float(_coalesce(data_confidence, _candidate_get(candidate, "data_confidence"), flags.get("data_confidence")))
    min_confidence = float(getattr(cfg, "EXECUTABLE_TRUTH_MIN_DATA_CONFIDENCE", getattr(cfg, "DATA_CONFIDENCE_MIN_EXECUTION", 0.20)) or 0.20)
    if confidence is not None and confidence < min_confidence:
        _append_unique(reasons, "low_data_confidence")

    allowed = not reasons
    context.update(
        {
            "firebreak_code": EXECUTABLE_TRUTH_FIREBREAK_CODE,
            "data_state": state or None,
            "chain_source": chain_source or None,
            "quote_sources": sorted(quote_sources),
            "quote_validation_statuses": sorted(validation_statuses),
            "execution_block_type": execution_block_type or None,
            "data_confidence": confidence,
            "min_data_confidence": min_confidence,
        }
    )
    return ExecutableTruthDecision(
        execution_allowed=allowed,
        reason_code="ok" if allowed else reasons[0],
        reasons=tuple(reasons),
        context=context,
    )