from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from research.governance.autonomous_loop import AutonomousLoopSupervisor, RegistryError, TaskState, assert_transition
from research.governance.autonomous_loop.dependency_graph import (
    DependencyError,
    build_eligible_task_ids,
    eligible_task_ids,
    validate_dependencies,
)
from research.governance.autonomous_loop.evidence_contract import SafetyBoundary


REGISTRY = Path("research/governance/autonomous_loop/TASK_REGISTRY.yaml")


def load_registry():
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def test_program_registry_preserves_t01_provisional_build_state():
    supervisor = AutonomousLoopSupervisor(load_registry())
    assert supervisor.tasks["T01"]["status"] == "INTEGRATION_VALID"
    assert supervisor.next_eligible_task() is None
    assert supervisor.next_build_eligible_task() == "T02"
    assert len(supervisor.tasks) == 35


def test_build_eligibility_releases_downstream_after_integration_valid_only():
    registry = load_registry()
    registry["tasks"]["T01"]["status"] = "INTEGRATION_VALID"
    assert build_eligible_task_ids(registry["tasks"]) == ["T02"]
    assert eligible_task_ids(registry["tasks"]) == []


def test_build_eligibility_never_treats_provisional_state_as_certification():
    registry = load_registry()
    registry["tasks"]["T01"]["status"] = "IMPLEMENTATION_VALID"
    supervisor = AutonomousLoopSupervisor(registry)
    assert supervisor.next_build_eligible_task() == "T02"
    assert supervisor.next_eligible_task() is None


def test_build_eligibility_remains_fail_closed_for_blocked_or_generic_invalidated():
    registry = load_registry()
    for state in ("BLOCKED", "INVALIDATED"):
        registry["tasks"]["T01"]["status"] = state
        assert "T02" not in build_eligible_task_ids(registry["tasks"])


def test_safety_boundary_is_fail_closed():
    SafetyBoundary().validate_fail_closed()
    with pytest.raises(ValueError):
        SafetyBoundary(order_authority=True).validate_fail_closed()
    with pytest.raises(ValueError):
        SafetyBoundary(broker_write_authority=True).validate_fail_closed()


def test_illegal_state_skip_is_rejected():
    with pytest.raises(ValueError):
        assert_transition(TaskState.PENDING, TaskState.SEALED)
    with pytest.raises(ValueError):
        assert_transition(TaskState.IMPLEMENTATION_VALID, TaskState.CI_GREEN)


def test_dependency_cycle_is_rejected():
    tasks = {
        "T01": {"status": "PENDING", "depends_on": ["T02"], "blocks": []},
        "T02": {"status": "PENDING", "depends_on": ["T01"], "blocks": []},
    }
    with pytest.raises(DependencyError):
        validate_dependencies(tasks)


def test_unknown_dependency_is_rejected():
    tasks = {"T01": {"status": "PENDING", "depends_on": ["T99"], "blocks": []}}
    with pytest.raises(DependencyError):
        validate_dependencies(tasks)


def test_unknown_block_target_is_rejected():
    tasks = {"T01": {"status": "PENDING", "depends_on": [], "blocks": ["T99"]}}
    with pytest.raises(DependencyError):
        validate_dependencies(tasks)


def test_dependencies_do_not_treat_blocked_or_generic_invalidated_as_pass():
    registry = load_registry()
    registry["tasks"]["T01"]["status"] = "BLOCKED"
    assert "T02" not in eligible_task_ids(registry["tasks"])
    registry["tasks"]["T01"]["status"] = "INVALIDATED"
    assert "T02" not in eligible_task_ids(registry["tasks"])


def test_declared_no_edge_terminal_releases_research_dependent():
    registry = load_registry()
    for task_id in ["T01", "T02", "T03", "T04", "T05"]:
        registry["tasks"][task_id]["status"] = "SEALED"
    registry["tasks"]["T06"]["status"] = "NO_STRUCTURAL_EDGE_FOUND"
    assert "T07" in eligible_task_ids(registry["tasks"])


def test_undeclared_no_edge_terminal_is_rejected_by_supervisor():
    supervisor = AutonomousLoopSupervisor(load_registry())
    supervisor.tasks["T01"]["status"] = "IMPLEMENTATION_VALID"
    with pytest.raises(RegistryError):
        supervisor.transition("T01", "NO_STRUCTURAL_EDGE_FOUND")


def dynamic_task(task_id="T36"):
    return {
        "task_id": task_id,
        "title": "Trusted provenance-anchor hardening",
        "architecture_version": "V2",
        "status": "PENDING",
        "depends_on": ["T01"],
        "blocks": ["T02"],
        "created_from": {"task_id": "T01", "candidate_sha": "a" * 40},
        "reason_code": "NEW_SAFETY_GAP",
        "reason": "Caller-controlled provenance could self-attest live evidence.",
        "required_guarantee": "Live evidence must be anchored to trusted provenance.",
        "change_budget_required": True,
        "rationale": {
            "evidence_exposed_need": "Adversarial provenance test accepted self-attested input.",
            "why_current_task_cannot_absorb": "Repair crosses the shared provenance trust boundary.",
            "protects_or_enables": "Trusted live-evidence identity.",
            "consequence_of_skipping": "Replay could masquerade as live.",
            "dependencies_and_blocks": "Depends on T01 and blocks T02.",
            "why_not_scope_drift": "It closes an existing locked live-provenance guarantee.",
        },
        "objective": "Harden the provenance trust anchor.",
        "allowed_scope": ["research provenance governance"],
        "prohibited_scope": ["broker writes", "orders", "execution authority"],
        "required_tests": {"focused": [], "adversarial": [], "integration": [], "regression": []},
        "independent_verification": {"required": True},
        "ci": {"required": True},
        "exit_gates": ["PROVENANCE_ANCHOR_OFFLINE_CERTIFIED"],
        "stop_conditions": ["BLOCKED_AUTH"],
        "evidence_paths": [],
        "evidence": {},
    }


