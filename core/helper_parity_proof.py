from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from core.orchestrator_truth import (
    candidate_origin,
    is_reportable_executable_candidate,
    is_synthetic_candidate,
)


def _legacy_trade_attr(trade: Any, name: str, default: Any = None) -> Any:
    if isinstance(trade, dict):
        return trade.get(name, default)
    return getattr(trade, name, default)


def legacy_candidate_origin(candidate: Any) -> str:
    origin_value = _legacy_trade_attr(candidate, "candidate_origin", None)
    if isinstance(origin_value, dict):
        return str(
            origin_value.get("candidate_origin")
            or origin_value.get("origin")
            or origin_value.get("source")
            or ""
        ).strip().lower()
    return str(origin_value or "").strip().lower()


def legacy_is_synthetic_candidate(candidate: Any) -> bool:
    if candidate is None:
        return False
    origin = legacy_candidate_origin(candidate)
    source_flags = _legacy_trade_attr(candidate, "source_flags", None)
    if not isinstance(source_flags, dict):
        source_flags = {}
    source_origin = str(
        source_flags.get("candidate_origin")
        or source_flags.get("origin")
        or source_flags.get("source")
        or ""
    ).strip().lower()
    soft_reason = str(source_flags.get("soft_reject_reason") or "").strip().lower()
    candidate_type = str(_legacy_trade_attr(candidate, "candidate_type", "") or "").strip().lower()
    strategy_family = str(_legacy_trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    score_origin = str(_legacy_trade_attr(candidate, "score_origin", "") or "").strip().lower()
    trade_id = str(_legacy_trade_attr(candidate, "trade_id", "") or "").strip()
    permission = str(_legacy_trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(_legacy_trade_attr(candidate, "final_action", "") or "").strip().upper()
    execution_status = str(_legacy_trade_attr(candidate, "execution_status", "") or "").strip().lower()
    advisory_lifecycle = permission == "ADVISORY_ONLY" or final_action == "ADVISORY_ONLY" or execution_status == "advisory_only"
    if candidate_type == "fallback_market_candidate":
        return True
    if trade_id.startswith(("softrej_", "tbsoft_")):
        return True
    if strategy_family == "synthetic_advisory":
        return True
    if score_origin == "soft_reject_seed":
        return True
    synthetic_origins = {
        "pre_builder_gate", "invalid_snapshot", "fallback", "fallback_min_breadth",
        "softened_builder_path", "softened", "planning_only",
    }
    if origin in synthetic_origins or source_origin in synthetic_origins:
        return True
    if bool(source_flags.get("recoverable_soft_reject")) or soft_reason:
        return True
    if advisory_lifecycle and (
        candidate_type.startswith("fallback")
        or origin in synthetic_origins
        or source_origin in synthetic_origins
        or trade_id.startswith(("softrej_", "tbsoft_"))
    ):
        return True
    return False


def legacy_is_reportable_executable_candidate(candidate: Any, *, allow_status_fallback: bool = True) -> bool:
    if candidate is None or legacy_is_synthetic_candidate(candidate):
        return False
    trade_id = str(_legacy_trade_attr(candidate, "trade_id", "") or "").strip().lower()
    if trade_id.startswith(("softrej_", "tbsoft_")):
        return False
    strategy_family = str(_legacy_trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    if strategy_family == "synthetic_advisory":
        return False
    candidate_status = str(_legacy_trade_attr(candidate, "candidate_status", "") or "").strip().lower()
    execution_status = str(_legacy_trade_attr(candidate, "execution_status", "") or "").strip().lower()
    entry_status = str(_legacy_trade_attr(candidate, "execution_entry_status", "") or "").strip().lower()
    permission = str(_legacy_trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(_legacy_trade_attr(candidate, "final_action", "") or "").strip().upper()
    readiness = str(_legacy_trade_attr(candidate, "readiness", "") or "").strip().upper()
    if bool(_legacy_trade_attr(candidate, "execution_truth_blocked", False)) or bool(_legacy_trade_attr(candidate, "execution_truth_blockers", None)):
        return False
    if candidate_status in {"advisory_only", "blocked", "blocked_contract"}:
        return False
    status_derived = (
        allow_status_fallback
        and execution_status in {"", "none", "null"}
        and entry_status == "executable"
        and bool(_legacy_trade_attr(candidate, "execution_allowed", False))
        and candidate_status not in {"advisory_only", "blocked", "blocked_contract"}
    )
    if execution_status != "executable" and not status_derived:
        return False
    if entry_status != "executable":
        return False
    if permission in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"} or final_action in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"} or readiness in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCKED"}:
        return False
    if not bool(_legacy_trade_attr(candidate, "execution_allowed", False)):
        return False
    eligible = _legacy_trade_attr(candidate, "eligible_for_execution", None)
    if eligible is None:
        eligible = _legacy_trade_attr(candidate, "execution_allowed", False)
    if not bool(eligible):
        return False
    if bool(_legacy_trade_attr(candidate, "execution_blocked", False)):
        return False
    if bool(_legacy_trade_attr(candidate, "hard_blockers", None)) or bool(_legacy_trade_attr(candidate, "blockers", None)):
        return False
    if bool(_legacy_trade_attr(candidate, "unresolved_contract", False)):
        return False
    return _legacy_trade_attr(candidate, "execution_entry", None) not in (None, "", "None")


@dataclass(frozen=True)
class ParityMismatch:
    index: int
    helper: str
    legacy: Any
    canonical: Any


def prove_helper_parity(candidates: Iterable[Any]) -> tuple[ParityMismatch, ...]:
    mismatches: list[ParityMismatch] = []
    helpers: tuple[tuple[str, Callable[[Any], Any], Callable[[Any], Any]], ...] = (
        ("candidate_origin", legacy_candidate_origin, candidate_origin),
        ("is_synthetic_candidate", legacy_is_synthetic_candidate, is_synthetic_candidate),
        ("is_reportable_executable_candidate", legacy_is_reportable_executable_candidate, is_reportable_executable_candidate),
    )
    for index, candidate in enumerate(candidates):
        for name, legacy, canonical in helpers:
            old = legacy(candidate)
            new = canonical(candidate)
            if old != new:
                mismatches.append(ParityMismatch(index=index, helper=name, legacy=old, canonical=new))
    return tuple(mismatches)


__all__ = [
    "ParityMismatch", "legacy_candidate_origin", "legacy_is_synthetic_candidate",
    "legacy_is_reportable_executable_candidate", "prove_helper_parity",
]
