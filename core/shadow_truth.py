from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.data_quality import assess_candidate_data_quality


@dataclass(frozen=True)
class ShadowTruthDecision:
    ref: str
    symbol: str | None
    current_selected_or_executable: bool
    current_execution_allowed: bool
    current_selected_for_execution: bool
    shadow_execution_truth_allowed: bool
    shadow_data_quality_grade: str
    shadow_blockers: list[str] = field(default_factory=list)
    shadow_fallback_fields: list[str] = field(default_factory=list)
    shadow_lineage: dict[str, str] = field(default_factory=dict)
    drift_type: str = "NO_DRIFT"
    drift_severity: str = "INFO"
    recommended_action: str = "observe"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "symbol": self.symbol,
            "current_selected_or_executable": bool(self.current_selected_or_executable),
            "current_execution_allowed": bool(self.current_execution_allowed),
            "current_selected_for_execution": bool(self.current_selected_for_execution),
            "shadow_execution_truth_allowed": bool(self.shadow_execution_truth_allowed),
            "shadow_data_quality_grade": self.shadow_data_quality_grade,
            "shadow_blockers": list(self.shadow_blockers),
            "shadow_fallback_fields": list(self.shadow_fallback_fields),
            "shadow_lineage": dict(self.shadow_lineage),
            "drift_type": self.drift_type,
            "drift_severity": self.drift_severity,
            "recommended_action": self.recommended_action,
        }


def _candidate_ref(candidate: Mapping[str, Any], index: int) -> str:
    return str(
        candidate.get("trade_id")
        or candidate.get("candidate_id")
        or candidate.get("trade_key")
        or candidate.get("instrument_id")
        or candidate.get("tradingsymbol")
        or candidate.get("symbol")
        or f"candidate-{index}"
    )


def _current_selected_or_executable(candidate: Mapping[str, Any]) -> bool:
    permission = str(candidate.get("permission") or "").strip().upper()
    final_action = str(candidate.get("final_action") or "").strip().upper()
    execution_status = str(candidate.get("execution_status") or "").strip().lower()
    return bool(
        candidate.get("selected_for_execution")
        or candidate.get("is_executable")
        or candidate.get("eligible_for_execution")
        or (permission == "EXECUTE" and final_action == "EXECUTE")
        or execution_status == "executable"
    )


def _classify_drift(candidate: Mapping[str, Any], *, shadow_allowed: bool, selected_or_executable: bool) -> tuple[str, str, str]:
    current_execution_allowed = bool(candidate.get("execution_allowed", False))
    current_selected = bool(candidate.get("selected_for_execution", False))

    if selected_or_executable and not shadow_allowed:
        return "CURRENT_ALLOWS_SHADOW_BLOCKS", "CRITICAL", "investigate_before_execution"
    if current_execution_allowed and not shadow_allowed:
        return "EXECUTION_ALLOWED_SHADOW_BLOCKS", "HIGH", "downgrade_or_block_before_wiring"
    if current_selected and not shadow_allowed:
        return "SELECTED_SHADOW_BLOCKS", "CRITICAL", "remove_from_execution_selection"
    if (not selected_or_executable) and shadow_allowed:
        return "CURRENT_BLOCKS_SHADOW_ALLOWS", "LOW", "observe_possible_false_negative"
    return "NO_DRIFT", "INFO", "observe"


def shadow_evaluate_candidate(candidate: Mapping[str, Any], *, index: int = 0) -> ShadowTruthDecision:
    row = dict(candidate or {})
    result = assess_candidate_data_quality(row)
    selected_or_executable = _current_selected_or_executable(row)
    drift_type, drift_severity, action = _classify_drift(
        row,
        shadow_allowed=result.execution_truth_allowed,
        selected_or_executable=selected_or_executable,
    )
    return ShadowTruthDecision(
        ref=_candidate_ref(row, index),
        symbol=row.get("symbol") or row.get("underlying"),
        current_selected_or_executable=selected_or_executable,
        current_execution_allowed=bool(row.get("execution_allowed", False)),
        current_selected_for_execution=bool(row.get("selected_for_execution", False)),
        shadow_execution_truth_allowed=bool(result.execution_truth_allowed),
        shadow_data_quality_grade=result.data_quality_grade,
        shadow_blockers=list(result.execution_truth_blockers),
        shadow_fallback_fields=list(result.fallback_fields),
        shadow_lineage=dict(result.lineage),
        drift_type=drift_type,
        drift_severity=drift_severity,
        recommended_action=action,
    )


def shadow_evaluate_candidates(candidates: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    decisions = [shadow_evaluate_candidate(candidate, index=index) for index, candidate in enumerate(list(candidates or []))]
    severity_counts: dict[str, int] = {}
    drift_counts: dict[str, int] = {}
    for decision in decisions:
        severity_counts[decision.drift_severity] = severity_counts.get(decision.drift_severity, 0) + 1
        drift_counts[decision.drift_type] = drift_counts.get(decision.drift_type, 0) + 1
    critical = [decision.to_dict() for decision in decisions if decision.drift_severity == "CRITICAL"]
    high = [decision.to_dict() for decision in decisions if decision.drift_severity == "HIGH"]
    return {
        "mode": "SHADOW_ONLY",
        "behavior_changed": False,
        "total_candidates": len(decisions),
        "severity_counts": severity_counts,
        "drift_counts": drift_counts,
        "critical_drifts": critical,
        "high_drifts": high,
        "decisions": [decision.to_dict() for decision in decisions],
    }
