from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CandidateRowClassification:
    row_class: str
    row_class_reason: str | None
    operator_status: str
    is_executable: bool
    is_near_executable: bool
    is_advisory: bool
    is_debug: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_class": self.row_class,
            "row_class_reason": self.row_class_reason,
            "operator_status": self.operator_status,
            "is_executable": bool(self.is_executable),
            "is_near_executable": bool(self.is_near_executable),
            "is_advisory": bool(self.is_advisory),
            "is_debug": bool(self.is_debug),
        }


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _bool(value: Any) -> bool:
    return bool(value is True)


def classify_candidate_row(
    *,
    row: Mapping[str, Any] | None,
    phase2_state: str | None = None,
    cycle_primary_reason: str | None = None,
) -> CandidateRowClassification:
    """Classify an operator-facing row without mutating decisions.

    This is evidence-only: it does not change ranking, Phase2 state, or any gate.
    """
    r = _as_mapping(row)
    state = _upper(phase2_state)
    cycle_reason = _lower(cycle_primary_reason)

    # Hard safety constraints: never treat fallback/synthetic rows as executable.
    source_flags = r.get("source_flags") if isinstance(r.get("source_flags"), dict) else {}
    recovered_fallback = bool(source_flags.get("recovered_fallback")) if isinstance(source_flags, dict) else False
    fallbackish = bool(r.get("synthetic_candidate")) or bool(r.get("forced_fallback_execution")) or recovered_fallback
    quote_source = _lower(r.get("quote_source"))
    if "fallback" in quote_source:
        fallbackish = True

    hard_blockers = {_upper(v) for v in (r.get("hard_blockers") or []) if _upper(v)}
    blockers = {_upper(v) for v in (r.get("blockers") or []) if _upper(v)} | hard_blockers
    execution_ok = r.get("execution_ok") is True
    candidate_status = _lower(r.get("candidate_status"))
    execution_status = _lower(r.get("execution_status"))
    permission = _upper(r.get("permission"))
    final_action = _upper(r.get("final_action"))

    # Market closed: global cycle truth, not row truth.
    if cycle_reason in {"market_closed", "market_closed_no_trade"}:
        return CandidateRowClassification(
            row_class="MARKET_CLOSED_NO_TRADE",
            row_class_reason="market_closed",
            operator_status="MARKET_CLOSED",
            is_executable=False,
            is_near_executable=False,
            is_advisory=False,
            is_debug=True,
        )

    # Debug-rejected: explicit hard blockers.
    if "FEED_STALE" in blockers:
        return CandidateRowClassification(
            row_class="DEBUG_REJECTED",
            row_class_reason="feed_stale",
            operator_status="BLOCKED_FEED_STALE",
            is_executable=False,
            is_near_executable=False,
            is_advisory=False,
            is_debug=True,
        )
    if "UNRESOLVED_CONTRACT" in blockers:
        return CandidateRowClassification(
            row_class="DEBUG_REJECTED",
            row_class_reason="unresolved_contract",
            operator_status="BLOCKED_UNRESOLVED_CONTRACT",
            is_executable=False,
            is_near_executable=False,
            is_advisory=False,
            is_debug=True,
        )

    # Executable: selected ENTER/HOLD/REPLACE only, execution_ok must be true, and never fallbackish.
    if state in {"ENTER", "REPLACE", "HOLD"} and execution_ok and not fallbackish:
        return CandidateRowClassification(
            row_class="EXECUTABLE",
            row_class_reason="phase2_selected",
            operator_status="EXECUTABLE",
            is_executable=True,
            is_near_executable=False,
            is_advisory=False,
            is_debug=False,
        )

    # Near executable: real row but blocked by one actionable reason (queue-only, watchlist).
    if candidate_status in {"near_executable"} or execution_status in {"queue_only"} or permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY":
        return CandidateRowClassification(
            row_class="NEAR_EXECUTABLE",
            row_class_reason="queue_only_or_near",
            operator_status="NEAR_EXECUTABLE",
            is_executable=False,
            is_near_executable=True,
            is_advisory=False,
            is_debug=False,
        )

    # Advisory: watchlist / non-executable (including fallbackish rows).
    if fallbackish:
        return CandidateRowClassification(
            row_class="ADVISORY",
            row_class_reason="fallback_or_recovered_fallback",
            operator_status="ADVISORY_FALLBACK_BLOCKED",
            is_executable=False,
            is_near_executable=False,
            is_advisory=True,
            is_debug=False,
        )

    if state == "WATCHLIST" or candidate_status in {"advisory_only", "watchlist"}:
        return CandidateRowClassification(
            row_class="ADVISORY",
            row_class_reason="watchlist",
            operator_status="ADVISORY",
            is_executable=False,
            is_near_executable=False,
            is_advisory=True,
            is_debug=False,
        )

    return CandidateRowClassification(
        row_class="DEBUG_REJECTED",
        row_class_reason="unclassified",
        operator_status="DEBUG_REJECTED",
        is_executable=False,
        is_near_executable=False,
        is_advisory=False,
        is_debug=True,
    )


__all__ = ["CandidateRowClassification", "classify_candidate_row"]