def test_dynamic_task_requires_monotonic_t36_plus_id():
    supervisor = AutonomousLoopSupervisor(load_registry())
    supervisor.create_dynamic_task(dynamic_task())
    assert "T36" in supervisor.tasks
    with pytest.raises(RegistryError):
        supervisor.create_dynamic_task(dynamic_task("T38"))


def test_dynamic_task_rejects_unguarded_scope_growth():
    supervisor = AutonomousLoopSupervisor(load_registry())
    task = dynamic_task()
    task["change_budget_required"] = False
    with pytest.raises(ValueError):
        supervisor.create_dynamic_task(task)


def test_dynamic_task_requires_complete_six_question_rationale():
    supervisor = AutonomousLoopSupervisor(load_registry())
    task = dynamic_task()
    del task["rationale"]["why_not_scope_drift"]
    with pytest.raises(ValueError):
        supervisor.create_dynamic_task(task)


def test_dynamic_task_blocks_field_becomes_real_dependency():
    supervisor = AutonomousLoopSupervisor(load_registry())
    supervisor.create_dynamic_task(dynamic_task())
    assert "T36" in supervisor.tasks["T02"]["depends_on"]
    supervisor.tasks["T01"]["status"] = "SEALED"
    assert "T02" not in eligible_task_ids(supervisor.tasks)


def test_dynamic_task_rejects_unknown_block_target_atomically():
    supervisor = AutonomousLoopSupervisor(load_registry())
    task = dynamic_task()
    task["blocks"] = ["T99"]
    with pytest.raises(RegistryError):
        supervisor.create_dynamic_task(task)
    assert "T36" not in supervisor.tasks


def _complete_evidence(candidate_sha="b" * 40):
    return {
        "candidate_sha": candidate_sha,
        "focused": {"status": "PASS", "candidate_sha": candidate_sha},
        "adversarial": {"status": "PASS", "candidate_sha": candidate_sha},
        "integration": {"status": "PASS", "candidate_sha": candidate_sha},
        "regression": {"status": "PASS", "candidate_sha": candidate_sha},
        "independent_verification": {"status": "PASS", "candidate_sha": candidate_sha},
        "ci": {"status": "PASS", "candidate_sha": candidate_sha},
    }


def test_seal_rejects_missing_exact_sha_and_gate_evidence():
    registry = load_registry()
    supervisor = AutonomousLoopSupervisor(registry)
    task = supervisor.tasks["T01"]
    task["status"] = "CI_GREEN"
    with pytest.raises(RegistryError):
        supervisor.transition("T01", "SEALED")


def test_seal_rejects_non_exact_candidate_sha():
    supervisor = AutonomousLoopSupervisor(load_registry())
    task = supervisor.tasks["T01"]
    task["status"] = "CI_GREEN"
    task["evidence"] = _complete_evidence("not-a-git-sha")
    with pytest.raises(RegistryError):
        supervisor.transition("T01", "SEALED")


def test_seal_rejects_unbound_gate_evidence():
    supervisor = AutonomousLoopSupervisor(load_registry())
    task = supervisor.tasks["T01"]
    task["status"] = "CI_GREEN"
    task["evidence"] = _complete_evidence()
    task["evidence"]["adversarial"]["candidate_sha"] = "c" * 40
    with pytest.raises(RegistryError):
        supervisor.transition("T01", "SEALED")


def test_seal_rejects_string_pass_without_sha_binding():
    supervisor = AutonomousLoopSupervisor(load_registry())
    task = supervisor.tasks["T01"]
    task["status"] = "CI_GREEN"
    task["evidence"] = _complete_evidence()
    task["evidence"]["focused"] = "pass"
    with pytest.raises(RegistryError):
        supervisor.transition("T01", "SEALED")


def test_seal_rejects_major_finding_even_with_evidence():
    registry = load_registry()
    supervisor = AutonomousLoopSupervisor(registry)
    task = supervisor.tasks["T01"]
    task["status"] = "CI_GREEN"
    task["major_findings"] = 1
    task["mandatory_unknowns"] = 0
    task["evidence"] = _complete_evidence()
    with pytest.raises(RegistryError):
        supervisor.transition("T01", "SEALED")


def test_seal_accepts_only_complete_fail_closed_evidence():
    registry = load_registry()
    supervisor = AutonomousLoopSupervisor(registry)
    task = supervisor.tasks["T01"]
    task["status"] = "CI_GREEN"
    task["major_findings"] = 0
    task["critical_findings"] = 0
    task["mandatory_unknowns"] = 0
    task["evidence"] = _complete_evidence()
    supervisor.transition("T01", "SEALED")
    assert supervisor.tasks["T01"]["status"] == "SEALED"


def test_dump_round_trip_preserves_registry():
    supervisor = AutonomousLoopSupervisor(load_registry())
    dumped = supervisor.dump()
    reloaded = yaml.safe_load(dumped)
    assert reloaded["tasks"]["T01"]["external_ref"]["number"] == 815
