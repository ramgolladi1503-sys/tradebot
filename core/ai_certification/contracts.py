from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNEVALUATED = "UNEVALUATED"
    ERROR = "ERROR"


class EvidenceCertification(str, Enum):
    CERTIFIED = "CERTIFIED"
    CONDITIONALLY_CERTIFIED = "CONDITIONALLY_CERTIFIED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AGENT_ERROR = "AGENT_ERROR"


class StrategyVerdict(str, Enum):
    STRUCTURAL_EDGE_SUPPORTED = "STRUCTURAL_EDGE_SUPPORTED"
    CONDITIONALLY_SUPPORTED = "CONDITIONALLY_SUPPORTED"
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    NO_STRUCTURAL_EDGE = "NO_STRUCTURAL_EDGE"
    INVALID_DUE_TO_DATA = "INVALID_DUE_TO_DATA"
    INVALID_DUE_TO_LEAKAGE = "INVALID_DUE_TO_LEAKAGE"
    WITHHELD = "WITHHELD"


@dataclass(frozen=True)
class EvidenceRef:
    artifact: str
    pointer: str = ""
    sha256: str | None = None


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: GateStatus
    reason_code: str
    summary: str
    mandatory: bool = True
    evidence_refs: tuple[EvidenceRef, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is GateStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["evidence_refs"] = [asdict(ref) for ref in self.evidence_refs]
        return payload


@dataclass(frozen=True)
class CertificationReport:
    schema_version: str
    run_id: str
    strategy_id: str
    evidence_certification: EvidenceCertification
    strategy_verdict: StrategyVerdict
    policy_version: str
    repository_commit: str
    bundle_digest: str
    trace_id: str
    gates: tuple[GateResult, ...]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "evidence_certification": self.evidence_certification.value,
            "strategy_verdict": self.strategy_verdict.value,
            "policy_version": self.policy_version,
            "repository_commit": self.repository_commit,
            "bundle_digest": self.bundle_digest,
            "trace_id": self.trace_id,
            "gates": {gate.gate: gate.to_dict() for gate in self.gates},
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "knowledge_refs": list(self.knowledge_refs),
        }
