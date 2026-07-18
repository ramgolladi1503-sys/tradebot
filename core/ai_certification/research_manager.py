from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .bundle import canonical_json_bytes
from .gemini_client import GeminiClient, GeminiClientError, redact_secrets
from .mcp_server import (
    certify_bundle_tool,
    evaluate_gate,
    inspect_bundle,
    retrieve_policy_context,
)


ALLOWED_ACTIONS = (
    "request_approval",
    "inspect_bundle",
    "validate_source_provenance",
    "validate_temporal_causality",
    "validate_execution_realism",
    "retrieve_policy_context",
    "certify_bundle",
    "critique_report",
    "complete",
)


@dataclass(frozen=True)
class ResearchRun:
    run_id: str
    bundle_id: str
    state: str
    approved: bool
    next_action: str
    report: dict[str, Any] | None = None
    critique: dict[str, Any] | None = None
    error: str | None = None


class ActionPlanner(Protocol):
    def choose_action(self, run: ResearchRun) -> str: ...


class DeterministicPlanner:
    """Fail-closed workflow policy; the model may suggest but cannot expand it."""

    def choose_action(self, run: ResearchRun) -> str:
        if run.state == "CREATED":
            return "request_approval"
        if not run.approved:
            return "request_approval"
        transitions = {
            "APPROVED": "inspect_bundle",
            "INSPECTED": "validate_source_provenance",
            "SOURCE_VALIDATED": "validate_temporal_causality",
            "TIMING_VALIDATED": "validate_execution_realism",
            "EXECUTION_VALIDATED": "retrieve_policy_context",
            "POLICY_RETRIEVED": "certify_bundle",
            "CERTIFIED": "critique_report",
            "CRITIQUED": "complete",
            "COMPLETED": "complete",
            "BLOCKED": "complete",
        }
        return transitions.get(run.state, "complete")


class GeminiPlanner:
    """Gemini planner constrained to the deterministic action vocabulary."""

    def __init__(self, client: GeminiClient) -> None:
        self.client = client
        self.fallback = DeterministicPlanner()

    def choose_action(self, run: ResearchRun) -> str:
        expected = self.fallback.choose_action(run)
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(ALLOWED_ACTIONS)},
                "reason": {"type": "string"},
            },
            "required": ["action", "reason"],
            "additionalProperties": False,
        }
        try:
            answer = self.client.generate_json(
                instruction=(
                    "Choose the next read-only certification action. Human approval is mandatory. "
                    "Never choose broker, order, risk override, code mutation, shell, database mutation, or Git actions."
                ),
                payload={
                    "state": run.state,
                    "approved": run.approved,
                    "has_report": run.report is not None,
                    "has_critique": run.critique is not None,
                    "deterministic_expected_action": expected,
                },
                schema=schema,
            )
        except GeminiClientError:
            return expected
        action = str(answer.get("action") or "")
        return action if action == expected else expected


class SQLiteResearchStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_ledger (
                    fingerprint TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    output TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def save(self, run: ResearchRun) -> None:
        payload = json.dumps(asdict(run), sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO research_runs(run_id,payload) VALUES(?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
                (run.run_id, payload),
            )

    def load(self, run_id: str) -> ResearchRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"research run not found: {run_id}")
        return ResearchRun(**json.loads(str(row[0])))

    def load_tool_output(self, fingerprint: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT output FROM tool_ledger WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
        return json.loads(str(row[0])) if row else None

    def save_tool_output(
        self,
        *,
        fingerprint: str,
        run_id: str,
        action: str,
        output: dict[str, Any],
    ) -> None:
        payload = json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO tool_ledger(fingerprint,run_id,action,output) VALUES(?,?,?,?)",
                (fingerprint, run_id, action, payload),
            )


class CertificationResearchManager:
    """Durable read-only orchestration around the deterministic certifier."""

    def __init__(
        self,
        *,
        evidence_root: str | Path,
        report_root: str | Path,
        repository_root: str | Path,
        store: SQLiteResearchStore,
        planner: ActionPlanner | None = None,
    ) -> None:
        self.evidence_root = Path(evidence_root).expanduser().resolve()
        self.report_root = Path(report_root).expanduser().resolve()
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.store = store
        self.planner = planner or DeterministicPlanner()

    def create_run(self, run_id: str, bundle_id: str) -> ResearchRun:
        if not run_id or not bundle_id:
            raise ValueError("run_id and bundle_id are required")
        run = ResearchRun(
            run_id=run_id,
            bundle_id=bundle_id,
            state="CREATED",
            approved=False,
            next_action="request_approval",
        )
        self.store.save(run)
        return run

    def approve(self, run_id: str) -> ResearchRun:
        run = self.store.load(run_id)
        if run.state not in {"CREATED", "AWAITING_APPROVAL"}:
            return run
        updated = ResearchRun(
            **{
                **asdict(run),
                "approved": True,
                "state": "APPROVED",
                "next_action": "inspect_bundle",
            }
        )
        self.store.save(updated)
        return updated

    def step(self, run_id: str) -> ResearchRun:
        run = self.store.load(run_id)
        action = self.planner.choose_action(run)
        if action not in ALLOWED_ACTIONS:
            action = DeterministicPlanner().choose_action(run)
        if action == "request_approval":
            updated = ResearchRun(**{**asdict(run), "state": "AWAITING_APPROVAL", "next_action": action})
            self.store.save(updated)
            return updated
        if action == "complete":
            updated = ResearchRun(**{**asdict(run), "state": "COMPLETED", "next_action": "complete"})
            self.store.save(updated)
            return updated
        if not run.approved:
            blocked = ResearchRun(
                **{
                    **asdict(run),
                    "state": "BLOCKED",
                    "next_action": "complete",
                    "error": "human_approval_required",
                }
            )
            self.store.save(blocked)
            return blocked

        try:
            output = self._execute_idempotent(run, action)
            updated = self._advance(run, action, output)
        except Exception as exc:  # fail closed at the orchestration boundary
            updated = ResearchRun(
                **{
                    **asdict(run),
                    "state": "BLOCKED",
                    "next_action": "complete",
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
        self.store.save(updated)
        return updated

    def run_to_completion(self, run_id: str, *, maximum_steps: int = 12) -> ResearchRun:
        for _ in range(maximum_steps):
            run = self.step(run_id)
            if run.state in {"COMPLETED", "BLOCKED", "AWAITING_APPROVAL"}:
                return run
        run = self.store.load(run_id)
        blocked = ResearchRun(
            **{
                **asdict(run),
                "state": "BLOCKED",
                "next_action": "complete",
                "error": "step_budget_exhausted",
            }
        )
        self.store.save(blocked)
        return blocked

    def _execute_idempotent(self, run: ResearchRun, action: str) -> dict[str, Any]:
        fingerprint = hashlib.sha256(
            canonical_json_bytes(
                {
                    "run_id": run.run_id,
                    "bundle_id": run.bundle_id,
                    "action": action,
                    "repository_root": str(self.repository_root),
                }
            )
        ).hexdigest()
        prior = self.store.load_tool_output(fingerprint)
        if prior is not None:
            return prior
        output = self._execute(run, action)
        self.store.save_tool_output(
            fingerprint=fingerprint,
            run_id=run.run_id,
            action=action,
            output=output,
        )
        return output

    def _execute(self, run: ResearchRun, action: str) -> dict[str, Any]:
        if action == "inspect_bundle":
            return inspect_bundle(run.bundle_id, evidence_root=self.evidence_root)
        if action == "validate_source_provenance":
            return evaluate_gate(
                run.bundle_id,
                "source_artifact_provenance",
                evidence_root=self.evidence_root,
            )
        if action == "validate_temporal_causality":
            return evaluate_gate(
                run.bundle_id,
                "temporal_causality",
                evidence_root=self.evidence_root,
            )
        if action == "validate_execution_realism":
            return evaluate_gate(
                run.bundle_id,
                "execution_realism",
                evidence_root=self.evidence_root,
            )
        if action == "retrieve_policy_context":
            return retrieve_policy_context(
                "source provenance temporal causality execution realism certification blockers",
                repository_root=self.repository_root,
                limit=4,
            )
        if action == "certify_bundle":
            return certify_bundle_tool(
                run.bundle_id,
                evidence_root=self.evidence_root,
                report_root=self.report_root,
                repository_root=self.repository_root,
            )
        if action == "critique_report":
            return deterministic_critique(run.report or {})
        raise ValueError(f"unsupported action: {action}")

    def _advance(
        self,
        run: ResearchRun,
        action: str,
        output: dict[str, Any],
    ) -> ResearchRun:
        state_map = {
            "inspect_bundle": "INSPECTED",
            "validate_source_provenance": "SOURCE_VALIDATED",
            "validate_temporal_causality": "TIMING_VALIDATED",
            "validate_execution_realism": "EXECUTION_VALIDATED",
            "retrieve_policy_context": "POLICY_RETRIEVED",
            "certify_bundle": "CERTIFIED",
            "critique_report": "CRITIQUED",
        }
        report = run.report
        critique = run.critique
        if action == "certify_bundle":
            report = dict(output.get("report") or {})
        if action == "critique_report":
            critique = output
        updated = ResearchRun(
            **{
                **asdict(run),
                "state": state_map[action],
                "next_action": "",
                "report": report,
                "critique": critique,
                "error": None,
            }
        )
        next_action = self.planner.choose_action(updated)
        return ResearchRun(**{**asdict(updated), "next_action": next_action})


def deterministic_critique(report: dict[str, Any]) -> dict[str, Any]:
    safe = redact_secrets(report)
    blockers = [str(item) for item in safe.get("blockers", [])]
    warnings = [str(item) for item in safe.get("warnings", [])]
    categories: list[str] = []
    joined = " ".join(blockers + warnings).lower()
    for name, needles in {
        "data": ("data", "hash", "source", "manifest"),
        "causality": ("temporal", "timing", "leakage", "future"),
        "execution": ("execution", "fill", "liquidity", "quote"),
        "wfa": ("walk_forward", "holdout", "contamination"),
        "tests": ("test", "exception", "agent_error"),
    }.items():
        if any(needle in joined for needle in needles):
            categories.append(name)
    status = str(safe.get("evidence_certification") or "UNKNOWN")
    verdict = str(safe.get("strategy_verdict") or "WITHHELD")
    return {
        "evidence_status": status,
        "strategy_verdict": verdict,
        "blocker_categories": sorted(set(categories)),
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "recommendation": (
            "repair evidence before further strategy claims"
            if blockers
            else "retain the deterministic verdict and avoid unsupported promotion"
        ),
        "unsafe_recommendation": False,
        "numeric_evidence_fabricated": False,
    }
