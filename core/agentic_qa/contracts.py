from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ControlStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"
    ERROR = "ERROR"


class AuditVerdict(str, Enum):
    CONTROL_PLANE_CERTIFIED = "CONTROL_PLANE_CERTIFIED"
    CONDITIONALLY_CERTIFIED = "CONDITIONALLY_CERTIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"
    AUDITOR_ERROR = "AUDITOR_ERROR"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class EvidenceRef:
    artifact: str
    pointer: str = ""
    sha256: str | None = None


@dataclass(frozen=True)
class ControlDefinition:
    control_id: str
    domain: str
    title: str
    description: str
    severity: Severity
    hard_fail: bool
    rule: str
    key: str
    expected: Any = True


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    domain: str
    title: str
    status: ControlStatus
    score: int
    reason_code: str
    summary: str
    severity: Severity
    hard_fail: bool
    evidence_refs: tuple[EvidenceRef, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is ControlStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["severity"] = self.severity.value
        payload["evidence_refs"] = [asdict(item) for item in self.evidence_refs]
        return payload


@dataclass(frozen=True)
class AuditReport:
    schema_version: str
    run_id: str
    trace_id: str
    policy_version: str
    repository_commit: str
    bundle_digest: str
    verdict: AuditVerdict
    controls: tuple[ControlResult, ...]
    deterministic_score: float
    passed: int
    failed: int
    insufficient: int
    errors: int
    hard_failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    agent_review: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "policy_version": self.policy_version,
            "repository_commit": self.repository_commit,
            "bundle_digest": self.bundle_digest,
            "verdict": self.verdict.value,
            "deterministic_score": self.deterministic_score,
            "summary": {
                "total": len(self.controls),
                "passed": self.passed,
                "failed": self.failed,
                "insufficient": self.insufficient,
                "errors": self.errors,
            },
            "hard_failures": list(self.hard_failures),
            "warnings": list(self.warnings),
            "controls": [item.to_dict() for item in self.controls],
            "agent_review": self.agent_review,
        }
