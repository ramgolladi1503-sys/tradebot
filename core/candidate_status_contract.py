from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PRICE_FEASIBLE_STATUS = "price_feasible"
PRICE_NOT_FEASIBLE_STATUS = "price_not_feasible"
PRICE_UNKNOWN_STATUS = "price_unknown"

EXECUTION_ALLOWED_STATUS = "execution_allowed"
EXECUTION_BLOCKED_STATUS = "execution_blocked"
EXECUTION_PERMISSION_UNKNOWN_STATUS = "execution_permission_unknown"

CANDIDATE_STATUS_CONTRACT_VERSION = "edge47.v1"

_PRICE_FEASIBLE_MARKERS = {
    "executable",
    "entry_feasible",
    "price_feasible",
    "priced",
    "valid_entry_price",
}

_PRICE_NOT_FEASIBLE_MARKERS = {
    "price_not_feasible",
    "missing_entry_price",
    "invalid_entry_price",
    "price_mismatch_quote",
    "stale_option_ltp",
    "stale_quote",
    "unverified_spread",
}

_EXECUTION_BLOCKERS = {
    "advisory_only",
    "planning_only",
    "debug_candidate",
    "data_not_live",
    "degraded_data",
    "fallback_driven_data",
    "price_mismatch_quote",
    "stale_option_ltp",
    "subscription_failed_quote",
    "symbol_execution_safety_failed",
    "symbol_feed_unsafe",
    "symbol_subscription_failed",
    "symbol_stale_option_ticks",
    "symbol_option_feed_blocked",
    "stale_quote",
    "missing_liquidity_validation",
    "unverified_spread",
    "low_data_confidence",
    "risk_rejected",
    "candidate_rejected",
    "no_signal",
    "no_candidates_survived",
}


@dataclass(frozen=True)
class CandidateStatusContractDecision:
    price_feasibility_status: str
    execution_permission_status: str
    price_feasible: bool = False
    execution_allowed: bool = False
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


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


def _normal(value: Any) -> str:
    return str(value or "").strip().lower()


def _append_unique(items: list[str], item: str | None) -> None:
    text = str(item or "").strip()
    if text and text not in items:
        items.append(text)


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _explicit_reasons(candidate: Any, flags: dict[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for field in (
        "reason",
        "reason_code",
        "status_reason",
        "reject_reason",
        "block_reason",
        "no_trade_reason",
    ):
        _append_unique(reasons, _candidate_get(candidate, field))
        _append_unique(reasons, flags.get(field))
    for field in (
        "reasons",
        "status_reasons",
        "reject_reasons",
        "block_reasons",
        "blocking_reasons",
        "tradable_reasons_blocking",
        "no_trade_reasons",
    ):
        for item in _iter_values(_candidate_get(candidate, field)):
            _append_unique(reasons, item)
        for item in _iter_values(flags.get(field)):
            _append_unique(reasons, item)
    return tuple(reasons)


def _markers(candidate: Any, flags: dict[str, Any], reasons: tuple[str, ...]) -> set[str]:
    markers = {_normal(reason) for reason in reasons if _normal(reason)}
    for field in (
        "execution_entry_status",
        "execution_feasibility_status",
        "price_feasibility_status",
        "status",
        "readiness",
    ):
        value = _normal(_candidate_get(candidate, field))
        if value:
            markers.add(value)
        flag_value = _normal(flags.get(field))
        if flag_value:
            markers.add(flag_value)
    if _truthy(_candidate_get(candidate, "advisory_only")) or _truthy(flags.get("advisory_only")):
        markers.add("advisory_only")
    if _truthy(_candidate_get(candidate, "planning_only")) or _truthy(flags.get("planning_only")):
        markers.add("planning_only")
    if _truthy(_candidate_get(candidate, "debug_candidate")) or _truthy(flags.get("debug_candidate")):
        markers.add("debug_candidate")
    return markers


def _price_is_feasible(candidate: Any, flags: dict[str, Any], markers: set[str]) -> tuple[str, bool]:
    if markers.intersection(_PRICE_NOT_FEASIBLE_MARKERS):
        return PRICE_NOT_FEASIBLE_STATUS, False
    if markers.intersection(_PRICE_FEASIBLE_MARKERS):
        return PRICE_FEASIBLE_STATUS, True
    if _truthy(_candidate_get(candidate, "price_feasible")) or _truthy(flags.get("price_feasible")):
        return PRICE_FEASIBLE_STATUS, True
    if _candidate_get(candidate, "entry_price") not in (None, "", "None"):
        return PRICE_FEASIBLE_STATUS, True
    return PRICE_UNKNOWN_STATUS, False


def _execution_permission(candidate: Any, flags: dict[str, Any], markers: set[str]) -> tuple[str, bool]:
    if markers.intersection(_EXECUTION_BLOCKERS):
        return EXECUTION_BLOCKED_STATUS, False
    explicit_allowed = _candidate_get(candidate, "execution_allowed")
    if explicit_allowed is None:
        explicit_allowed = flags.get("execution_allowed")
    if explicit_allowed is True:
        return EXECUTION_ALLOWED_STATUS, True
    if explicit_allowed is False:
        return EXECUTION_BLOCKED_STATUS, False
    return EXECUTION_PERMISSION_UNKNOWN_STATUS, False


def classify_candidate_status_contract(candidate: Any) -> CandidateStatusContractDecision:
    """Separate price feasibility from execution permission.

    A priced/feasible entry can still be blocked from execution by advisory,
    debug, freshness, fallback, risk, or symbol-safety evidence. This function is
    read-only and does not call broker adapters or mutate runtime state.
    """
    flags = _source_flags(candidate)
    reasons = _explicit_reasons(candidate, flags)
    markers = _markers(candidate, flags, reasons)
    price_status, price_feasible = _price_is_feasible(candidate, flags, markers)
    permission_status, allowed = _execution_permission(candidate, flags, markers)

    output_reasons: list[str] = []
    for reason in reasons:
        _append_unique(output_reasons, reason)
    if price_status == PRICE_UNKNOWN_STATUS:
        _append_unique(output_reasons, "price_feasibility_unknown")
    if permission_status == EXECUTION_PERMISSION_UNKNOWN_STATUS:
        _append_unique(output_reasons, "execution_permission_unknown")

    return CandidateStatusContractDecision(
        price_feasibility_status=price_status,
        execution_permission_status=permission_status,
        price_feasible=price_feasible,
        execution_allowed=allowed,
        reasons=tuple(output_reasons),
        context={
            "contract_version": CANDIDATE_STATUS_CONTRACT_VERSION,
            "markers": sorted(markers),
            "legacy_execution_entry_status": _candidate_get(candidate, "execution_entry_status"),
            "legacy_execution_feasibility_status": _candidate_get(candidate, "execution_feasibility_status"),
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
    )
