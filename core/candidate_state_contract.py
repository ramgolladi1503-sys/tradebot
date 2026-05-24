from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

EXECUTABLE_STATE = "executable"
RANKABLE_STATE = "rankable"
ADVISORY_STATE = "advisory"
DEBUG_ONLY_STATE = "debug_only"
SOFT_REJECT_STATE = "soft_reject"
HARD_REJECT_STATE = "hard_reject"

CANDIDATE_STATE_CONTRACT_VERSION = "edge46.v1"

_HARD_REJECT_MARKERS = {
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
    "inconsistent_quote",
    "missing_quote",
    "low_data_confidence",
    "missing_liquidity_validation",
    "unverified_spread",
    "candidate_rejected",
    "risk_rejected",
    "token_missing",
    "invalid_token",
}

_SOFT_REJECT_MARKERS = {
    "no_signal",
    "no_strategy_signal",
    "weak_strategy_signal",
    "conflicting_strategy_signal",
    "no_candidates_survived",
    "no_rankable_candidates",
    "strategy_signal_quality_failed",
    "missing_strategy_family",
    "missing_signal_direction",
    "candidate_suppressed",
    "not_selected",
}

_ADVISORY_MARKERS = {
    "advisory_only",
    "planning_only",
    "data_not_live",
    "degraded_data",
    "execution_block_type:advisory",
}

_DEBUG_MARKERS = {
    "debug_candidate",
    "debug_only",
    "diagnostic_only",
    "trace_only",
}

_RANKABLE_MARKERS = {
    "rankable",
    "eligible_for_ranking",
}

_EXECUTABLE_MARKERS = {
    "execution_allowed",
    "selected_for_execution",
    "execution_entry_status:executable",
    "candidate_class:executable",
}


@dataclass(frozen=True)
class CandidateStateDecision:
    state: str
    is_hard_reject: bool = False
    is_soft_reject: bool = False
    is_advisory: bool = False
    is_debug_only: bool = False
    is_rankable: bool = False
    is_executable: bool = False
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    return candidate.get(field, default) if isinstance(candidate, dict) else getattr(candidate, field, default)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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


def _append_unique(items: list[str], item: str | None) -> None:
    text = str(item or "").strip()
    if text and text not in items:
        items.append(text)


def _normal(value: Any) -> str:
    return str(value or "").strip().lower()


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

    for field in ("state", "candidate_state", "status", "readiness", "rankability"):
        value = _normal(_candidate_get(candidate, field))
        if value:
            markers.add(value)
        flag_value = _normal(flags.get(field))
        if flag_value:
            markers.add(flag_value)

    candidate_class = _normal(_candidate_get(candidate, "candidate_class"))
    if candidate_class:
        markers.add(f"candidate_class:{candidate_class}")
    execution_status = _normal(_candidate_get(candidate, "execution_entry_status"))
    if execution_status:
        markers.add(f"execution_entry_status:{execution_status}")
    execution_block_type = _normal(flags.get("execution_block_type") or _candidate_get(candidate, "execution_block_type"))
    if execution_block_type:
        markers.add(f"execution_block_type:{execution_block_type}")

    bool_fields = {
        "debug_candidate": "debug_candidate",
        "debug_only": "debug_only",
        "diagnostic_only": "diagnostic_only",
        "planning_only": "planning_only",
        "advisory_only": "advisory_only",
        "rankable": "rankable",
        "eligible_for_ranking": "eligible_for_ranking",
        "execution_allowed": "execution_allowed",
        "selected_for_execution": "selected_for_execution",
        "candidate_rejected": "candidate_rejected",
        "risk_rejected": "risk_rejected",
    }
    for field, marker in bool_fields.items():
        if _truthy(_candidate_get(candidate, field)) or _truthy(flags.get(field)):
            markers.add(marker)
    return markers


def _matched(markers: set[str], expected: set[str]) -> tuple[str, ...]:
    return tuple(sorted(marker for marker in markers if marker in expected))


def classify_candidate_state(candidate: Any) -> CandidateStateDecision:
    """Separate candidate state vocabulary without broker/runtime side effects.

    Precedence is intentionally fail-closed for safety-like states:
    hard reject > soft reject > debug-only > advisory > executable > rankable.
    """
    flags = _source_flags(candidate)
    reasons = _explicit_reasons(candidate, flags)
    markers = _markers(candidate, flags, reasons)

    hard_reasons = _matched(markers, _HARD_REJECT_MARKERS)
    soft_reasons = _matched(markers, _SOFT_REJECT_MARKERS)
    debug_reasons = _matched(markers, _DEBUG_MARKERS)
    advisory_reasons = _matched(markers, _ADVISORY_MARKERS)
    executable_reasons = _matched(markers, _EXECUTABLE_MARKERS)
    rankable_reasons = _matched(markers, _RANKABLE_MARKERS)

    if hard_reasons:
        state = HARD_REJECT_STATE
    elif soft_reasons:
        state = SOFT_REJECT_STATE
    elif debug_reasons:
        state = DEBUG_ONLY_STATE
    elif advisory_reasons:
        state = ADVISORY_STATE
    elif executable_reasons:
        state = EXECUTABLE_STATE
    elif rankable_reasons:
        state = RANKABLE_STATE
    else:
        state = SOFT_REJECT_STATE
        soft_reasons = ("unclassified_candidate_state",)

    return CandidateStateDecision(
        state=state,
        is_hard_reject=state == HARD_REJECT_STATE,
        is_soft_reject=state == SOFT_REJECT_STATE,
        is_advisory=state == ADVISORY_STATE,
        is_debug_only=state == DEBUG_ONLY_STATE,
        is_rankable=state == RANKABLE_STATE,
        is_executable=state == EXECUTABLE_STATE,
        reasons=hard_reasons or soft_reasons or debug_reasons or advisory_reasons or executable_reasons or rankable_reasons,
        context={
            "contract_version": CANDIDATE_STATE_CONTRACT_VERSION,
            "markers": sorted(markers),
            "explicit_reasons": reasons,
            "is_order_action": False,
            "broker_api_called": False,
        },
    )
