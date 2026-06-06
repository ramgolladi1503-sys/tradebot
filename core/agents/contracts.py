from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


AGENT_CONTRACT_SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentEvidenceRef:
    source_path: str
    line_number: int | None = None
    event: str | None = None
    ts_epoch: float | None = None
    ts_ist: str | None = None
    excerpt: str = ""
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value not in (None, {}, [], ())}


@dataclass(frozen=True)
class AgentFinding:
    code: str
    severity: str
    layer: str
    message: str
    confidence: str
    first_seen_ts_epoch: float | None = None
    evidence_refs: tuple[AgentEvidenceRef, ...] = ()
    recommended_action: str = ""
    files_likely_involved: tuple[str, ...] = ()
    tests_needed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = [ref.to_dict() for ref in self.evidence_refs]
        return {key: value for key, value in payload.items() if value not in (None, {}, [], ())}


@dataclass(frozen=True)
class AgentReport:
    schema_version: int
    agent_name: str
    generated_at: str
    read_only: bool
    append: bool
    is_order_action: bool  # is_order_action=false
    broker_api_called: bool  # broker_api_called=false
    live_order_allowed: bool
    no_order_action: bool
    verdict: str
    confidence: str
    first_failing_event: str | None
    findings: tuple[AgentFinding, ...] = ()
    not_root_cause: tuple[str, ...] = ()
    next_fix_recommendation: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["findings"] = [item.to_dict() for item in self.findings]
        payload["metrics"] = dict(self.metrics)
        return {key: value for key, value in payload.items() if value not in (None, {}, [], ())}


@dataclass(frozen=True)
class CommandCenterReport:
    schema_version: int
    generated_at: str
    analyzed_paths: tuple[str, ...]
    agents: tuple[AgentReport, ...]
    first_blocker_layer: str | None
    root_cause_summary: str
    next_pr_recommendation: str
    safety_summary: dict[str, Any]
    metrics_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["agents"] = [agent.to_dict() for agent in self.agents]
        payload["safety_summary"] = dict(self.safety_summary)
        payload["metrics_summary"] = dict(self.metrics_summary)
        return {key: value for key, value in payload.items() if value not in (None, {}, [], ())}


def build_read_only_agent_report(
    *,
    agent_name: str,
    verdict: str,
    confidence: str,
    first_failing_event: str | None = None,
    findings: tuple[AgentFinding, ...] = (),
    not_root_cause: tuple[str, ...] = (),
    next_fix_recommendation: str = "",
    metrics: dict[str, Any] | None = None,
) -> AgentReport:
    return AgentReport(
        schema_version=AGENT_CONTRACT_SCHEMA_VERSION,
        agent_name=agent_name,
        generated_at=_utc_now_iso(),
        read_only=True,
        append=False,
        is_order_action=False,
        broker_api_called=False,
        live_order_allowed=False,
        no_order_action=True,
        verdict=verdict,
        confidence=confidence,
        first_failing_event=first_failing_event,
        findings=findings,
        not_root_cause=not_root_cause,
        next_fix_recommendation=next_fix_recommendation,
        metrics=dict(metrics or {}),
    )
