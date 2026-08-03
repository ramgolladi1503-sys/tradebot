from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .agent import ReliabilityAgent, ToolRegistry
from .contracts import AgentMode
from .evidence import EvidenceLedger, canonical_json
from .openai_reasoner import OpenAIReasoner
from .runtime import build_session_manifest, build_tools, read_jsonl, default_artifact_paths


@dataclass(frozen=True)
class Trigger:
    trigger_type: str
    severity: str
    payload: Mapping[str, Any]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json({
            "trigger_type": self.trigger_type,
            "severity": self.severity,
            "payload": dict(self.payload),
        }).encode("utf-8")).hexdigest()



def detect_triggers(repo_root: str | Path, *, session_date: str | None = None) -> list[Trigger]:
    paths = default_artifact_paths(repo_root, session_date=session_date)
    triggers: list[Trigger] = []
    lineage_path = paths["candidate_lineage"]
    if not lineage_path.exists():
        triggers.append(Trigger("CANDIDATE_LINEAGE_MISSING", "P1", {"path": str(lineage_path)}))
        return triggers
    rows = read_jsonl(lineage_path)
    invalid = [row for row in rows if row.get("_invalid_json")]
    if invalid:
        triggers.append(Trigger("CANDIDATE_LINEAGE_INVALID_JSON", "P1", {"count": len(invalid)}))
    untrustworthy = [
        row for row in rows
        if (
            str(row.get("stage_status") or "").lower() == "selected"
            or bool(row.get("top_opportunity"))
            or str(row.get("permission") or "").upper() == "EXECUTE"
        ) and (
            bool(row.get("fallback_used"))
            or bool(row.get("recovered_fallback"))
            or bool(row.get("stale_quote"))
        )
    ]
    if untrustworthy:
        triggers.append(Trigger(
            "UNTRUSTWORTHY_EXECUTABLE_CANDIDATE", "P0",
            {"count": len(untrustworthy), "candidate_ids": sorted({str(row.get('candidate_id') or '') for row in untrustworthy})[:20]},
        ))
    blocked_without_reason = [
        row for row in rows
        if str(row.get("stage_status") or "").lower() == "blocked"
        and not str(row.get("block_reason") or row.get("block_reason_code") or "").strip()
        and not row.get("downgrade_reasons")
    ]
    if blocked_without_reason:
        triggers.append(Trigger(
            "BLOCKED_CANDIDATE_WITHOUT_REASON", "P1", {"count": len(blocked_without_reason)}
        ))
    return triggers


class LiveAgentSupervisor:
    """Polling supervisor that invokes the AI only for deterministic triggers."""

    def __init__(
        self,
        *,
        session_id: str,
        repo_root: str | Path,
        evidence_path: str | Path,
        interval_sec: float = 15.0,
        session_date: str | None = None,
        reasoner_factory: Callable[[], Any] | None = None,
    ):
        if interval_sec < 1.0:
            raise ValueError("interval_sec_below_minimum")
        self.session_id = str(session_id)
        self.repo_root = Path(repo_root)
        self.interval_sec = float(interval_sec)
        self.session_date = session_date
        self.ledger = EvidenceLedger(evidence_path)
        self.tools: ToolRegistry = build_tools(repo_root, session_date=session_date)
        self.reasoner_factory = reasoner_factory or OpenAIReasoner
        self._seen: set[str] = set()

    def run(self, *, max_iterations: int | None = None, stop_file: str | Path | None = None) -> dict[str, Any]:
        manifest = build_session_manifest(
            session_id=self.session_id, mode=AgentMode.LIVE_OBSERVE, repo_root=self.repo_root
        )
        self.ledger.append("session_manifest", manifest, session_id=self.session_id)
        iteration = 0
        investigations: list[dict[str, Any]] = []
        stop_path = Path(stop_file) if stop_file else None
        while max_iterations is None or iteration < max_iterations:
            if stop_path and stop_path.exists():
                break
            iteration += 1
            triggers = detect_triggers(self.repo_root, session_date=self.session_date)
            for trigger in triggers:
                if trigger.fingerprint in self._seen:
                    continue
                self._seen.add(trigger.fingerprint)
                trigger_ref = self.ledger.append(
                    "supervisor_trigger",
                    {"trigger_type": trigger.trigger_type, "severity": trigger.severity, "payload": dict(trigger.payload)},
                    session_id=self.session_id,
                )
                agent = ReliabilityAgent(
                    session_id=self.session_id,
                    mode=AgentMode.LIVE_OBSERVE,
                    reasoner=self.reasoner_factory(),
                    tools=self.tools,
                    ledger=self.ledger,
                    max_steps=12,
                    max_tool_calls=8,
                )
                result = agent.run(
                    f"Investigate trigger {trigger.trigger_type} and either produce a machine-verifiable finding or stop for insufficient evidence.",
                    initial_observations={
                        "trigger_evidence_id": trigger_ref.evidence_id,
                        "trigger": {"type": trigger.trigger_type, "severity": trigger.severity, "payload": dict(trigger.payload)},
                    },
                )
                investigations.append({
                    "trigger": trigger.trigger_type,
                    "trigger_evidence_id": trigger_ref.evidence_id,
                    "result": result,
                })
            if max_iterations is None or iteration < max_iterations:
                time.sleep(self.interval_sec)
        verification = self.ledger.verify()
        return {
            "session_id": self.session_id,
            "iterations": iteration,
            "unique_triggers": len(self._seen),
            "investigations": investigations,
            "evidence_chain_valid": verification.valid,
            "evidence_chain_errors": list(verification.errors),
        }
