import hashlib
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.delivery.evidence import canonical_json
from core.delivery.gates import GateName, GateStatus, evaluate_gate
from core.delivery.models import (
    Defect, DefectSeverity, DefectStatus, DeliveryState, Evidence, EvidenceStatus,
    EvidenceType, WorkItem, WorkItemType,
)
from core.delivery.orchestrator import DeliveryOrchestrator, GovernanceError
from core.delivery.roles import DeliveryRole as R
from core.delivery.validators import validate_work_item, work_item_from_dict, work_item_to_dict
from core.delivery.cli import main as delivery_cli


def make_item(**kw):
    base = dict(
        work_item_id="FTR-1", type=WorkItemType.FEATURE, parent_epic="EP-1", parent_feature="",
        title="Delivery governance", priority="P1", business_goal="Enforce delivery gates",
        current_behavior="No machine enforcement", expected_behavior="Invalid transitions fail closed",
        in_scope=("governance package",), out_of_scope=("trading runtime",), dependencies=(),
        acceptance_criteria=("unsafe transitions are rejected",),
        safety_constraints=("no broker calls", "no runtime wiring"), architecture_impact="offline Python package",
        allowed_paths=("core/delivery/**", "tests/delivery/**"),
        forbidden_paths=("core/broker/**", "strategies/**", "config/**"),
        expected_tests=("tests/delivery/test_delivery_orchestrator.py",),
        qa_attack_plan=("unknown role", "self approval", "forged state"),
        uat_criteria=("blocked CI prevents merge",), release_gates=("all required gates pass",),
        rollback_plan="Remove governance package; no runtime consumer is wired.",
        required_ci_checks=("unit", "lint"),
    )
    base.update(kw)
    return WorkItem(**base)


def add(o, eid, kind, role, author, status=EvidenceStatus.PASS, refs=(), checks=(), summary="proof",
        timestamp=None):
    timestamp = timestamp or f"2026-01-01T00:{len(o.item.evidence):02d}:00+00:00"
    refs = tuple(refs) or (f"evidence://{eid}",)
    ev = Evidence(eid, o.item.work_item_id, kind, role, author, timestamp, status, summary,
                  tuple(refs), check_results=tuple(checks))
    o.add_evidence(ev)
    return o.item.evidence[-1]


def transition(o, target, role, actor, ev=(), minute=0):
    return o.transition(target, acting_role=role, actor=actor,
                        timestamp=f"2026-01-01T01:{minute:02d}:00+00:00",
                        reason=f"evidence review for {target}", evidence_ids=ev)


def prepared_for_dev(**item_kwargs):
    o = DeliveryOrchestrator(make_item(**item_kwargs))
    ba = add(o, "req-ba", EvidenceType.REQUIREMENT_EVIDENCE, R.BUSINESS_ANALYST, "ba")
    transition(o, DeliveryState.REQUIREMENT_READY, R.BUSINESS_ANALYST, "ba", (ba.evidence_id,))
    po = add(o, "req-po", EvidenceType.REQUIREMENT_EVIDENCE, R.PRODUCT_OWNER, "po")
    arch = add(o, "arch", EvidenceType.ARCHITECTURE_EVIDENCE, R.SYSTEM_ARCHITECT, "architect")
    transition(o, DeliveryState.DESIGN_READY, R.SYSTEM_ARCHITECT, "architect",
               (o.item.evidence[0].evidence_id, po.evidence_id, arch.evidence_id), 1)
    transition(o, DeliveryState.IN_DEVELOPMENT, R.BACKEND_DEVELOPER, "dev", minute=2)
    return o


def ready_for_uat(o):
    dev = add(o, "devtest", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "dev",
              timestamp="2026-01-01T01:03:00+00:00")
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (dev.evidence_id,), 3)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=4)
    qa = add(o, "qa", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
             timestamp="2026-01-01T01:05:00+00:00")
    transition(o, DeliveryState.QA_PASSED, R.QA_ENGINEER, "qa", (qa.evidence_id,), 5)
    senior = add(o, "senior", EvidenceType.SENIOR_QA_EVIDENCE, R.SENIOR_QA, "senior",
                 timestamp="2026-01-01T01:06:00+00:00")
    transition(o, DeliveryState.SENIOR_QA, R.SENIOR_QA, "senior", (senior.evidence_id,), 6)
    transition(o, DeliveryState.UAT, R.SENIOR_QA, "senior", (senior.evidence_id,), 7)
    return o


