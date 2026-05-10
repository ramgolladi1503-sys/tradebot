from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.data_quality import assess_candidate_data_quality


@dataclass(frozen=True)
class DataRiskGuardResult:
    allowed: bool
    reason_code: str
    reason: str
    data_quality_grade: str
    blockers: list[str] = field(default_factory=list)
    fallback_fields: list[str] = field(default_factory=list)
    lineage: dict[str, str] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "data_risk_allowed": bool(self.allowed),
            "data_risk_reason_code": self.reason_code,
            "data_risk_reason": self.reason,
            "data_quality_grade": self.data_quality_grade,
            "data_truth_blockers": list(self.blockers),
            "fallback_fields": list(self.fallback_fields),
            "data_lineage": dict(self.lineage),
        }


def _candidate_snapshot(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        return dict(candidate)
    if hasattr(candidate, "__dict__"):
        return dict(candidate.__dict__)
    return {}


def evaluate_data_risk(candidate: Any) -> DataRiskGuardResult:
    """Convert candidate data truth into an explicit risk decision.

    Bad data is risk. This guard is reusable by risk engine, allocation, review
    queue, and tests without duplicating blocker interpretation.
    """
    result = assess_candidate_data_quality(_candidate_snapshot(candidate))
    if result.execution_truth_allowed:
        return DataRiskGuardResult(
            allowed=True,
            reason_code="data_risk_ok",
            reason="data truth allows execution",
            data_quality_grade=result.data_quality_grade,
            blockers=list(result.execution_truth_blockers),
            fallback_fields=list(result.fallback_fields),
            lineage=dict(result.lineage),
        )

    primary = result.execution_truth_blockers[0] if result.execution_truth_blockers else "data_truth_blocked"
    reason_code = f"data_risk_block:{primary}"
    reason = f"data risk blocked execution: grade={result.data_quality_grade}; blockers={','.join(result.execution_truth_blockers) or 'unknown'}"
    return DataRiskGuardResult(
        allowed=False,
        reason_code=reason_code,
        reason=reason,
        data_quality_grade=result.data_quality_grade,
        blockers=list(result.execution_truth_blockers),
        fallback_fields=list(result.fallback_fields),
        lineage=dict(result.lineage),
    )
