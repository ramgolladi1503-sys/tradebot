from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg

EXECUTABLE_TRUTH_FIREBREAK_CODE = "EXECUTABLE_TRUTH_FIREBREAK_FAILED"
FALLBACK_DRIVEN_REASON = "fallback_driven_data"
DEGRADED_DATA_REASON = "degraded_data"
DATA_NOT_LIVE_REASON = "data_not_live"

_FALLBACK_CHAIN_SOURCES = {
    "synthetic_chain",
    "close_fallback",
    "quote_fallback",
    "recovered_fallback",
    "fallback_close",
    "fallback_last_atm",
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
    chain_source = str(
        _coalesce(
            _candidate_get(candidate, "chain_source"),
            flags.get("chain_source"),
            _candidate_get(candidate, "price_source"),
            flags.get("quote_source"),
        )
        or ""
    ).strip().lower()

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
    if chain_source in _FALLBACK_CHAIN_SOURCES:
        _append_unique(reasons, FALLBACK_DRIVEN_REASON)

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

    confidence = _safe_float(_coalesce(data_confidence, _candidate_get(candidate, "data_confidence"), flags.get("data_confidence")))
    min_confidence = float(getattr(cfg, "EXECUTABLE_TRUTH_MIN_DATA_CONFIDENCE", getattr(cfg, "DATA_CONFIDENCE_MIN_EXECUTION", 0.20)) or 0.20)
    if confidence is not None and confidence < min_confidence:
        _append_unique(reasons, "low_data_confidence")

    allowed = not reasons
    return ExecutableTruthDecision(
        execution_allowed=allowed,
        reason_code="ok" if allowed else reasons[0],
        reasons=tuple(reasons),
        context={
            "firebreak_code": EXECUTABLE_TRUTH_FIREBREAK_CODE,
            "data_state": state or None,
            "chain_source": chain_source or None,
            "execution_block_type": execution_block_type or None,
            "data_confidence": confidence,
            "min_data_confidence": min_confidence,
        },
    )