def complete_to_product(o, uat_status=EvidenceStatus.PASS):
    o = ready_for_uat(o)
    uat = add(o, "uat", EvidenceType.UAT_EVIDENCE, R.UAT_REVIEWER, "uat",
              status=uat_status, summary="valid documented N/A" if uat_status == EvidenceStatus.NOT_APPLICABLE else "UAT passed",
              timestamp="2026-01-01T01:08:00+00:00")
    product = add(o, "product", EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE, R.PRODUCT_OWNER, "po",
                  timestamp="2026-01-01T01:09:00+00:00")
    transition(o, DeliveryState.PRODUCT_ACCEPTED, R.PRODUCT_OWNER, "po",
               (uat.evidence_id, product.evidence_id), 9)
    return o


def ready_for_pr_open():
    o = complete_to_product(prepared_for_dev())
    release = add(o, "release", EvidenceType.RELEASE_EVIDENCE, R.RELEASE_MANAGER, "rm",
                  timestamp="2026-01-01T01:10:00+00:00")
    transition(o, DeliveryState.RELEASE_READY, R.RELEASE_MANAGER, "rm", (release.evidence_id,), 10)
    transition(o, DeliveryState.PR_OPEN, R.RELEASE_MANAGER, "rm", (release.evidence_id,), 11)
    return o, release


def test_complete_lifecycle_requires_evidence_at_every_gate_and_appends_audit():
    o, release = ready_for_pr_open()
    ci = add(o, "ci", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
             checks=(("unit", "SUCCESS"), ("lint", "SUCCESS")), timestamp="2026-01-01T01:12:00+00:00")
    transition(o, DeliveryState.CI_GREEN, R.RELEASE_MANAGER, "rm", (ci.evidence_id,), 12)
    transition(o, DeliveryState.MERGE_APPROVED, R.RELEASE_MANAGER, "rm", (release.evidence_id,), 13)
    merged = add(o, "merged", EvidenceType.RELEASE_EVIDENCE, R.RELEASE_MANAGER, "rm",
                 refs=("https://example.invalid/commit/abc",), timestamp="2026-01-01T01:14:00+00:00")
    transition(o, DeliveryState.MERGED, R.RELEASE_MANAGER, "rm", (merged.evidence_id,), 14)
    prod = add(o, "prod", EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE, R.PRODUCTION_SRE, "sre",
               timestamp="2026-01-01T01:15:00+00:00")
    transition(o, DeliveryState.PRODUCTION_VERIFIED, R.PRODUCTION_SRE, "sre", (prod.evidence_id,), 15)
    transition(o, DeliveryState.DONE, R.PRODUCTION_SRE, "sre", (prod.evidence_id,), 16)
    assert o.item.current_state == DeliveryState.DONE
    assert len(o.item.state_history) == 16
    gate_statuses = {g["gate"]: g["status"] for g in o.gate_results()}
    assert gate_statuses["G8_MERGE"] == "PASS"
    assert gate_statuses["G9_PRODUCTION_VERIFY"] == "PASS"
    evidence_gates = [g for g in o.gate_results() if g["gate"].startswith("EVIDENCE_G")]
    assert len(evidence_gates) == 4
    assert all(g["status"] == "BLOCKED" and g["blocking"] is False for g in evidence_gates)
    readiness = o.readiness()
    assert readiness["ready"] is True
    assert readiness["evidence_standard"]["mode"] == "REPORT_ONLY"
    assert readiness["evidence_standard"]["blocking"] is False
    validate_work_item(work_item_from_dict(work_item_to_dict(o.item)))


def test_documented_uat_na_is_accepted_and_visible_as_na_gate():
    o = complete_to_product(prepared_for_dev(), EvidenceStatus.NOT_APPLICABLE)
    assert o.item.current_state == DeliveryState.PRODUCT_ACCEPTED
    g4 = next(g for g in o.gate_results() if g["gate"] == "G4_UAT")
    assert g4["status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("target", ["MERGED", "unknown", "QA_PASSED"])
def test_invalid_or_unknown_transition_fails_closed(target):
    o = DeliveryOrchestrator(make_item())
    with pytest.raises(GovernanceError):
        transition(o, target, R.BACKEND_DEVELOPER, "dev")
    assert o.item.current_state == DeliveryState.BACKLOG


def test_product_acceptance_cannot_skip_uat():
    o = prepared_for_dev()
    with pytest.raises(GovernanceError, match="invalid transition"):
        transition(o, DeliveryState.PRODUCT_ACCEPTED, R.PRODUCT_OWNER, "po")


def test_unknown_role_is_rejected():
    o = DeliveryOrchestrator(make_item())
    with pytest.raises(GovernanceError, match="unknown workflow state or role"):
        o.transition("BACKLOG", acting_role="ADMIN", actor="x", timestamp="2026-01-01T00:00:00+00:00",
                     reason="bad")


def test_definition_of_ready_and_missing_requirement_evidence_block():
    o = DeliveryOrchestrator(make_item(acceptance_criteria=()))
    req = add(o, "req", EvidenceType.REQUIREMENT_EVIDENCE, R.BUSINESS_ANALYST, "ba")
    with pytest.raises(GovernanceError, match="definition of ready"):
        transition(o, DeliveryState.REQUIREMENT_READY, R.BUSINESS_ANALYST, "ba", (req.evidence_id,))
    assert o.item.state_history == ()


def test_developer_cannot_self_approve_qa():
    o = prepared_for_dev()
    dev = add(o, "devtest", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "same",
              timestamp="2026-01-01T01:03:00+00:00")
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "same", (dev.evidence_id,), 3)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "same", minute=4)
    qa = add(o, "qa", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "same",
             timestamp="2026-01-01T01:05:00+00:00")
    with pytest.raises(GovernanceError, match="self-approve"):
        transition(o, DeliveryState.QA_PASSED, R.QA_ENGINEER, "same", (qa.evidence_id,), 5)


