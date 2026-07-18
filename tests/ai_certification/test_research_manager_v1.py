from __future__ import annotations

import sqlite3
from pathlib import Path

from core.ai_certification.research_manager import (
    CertificationResearchManager,
    GeminiPlanner,
    SQLiteResearchStore,
)


class WrongButAllowedClient:
    def generate_json(self, **kwargs):
        del kwargs
        return {"action": "certify_bundle", "reason": "skip controls"}


def _manager(tmp_path: Path, bundle: Path, planner=None) -> CertificationResearchManager:
    return CertificationResearchManager(
        evidence_root=bundle.parent,
        report_root=tmp_path / "reports",
        repository_root=tmp_path,
        store=SQLiteResearchStore(tmp_path / "state" / "research.sqlite3"),
        planner=planner,
    )


def test_human_approval_is_required_before_bundle_access(qa_bundle_factory, tmp_path: Path):
    bundle = qa_bundle_factory()
    manager = _manager(tmp_path, bundle)
    manager.create_run("approval-run", bundle.name)

    run = manager.run_to_completion("approval-run")

    assert run.state == "AWAITING_APPROVAL"
    assert run.approved is False
    assert run.report is None


def test_manager_completes_deterministic_read_only_flow(qa_bundle_factory, tmp_path: Path):
    bundle = qa_bundle_factory()
    manager = _manager(tmp_path, bundle)
    manager.create_run("complete-run", bundle.name)
    manager.approve("complete-run")

    run = manager.run_to_completion("complete-run")

    assert run.state == "COMPLETED"
    assert run.report["evidence_certification"] == "CERTIFIED"
    assert run.report["strategy_verdict"] == "NO_STRUCTURAL_EDGE"
    assert run.critique["unsafe_recommendation"] is False
    assert run.critique["numeric_evidence_fabricated"] is False


def test_restart_reuses_idempotent_tool_outputs(qa_bundle_factory, tmp_path: Path):
    bundle = qa_bundle_factory()
    first = _manager(tmp_path, bundle)
    first.create_run("restart-run", bundle.name)
    first.approve("restart-run")
    completed = first.run_to_completion("restart-run")
    assert completed.state == "COMPLETED"

    second = _manager(tmp_path, bundle)
    repeated = second.run_to_completion("restart-run")

    assert repeated.report == completed.report
    with sqlite3.connect(tmp_path / "state" / "research.sqlite3") as connection:
        count = connection.execute("SELECT COUNT(*) FROM tool_ledger").fetchone()[0]
    assert count == 7


def test_gemini_cannot_skip_deterministic_action_order(qa_bundle_factory, tmp_path: Path):
    bundle = qa_bundle_factory()
    planner = GeminiPlanner(WrongButAllowedClient())
    manager = _manager(tmp_path, bundle, planner=planner)
    manager.create_run("bounded-run", bundle.name)
    manager.approve("bounded-run")

    first_step = manager.step("bounded-run")

    assert first_step.state == "INSPECTED"
    assert first_step.next_action == "validate_source_provenance"


def test_step_budget_fails_closed(qa_bundle_factory, tmp_path: Path):
    bundle = qa_bundle_factory()
    manager = _manager(tmp_path, bundle)
    manager.create_run("budget-run", bundle.name)
    manager.approve("budget-run")

    run = manager.run_to_completion("budget-run", maximum_steps=1)

    assert run.state == "BLOCKED"
    assert run.error == "step_budget_exhausted"
