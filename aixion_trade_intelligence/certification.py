from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


REQUIRED_STRATEGY_GATES = (
    "DATA_VALID",
    "POINT_IN_TIME_VALID",
    "CAUSALITY_VALID",
    "NEGATIVE_CONTROLS_PASS",
    "OVERFITTING_RISK_ACCEPTABLE",
    "INCREMENTAL_EDGE_POSITIVE",
    "COST_ADJUSTED_EDGE_POSITIVE",
    "FILL_REALISM_VALID",
    "CAPACITY_ACCEPTABLE",
    "HOLDOUT_POSITIVE",
    "DRIFT_STABLE",
    "RISK_OF_RUIN_ACCEPTABLE",
    "LIVE_SHADOW_CONSISTENT",
)


@dataclass(frozen=True)
class CertificationGateResult:
    gate_id: str
    status: GateStatus
    reason: str
    evidence_refs: tuple[str, ...]
    calculation_version: str

    def __post_init__(self) -> None:
        if self.gate_id not in REQUIRED_STRATEGY_GATES:
            raise ValueError(f"unsupported_gate={self.gate_id}")
        if not self.reason.strip():
            raise ValueError("missing_gate_reason")
        if not self.calculation_version.strip():
            raise ValueError("missing_calculation_version")
        if self.status in {GateStatus.PASS, GateStatus.FAIL} and not self.evidence_refs:
            raise ValueError("evaluated_gate_requires_evidence")
        if any(not str(reference).strip() for reference in self.evidence_refs):
            raise ValueError("empty_evidence_reference")


@dataclass(frozen=True)
class CertificationDecision:
    verdict: str
    ready_for_human_review: bool
    failed_gates: tuple[str, ...]
    unevaluated_gates: tuple[str, ...]
    passed_gates: tuple[str, ...]
    gate_results: tuple[CertificationGateResult, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "ready_for_human_review": self.ready_for_human_review,
            "failed_gates": list(self.failed_gates),
            "unevaluated_gates": list(self.unevaluated_gates),
            "passed_gates": list(self.passed_gates),
            "gate_results": [
                {
                    "gate_id": result.gate_id,
                    "status": result.status.value,
                    "reason": result.reason,
                    "evidence_refs": list(result.evidence_refs),
                    "calculation_version": result.calculation_version,
                }
                for result in self.gate_results
            ],
        }


def certify_strategy(
    results: Iterable[CertificationGateResult],
) -> CertificationDecision:
    provided = tuple(results)
    by_gate: dict[str, CertificationGateResult] = {}
    for result in provided:
        if result.gate_id in by_gate:
            raise ValueError(f"duplicate_gate={result.gate_id}")
        by_gate[result.gate_id] = result
    normalized: list[CertificationGateResult] = []
    for gate_id in REQUIRED_STRATEGY_GATES:
        normalized.append(
            by_gate.get(
                gate_id,
                CertificationGateResult(
                    gate_id=gate_id,
                    status=GateStatus.NOT_EVALUATED,
                    reason="GATE_RESULT_NOT_PROVIDED",
                    evidence_refs=(),
                    calculation_version="not-evaluated",
                ),
            )
        )
    failed = tuple(result.gate_id for result in normalized if result.status is GateStatus.FAIL)
    unevaluated = tuple(
        result.gate_id
        for result in normalized
        if result.status is GateStatus.NOT_EVALUATED
    )
    passed = tuple(result.gate_id for result in normalized if result.status is GateStatus.PASS)
    if failed:
        verdict = f"REJECTED_{failed[0]}"
        ready = False
    elif unevaluated:
        verdict = "INSUFFICIENT_EVIDENCE"
        ready = False
    else:
        verdict = "READY_FOR_HUMAN_PROMOTION_REVIEW"
        ready = True
    return CertificationDecision(
        verdict=verdict,
        ready_for_human_review=ready,
        failed_gates=failed,
        unevaluated_gates=unevaluated,
        passed_gates=passed,
        gate_results=tuple(normalized),
    )