def test_qa_failed_returns_to_development_and_severe_defect_blocks_pass():
    o = prepared_for_dev()
    dev = add(o, "devtest", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "dev",
              timestamp="2026-01-01T01:03:00+00:00")
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (dev.evidence_id,), 3)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=4)
    fail = add(o, "qa-fail", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa", EvidenceStatus.FAIL,
               timestamp="2026-01-01T01:05:00+00:00")
    defect_e = add(o, "defect-e", EvidenceType.DEFECT_EVIDENCE, R.QA_ENGINEER, "qa",
                   timestamp="2026-01-01T01:04:30+00:00")
    defect = Defect("D-1", o.item.work_item_id, DefectSeverity.S1, "unsafe condition",
                    ("perform bounded input",), "reject", "accepted", (defect_e.evidence_id,))
    o.add_defect(defect, actor_role=R.QA_ENGINEER, actor="qa",
                 timestamp="2026-01-01T01:05:30+00:00", reason="reproduced QA defect")
    transition(o, DeliveryState.QA_FAILED, R.QA_ENGINEER, "qa", (fail.evidence_id, defect_e.evidence_id), 6)
    transition(o, DeliveryState.IN_DEVELOPMENT, R.BACKEND_DEVELOPER, "dev", minute=7)
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (dev.evidence_id,), 8)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=9)
    qa = add(o, "qa-pass", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
             timestamp="2026-01-01T01:10:00+00:00")
    with pytest.raises(GovernanceError, match="unresolved S1/S2"):
        transition(o, DeliveryState.QA_PASSED, R.QA_ENGINEER, "qa", (qa.evidence_id,), 11)


def test_qa_retest_and_new_adversarial_pass_required_after_fix():
    o = prepared_for_dev()
    dev = add(o, "dev0", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "dev",
              timestamp="2026-01-01T01:03:00+00:00")
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (dev.evidence_id,), 3)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=4)
    qa_fail = add(o, "qa-fail", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
                  EvidenceStatus.FAIL, timestamp="2026-01-01T01:05:00+00:00")
    de = add(o, "defect", EvidenceType.DEFECT_EVIDENCE, R.QA_ENGINEER, "qa",
             timestamp="2026-01-01T01:04:30+00:00")
    d = Defect("D-1", o.item.work_item_id, DefectSeverity.S2, "bug", ("reproduce",),
               "reject", "accept", (de.evidence_id,))
    o.add_defect(d, actor_role=R.QA_ENGINEER, actor="qa",
                 timestamp="2026-01-01T01:05:30+00:00", reason="QA reproduced defect")
    transition(o, DeliveryState.QA_FAILED, R.QA_ENGINEER, "qa", (qa_fail.evidence_id, de.evidence_id), 6)
    transition(o, DeliveryState.IN_DEVELOPMENT, R.BACKEND_DEVELOPER, "dev", minute=7)
    o.advance_defect("D-1", DefectStatus.FIX_IN_PROGRESS, actor_role=R.BACKEND_DEVELOPER,
                     actor="dev", timestamp="2026-01-01T01:07:30+00:00", reason="fix started")
    fix = add(o, "fix", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "dev",
              timestamp="2026-01-01T01:08:00+00:00")
    o.advance_defect("D-1", DefectStatus.READY_FOR_RETEST, actor_role=R.BACKEND_DEVELOPER,
                     actor="dev", timestamp="2026-01-01T01:08:30+00:00", reason="fix validated",
                     evidence_ref=fix.evidence_id)
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (fix.evidence_id,), 9)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=10)
    retest = add(o, "retest", EvidenceType.QA_RETEST_EVIDENCE, R.QA_ENGINEER, "qa",
                 timestamp="2026-01-01T01:11:00+00:00")
    o.advance_defect("D-1", DefectStatus.RETEST_PASSED, actor_role=R.QA_ENGINEER,
                     actor="qa", timestamp="2026-01-01T01:11:30+00:00", reason="retest passed",
                     evidence_ref=retest.evidence_id)
    o.advance_defect("D-1", DefectStatus.CLOSED, actor_role=R.QA_ENGINEER,
                     actor="qa", timestamp="2026-01-01T01:12:00+00:00", reason="regression passed",
                     regression_result="regression suite passed")
    stale_pass = add(o, "stale-pass", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
                     timestamp="2026-01-01T01:13:00+00:00")
    with pytest.raises(GovernanceError, match="new adversarial"):
        transition(o, DeliveryState.QA_PASSED, R.QA_ENGINEER, "qa", (stale_pass.evidence_id,), 14)
    adversarial = add(o, "attack", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
                      refs=(retest.evidence_id,), timestamp="2026-01-01T01:15:00+00:00")
    transition(o, DeliveryState.QA_PASSED, R.QA_ENGINEER, "qa", (adversarial.evidence_id,), 16)
    assert adversarial.status == EvidenceStatus.PASS
    assert o.item.defects[0].status == DefectStatus.CLOSED


