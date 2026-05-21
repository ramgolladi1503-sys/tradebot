from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    BLOCKER = "BLOCKER"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ForensicEvent:
    event: str
    run_id: str
    boot_epoch: float
    ts_epoch: float
    source: str
    writer: str
    schema_version: int
    action_evidence: bool
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceLoadResult:
    profile: str
    events_path: Path
    latest_path: Path
    events: tuple[ForensicEvent, ...]
    selected_run_id: str
    selected_boot_epoch: float | None
    validation_errors: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.validation_errors


@dataclass(frozen=True)
class FlowContract:
    profile: str
    expected_events: tuple[str, ...]
    terminal_success_events: tuple[str, ...]
    forbidden_events: tuple[str, ...]
    readonly_required: bool = True


@dataclass(frozen=True)
class ForensicsFinding:
    severity: Severity
    code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        return payload


@dataclass(frozen=True)
class ForensicsReport:
    profile: str
    evidence_valid: bool
    selected_run_id: str
    last_confirmed_event: str | None
    first_missing_event: str | None
    findings: tuple[ForensicsFinding, ...]
    killed_hypotheses: tuple[str, ...]
    next_diagnostic_scope: str
    forbidden_distractions: tuple[str, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "evidence_valid": self.evidence_valid,
            "selected_run_id": self.selected_run_id,
            "last_confirmed_event": self.last_confirmed_event,
            "first_missing_event": self.first_missing_event,
            "findings": [finding.to_dict() for finding in self.findings],
            "killed_hypotheses": list(self.killed_hypotheses),
            "next_diagnostic_scope": self.next_diagnostic_scope,
            "forbidden_distractions": list(self.forbidden_distractions),
            "is_order_action": False,
        }