def test_qa_cannot_reuse_evidence_from_before_a_new_development_cycle():
    o = prepared_for_dev()
    dev0 = add(o, "dev0", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "dev",
               timestamp="2026-01-01T01:03:00+00:00")
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (dev0.evidence_id,), 3)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=4)
    stale = add(o, "old-qa", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
                timestamp="2026-01-01T01:05:00+00:00")
    failed = add(o, "qa-fail", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
                 EvidenceStatus.FAIL, timestamp="2026-01-01T01:05:30+00:00")
    defect_e = add(o, "defect-e", EvidenceType.DEFECT_EVIDENCE, R.QA_ENGINEER, "qa",
                   timestamp="2026-01-01T01:05:20+00:00")
    defect = Defect("D-STALE", o.item.work_item_id, DefectSeverity.S4, "minor defect",
                    ("reproduce",), "expected", "actual", (defect_e.evidence_id,))
    o.add_defect(defect, actor_role=R.QA_ENGINEER, actor="qa",
                 timestamp="2026-01-01T01:05:40+00:00", reason="logged for fix")
    transition(o, DeliveryState.QA_FAILED, R.QA_ENGINEER, "qa",
               (failed.evidence_id, defect_e.evidence_id), 6)
    transition(o, DeliveryState.IN_DEVELOPMENT, R.BACKEND_DEVELOPER, "dev", minute=7)
    dev1 = add(o, "dev1", EvidenceType.DEV_TEST_EVIDENCE, R.BACKEND_DEVELOPER, "dev",
               timestamp="2026-01-01T01:08:00+00:00")
    transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev", (dev1.evidence_id,), 9)
    transition(o, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=10)
    current_qa = add(o, "late-old-qa", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
                     timestamp=stale.timestamp)
    with pytest.raises(GovernanceError, match="stale lifecycle evidence"):
        transition(o, DeliveryState.QA_PASSED, R.QA_ENGINEER, "qa", (current_qa.evidence_id,), 11)


def test_ci_missing_or_red_checks_do_not_allow_green():
    o, _ = ready_for_pr_open()
    gaps, _ = o._lifecycle_gaps(include_ci=True)
    assert "G6_CI:BLOCKED" in gaps
    missing = add(o, "ci1", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
                  checks=(("unit", "SUCCESS"),), timestamp="2026-01-01T01:12:00+00:00")
    with pytest.raises(GovernanceError, match="missing"):
        transition(o, DeliveryState.CI_GREEN, R.RELEASE_MANAGER, "rm", (missing.evidence_id,), 12)
    red = add(o, "ci2", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
              checks=(("unit", "SUCCESS"), ("lint", "CANCELLED")), timestamp="2026-01-01T01:13:00+00:00")
    with pytest.raises(GovernanceError, match="not proven successful"):
        transition(o, DeliveryState.CI_GREEN, R.RELEASE_MANAGER, "rm", (red.evidence_id,), 14)


def test_merge_approval_cannot_select_superseded_release_evidence():
    o, release = ready_for_pr_open()
    ci = add(o, "ci", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
             checks=(("unit", "SUCCESS"), ("lint", "SUCCESS")), timestamp="2026-01-01T01:12:00+00:00")
    transition(o, DeliveryState.CI_GREEN, R.RELEASE_MANAGER, "rm", (ci.evidence_id,), 12)
    failed_release = add(o, "release-fail", EvidenceType.RELEASE_EVIDENCE, R.RELEASE_MANAGER, "rm",
                         EvidenceStatus.FAIL, timestamp="2026-01-01T01:13:00+00:00")
    with pytest.raises(GovernanceError):
        transition(o, DeliveryState.MERGE_APPROVED, R.RELEASE_MANAGER, "rm", (release.evidence_id,), 14)
    assert o.item.current_state == DeliveryState.CI_GREEN
    assert failed_release.status == EvidenceStatus.FAIL


def test_merge_approval_is_removed_when_latest_ci_result_turns_red():
    o, release = ready_for_pr_open()
    ci_green = add(o, "ci-green", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
                   checks=(("unit", "SUCCESS"), ("lint", "SUCCESS")),
                   timestamp="2026-01-01T01:12:00+00:00")
    transition(o, DeliveryState.CI_GREEN, R.RELEASE_MANAGER, "rm",
               (ci_green.evidence_id,), 12)
    ci_red = add(o, "ci-red", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
                 EvidenceStatus.FAIL,
                 checks=(("unit", "SUCCESS"), ("lint", "FAILURE")),
                 timestamp="2026-01-01T01:13:00+00:00")
    assert "MERGE_APPROVED" not in o.allowed_next_states()
    with pytest.raises(GovernanceError, match="merge gates blocked"):
        transition(o, DeliveryState.MERGE_APPROVED, R.RELEASE_MANAGER, "rm",
                   (release.evidence_id,), 14)
    transition(o, DeliveryState.CI_FAILED, R.RELEASE_MANAGER, "rm",
               (ci_red.evidence_id,), 15)
    assert o.item.current_state == DeliveryState.CI_FAILED


def test_na_without_reason_and_reference_is_rejected():
    o = ready_for_uat(prepared_for_dev())
    ev = Evidence("na", o.item.work_item_id, EvidenceType.UAT_EVIDENCE, R.UAT_REVIEWER, "uat",
                  "2026-01-01T00:00:00+00:00", EvidenceStatus.NOT_APPLICABLE, "", ())
    with pytest.raises(GovernanceError, match="N/A"):
        o.add_evidence(ev)


def test_history_tampering_and_unknown_schema_keys_fail():
    o = prepared_for_dev()
    data = work_item_to_dict(o.item)
    data["current_state"] = "MERGED"
    with pytest.raises(ValueError, match="does not match"):
        work_item_from_dict(data)
    data = work_item_to_dict(o.item)
    data["surprise"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        work_item_from_dict(data)
    data = work_item_to_dict(o.item)
    data["state_history"][0]["reason"] = "rewritten"
    with pytest.raises(ValueError, match="hash"):
        work_item_from_dict(data)
    with pytest.raises(ValueError, match="evidence history sequence/hash chain"):
        DeliveryOrchestrator(replace(o.item, evidence=tuple(reversed(o.item.evidence))))


def test_evidence_hash_detects_mutation_and_wrong_work_item():
    o = DeliveryOrchestrator(make_item())
    e = add(o, "req", EvidenceType.REQUIREMENT_EVIDENCE, R.BUSINESS_ANALYST, "ba")
    tampered = replace(e, summary="forged")
    with pytest.raises(ValueError, match="hash"):
        DeliveryOrchestrator(replace(o.item, evidence=(tampered,)))
    with pytest.raises(GovernanceError, match="different work item"):
        o.add_evidence(replace(e, evidence_id="other", work_item_id="OTHER", content_hash=""))
    changed_contract = replace(o.item, business_goal="a different requirement")
    assert DeliveryOrchestrator(changed_contract).contract_drift is False  # No recorded transition yet.


def test_duplicate_evidence_ids_are_rejected():
    o = DeliveryOrchestrator(make_item())
    add(o, "req", EvidenceType.REQUIREMENT_EVIDENCE, R.BUSINESS_ANALYST, "ba")
    duplicate = Evidence("req", o.item.work_item_id, EvidenceType.REQUIREMENT_EVIDENCE,
                         R.BUSINESS_ANALYST, "ba", "2026-01-01T00:01:00+00:00",
                         EvidenceStatus.PASS, "duplicate", ("evidence://duplicate",))
    with pytest.raises(GovernanceError, match="unique"):
        o.add_evidence(duplicate)


def test_scope_change_invalidates_prior_proofs_and_requires_requirement_block_reentry():
    o = prepared_for_dev()
    o = DeliveryOrchestrator(replace(o.item, expected_behavior="a revised contract"))
    assert o.contract_drift
    assert o.allowed_next_states() == ("BLOCKED_REQUIREMENT",)
    with pytest.raises(GovernanceError, match="contract changed"):
        transition(o, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev")
    block = add(o, "revise-block", EvidenceType.REQUIREMENT_EVIDENCE,
                R.BUSINESS_ANALYST, "ba", EvidenceStatus.BLOCKED,
                summary="scope changed; prior approvals invalidated")
    transition(o, DeliveryState.BLOCKED_REQUIREMENT, R.BUSINESS_ANALYST, "ba",
               (block.evidence_id,), 3)
    assert not o.contract_drift
    req = add(o, "req-revised", EvidenceType.REQUIREMENT_EVIDENCE,
              R.BUSINESS_ANALYST, "ba", timestamp="2026-01-01T01:04:00+00:00")
    transition(o, DeliveryState.REQUIREMENT_READY, R.BUSINESS_ANALYST, "ba",
               (req.evidence_id,), 4)


def test_governance_package_has_no_broker_or_order_imports():
    from pathlib import Path
    import ast
    root = Path(__file__).parents[2] / "core" / "delivery"
    forbidden = ("core.broker", "broker", "order", "execution", "strategies")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(any(token in name.lower() for token in forbidden) for name in imports), path


def test_json_serialization_is_deterministic():
    item = make_item()
    assert canonical_json(work_item_to_dict(item)) == canonical_json(work_item_to_dict(item))


def test_cli_create_validate_and_refuse_overwrite(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "governance/evidence/work_items/FTR-CLI.json"
    path.parent.mkdir(parents=True)
    epic_path = path.parent / "EPIC-CLI.json"
    assert delivery_cli(["create", str(epic_path), "EPIC-CLI", "EPIC", "CLI epic"]) == 0
    capsys.readouterr()
    assert delivery_cli(["create", str(path), "FTR-CLI", "FEATURE", "CLI work",
                         "--parent-epic", "EPIC-CLI"]) == 0
    capsys.readouterr()
    assert delivery_cli(["validate", str(path)]) == 0
    result = __import__("json").loads(capsys.readouterr().out)
    assert result["valid"] is True
    assert result["scope"] == "structural_only"
    assert result["research_capture_authorized"] is False
    before = path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        delivery_cli(["create", str(path), "FTR-CLI", "FEATURE", "overwrite",
                      "--parent-epic", "EPIC-CLI"])
    assert exc.value.code == 2
    assert path.read_bytes() == before


def test_cli_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "malformed.json"
    path.write_text('{"work_item_id":"x","work_item_id":"y"}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        delivery_cli(["validate", str(path)])
    assert exc.value.code == 2


def test_ci_gate_blocks_when_no_required_check_names_are_configured():
    evidence = Evidence("ci", "FTR-1", EvidenceType.CI_EVIDENCE, R.RELEASE_MANAGER, "rm",
                        "2026-01-01T00:00:00+00:00", EvidenceStatus.PASS, "CI reported success",
                        ("ci://run/1",), check_results=(("unit", "SUCCESS"),))
    result = evaluate_gate(GateName.G6_CI, (evidence,), ())
    assert result.status == GateStatus.BLOCKED
    assert "no required CI checks" in result.reason


def _capture_item_with_pending_request(tmp_path, monkeypatch, *, close_unknown=False):
    from datetime import datetime, timezone
    from pathlib import Path
    from core.delivery.research_request_capture import append_event, locked_sidecar, make_event
    from core.delivery.cli import _write_atomic

    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence.txt").write_text("local metadata reference\n", encoding="utf-8")
    path = tmp_path / "STORY-CAPTURE.json"
    item = make_item(allowed_paths=("evidence.txt",))
    _write_atomic(path, item)
    scope_ref = "00000000-0000-0000-0000-000000000001"
    route_ref = "00000000-0000-0000-0000-000000000002"
    request_id = "00000000-0000-0000-0000-000000000003"
    with locked_sidecar(Path(str(path) + ".lock"), create=True) as fd:
        preflight = make_event(item, "ROUTE_PREFLIGHT", {
            "route_ref": route_ref, "request_scope": "DOCS_ONLY", "scope_ref": scope_ref,
            "route_class": "STATIC_METADATA", "result": "PASS",
            "evidence_refs": ["repo:evidence.txt#sha256:" + "a" * 64], "reason_code": "NONE"},
            now=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc))
        item = append_event(path, fd, preflight)
        prepared = make_event(item, "REQUEST_PREPARED", {
            "request_id": request_id, "route_preflight_event_id": preflight["event_id"],
            "request_scope": "DOCS_ONLY", "scope_ref": scope_ref,
            "request_class": "STATIC_METADATA"},
            now=datetime(2026, 1, 1, 1, 1, tzinfo=timezone.utc))
        item = append_event(path, fd, prepared)
        if close_unknown:
            result = make_event(item, "REQUEST_RESULT", {
                "request_id": request_id, "prepared_event_id": prepared["event_id"],
                "result_status": "UNKNOWN", "access_category": "UNKNOWN"},
                now=datetime(2026, 1, 1, 1, 2, tzinfo=timezone.utc))
            item = append_event(path, fd, result)
    from core.delivery.research_request_capture import _read_canonical
    return _read_canonical(path)[1]


def test_pending_research_request_blocks_orchestrator_transitions(tmp_path, monkeypatch):
    item = _capture_item_with_pending_request(tmp_path, monkeypatch)
    orchestrator = DeliveryOrchestrator(item)
    assert orchestrator.allowed_next_states() == ()
    with pytest.raises(GovernanceError, match="pending research request"):
        orchestrator.transition(DeliveryState.BLOCKED_REQUIREMENT,
                                acting_role=R.BUSINESS_ANALYST, actor="ba",
                                timestamp="2026-01-01T02:00:00+00:00", reason="test")


def test_terminal_research_result_blocks_orchestrator_writes(tmp_path, monkeypatch):
    item = _capture_item_with_pending_request(tmp_path, monkeypatch, close_unknown=True)
    orchestrator = DeliveryOrchestrator(item)
    assert orchestrator.allowed_next_states() == ()
    with pytest.raises(GovernanceError, match="terminal research freeze"):
        orchestrator.transition(DeliveryState.BLOCKED_REQUIREMENT,
                                acting_role=R.BUSINESS_ANALYST, actor="ba",
                                timestamp="2026-01-01T02:00:00+00:00", reason="test")


def _journal_work_item(path, item):
    from core.delivery.cli import _write_atomic
    from core.delivery.research_request_capture import append_event, locked_sidecar, make_event, _read_canonical

    path.parent.mkdir(parents=True, exist_ok=True)
    path.parents[3].joinpath("evidence.txt").write_text("local test evidence\n", encoding="utf-8")
    _write_atomic(path, item)
    lock_path = path.with_name(path.name + ".lock")
    with locked_sidecar(lock_path, create=True) as fd:
        _, current, _ = _read_canonical(path)
        preflight = make_event(current, "ROUTE_PREFLIGHT", {
            "route_ref": "00000000-0000-0000-0000-000000000041", "request_scope": "DOCS_ONLY",
            "scope_ref": "00000000-0000-0000-0000-000000000042", "route_class": "STATIC_METADATA",
            "result": "PASS", "evidence_refs": ["repo:evidence.txt#sha256:" + "a" * 64],
            "reason_code": "NONE"}, now=datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc))
        append_event(path, fd, preflight)
    return lock_path


def test_post_init_requirement_evidence_and_transition_survive_restart(tmp_path, monkeypatch):
    from core.delivery.research_request_capture import (
        _load_journal, _read_canonical, locked_sidecar, persist_work_item, research_status,
    )

    monkeypatch.chdir(tmp_path)
    item = make_item(allowed_paths=("evidence.txt",))
    path = tmp_path / "governance/evidence/work_items" / f"{item.work_item_id}.json"
    lock_path = _journal_work_item(path, item)
    with locked_sidecar(lock_path, create=False) as fd:
        raw, base, _ = _read_canonical(path)
        orchestrator = DeliveryOrchestrator(base)
        requirement = add(orchestrator, "journal-ba", EvidenceType.REQUIREMENT_EVIDENCE,
                          R.BUSINESS_ANALYST, "ba")
        persist_work_item(path, fd, raw, base, orchestrator.item, "EVIDENCE_UPDATE")
        raw, base, _ = _read_canonical(path)
        orchestrator = DeliveryOrchestrator(base)
        updated = transition(orchestrator, DeliveryState.REQUIREMENT_READY, R.BUSINESS_ANALYST,
                             "ba", (requirement.evidence_id,), minute=1)
        persist_work_item(path, fd, raw, base, updated, "LIFECYCLE_UPDATE")
        records = _load_journal(fd)
        final_raw, final_item, _ = _read_canonical(path)

    assert final_item.current_state == DeliveryState.REQUIREMENT_READY
    assert len(final_item.evidence) == 1
    assert final_item.state_history[-1].to_state == DeliveryState.REQUIREMENT_READY.value
    assert records[-4]["operation"] == "EVIDENCE_UPDATE"
    assert records[-2]["operation"] == "LIFECYCLE_UPDATE"
    assert records[-1]["resulting_canonical_sha256"] == hashlib.sha256(final_raw).hexdigest()
    status, code = research_status(item.work_item_id, root=tmp_path)
    assert code == 0 and status["status"] == "READY"
    assert status["capture_allowed"] is True


def test_post_init_defect_and_history_mutations_survive_restart(tmp_path, monkeypatch):
    from core.delivery.research_request_capture import (
        _load_journal, _read_canonical, locked_sidecar, persist_work_item, research_status,
    )

    monkeypatch.chdir(tmp_path)
    orchestrator = prepared_for_dev(allowed_paths=("evidence.txt",))
    item = orchestrator.item
    path = tmp_path / "governance/evidence/work_items" / f"{item.work_item_id}.json"
    lock_path = _journal_work_item(path, item)

    def mutate(operation, callback):
        with locked_sidecar(lock_path, create=False) as fd:
            raw, base, _ = _read_canonical(path)
            current = DeliveryOrchestrator(base)
            updated = callback(current)
            if updated is None:
                updated = current.item
            persist_work_item(path, fd, raw, base, updated, operation)

    mutate("EVIDENCE_UPDATE", lambda current: add(
        current, "journal-dev-test", EvidenceType.DEV_TEST_EVIDENCE,
        R.BACKEND_DEVELOPER, "dev", timestamp="2026-01-01T01:03:00+00:00") and current.item)
    mutate("LIFECYCLE_UPDATE", lambda current: transition(
        current, DeliveryState.DEV_VERIFIED, R.BACKEND_DEVELOPER, "dev",
        ("journal-dev-test",), minute=3))
    mutate("LIFECYCLE_UPDATE", lambda current: transition(
        current, DeliveryState.QA_IN_PROGRESS, R.QA_ENGINEER, "qa", minute=4))

    def add_qa_proofs(current):
        add(current, "journal-qa-fail", EvidenceType.QA_EVIDENCE, R.QA_ENGINEER, "qa",
            EvidenceStatus.FAIL, timestamp="2026-01-01T01:05:00+00:00")
        add(current, "journal-defect-proof", EvidenceType.DEFECT_EVIDENCE, R.QA_ENGINEER, "qa",
            timestamp="2026-01-01T01:04:30+00:00")
        return current.item
    mutate("EVIDENCE_UPDATE", add_qa_proofs)

    def create_defect(current):
        defect = Defect("JOURNAL-D1", current.item.work_item_id, DefectSeverity.S1,
                        "journal recovery defect", ("reproduce",), "reject", "accepted",
                        ("journal-defect-proof",))
        current.add_defect(defect, actor_role=R.QA_ENGINEER, actor="qa",
                           timestamp="2026-01-01T01:05:30+00:00", reason="QA reproduced defect")
        return current.item
    mutate("DEFECT_UPDATE", create_defect)
    mutate("LIFECYCLE_UPDATE", lambda current: transition(
        current, DeliveryState.QA_FAILED, R.QA_ENGINEER, "qa",
        ("journal-qa-fail", "journal-defect-proof"), minute=6))
    mutate("LIFECYCLE_UPDATE", lambda current: transition(
        current, DeliveryState.IN_DEVELOPMENT, R.BACKEND_DEVELOPER, "dev", minute=7))
    mutate("HISTORY_UPDATE", lambda current: current.advance_defect(
        "JOURNAL-D1", DefectStatus.FIX_IN_PROGRESS, actor_role=R.BACKEND_DEVELOPER,
        actor="dev", timestamp="2026-01-01T01:07:30+00:00", reason="fix started"))

    with locked_sidecar(lock_path, create=False) as fd:
        records = _load_journal(fd)
        final_raw, final_item, _ = _read_canonical(path)
    operations = [records[i]["operation"] for i in range(1, len(records), 2)]
    assert "EVIDENCE_UPDATE" in operations
    assert "DEFECT_UPDATE" in operations
    assert "HISTORY_UPDATE" in operations
    assert operations.count("LIFECYCLE_UPDATE") >= 4
    assert final_item.current_state == DeliveryState.IN_DEVELOPMENT
    assert final_item.defects[0].status == DefectStatus.FIX_IN_PROGRESS
    assert records[-1]["resulting_canonical_sha256"] == hashlib.sha256(final_raw).hexdigest()
    status, code = research_status(item.work_item_id, root=tmp_path)
    assert code == 0 and status["status"] == "READY"
    assert status["capture_allowed"] is True
