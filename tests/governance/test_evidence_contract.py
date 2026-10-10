from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from core.delivery.evidence import seal_evidence
from core.delivery.evidence_standard import (
    GATES,
    validate_claim_registry,
    validate_evidence_standard_record,
    validate_source_registry,
    validate_subject_commit,
)
from core.delivery.models import (DeliveryState, Evidence, EvidenceStatus, EvidenceType,
                                  WorkItem, WorkItemType)
from core.delivery.orchestrator import DeliveryOrchestrator
from core.delivery.roles import DeliveryRole
from core.delivery.validators import validate_work_item
from core.delivery.validators import work_item_contract_hash
import tools.verify_evidence as evidence_tool
from tools.verify_evidence import _local_source_exists, build_report, main, render_summary
from tools.verify_evidence import _path_matches, _prefixes_overlap


SUBJECT_SHA = "a" * 40
ARTIFACT_SHA = "b" * 64


def _standard(*, status: str = "VERIFIED", subject_sha: str | None = SUBJECT_SHA) -> dict:
    return {
        "schema_version": 1,
        "enforcement_mode": "REPORT_ONLY",
        "applicability": "REQUIRED",
        "applicability_reason": "A material calculation claim is in scope.",
        "assessed_paths": ["core/example.py"],
        "subject_commit_sha": subject_sha,
        "claims": [{
            "claim_id": "TEST-CLAIM",
            "statement": "The calculation matches the independent reference over the tested domain.",
            "claim_kind": "mathematical",
            "status": status,
            "source_ids": ["TEST-SOURCE"],
            "evidence_refs": ["ev-source"],
            "assumptions": [{"assumption_id": "A1", "statement": "Input domain is finite and documented.",
                             "classification": "THEORETICAL_ASSUMPTION", "source_ids": ["TEST-SOURCE"]}],
            "gate_evidence": {
                "G1_SOURCE": "ev-source",
                "G2_CORRECTNESS": "ev-correctness",
                "G3_ADVERSARIAL": "ev-adversarial",
                "G4_INDEPENDENT": "ev-independent",
            } if status != "NOT_APPLICABLE" else {},
            "limitation": "Independent production observations remain outside this test claim." if status != "VERIFIED" else "",
        }],
    }


def _item(*, status: str = "VERIFIED", authors: dict[str, str] | None = None,
          failed_gate: str | None = None, include_developer: bool = False) -> WorkItem:
    authors = authors or {}
    item = WorkItem(
        work_item_id="TASK-TEST-001", type=WorkItemType.TASK, parent_epic="EPIC-TEST",
        parent_feature="FEATURE-TEST", title="Test evidence contract",
        extensions={"evidence_standard": _standard(status=status)},
    )
    contract_hash = work_item_contract_hash(item)
    gate_evidence = [
        ("G1_SOURCE", "ev-source", EvidenceType.SOURCE_VERIFICATION_EVIDENCE,
         DeliveryRole.BUSINESS_ANALYST, "ba", ("TEST-SOURCE", "spec.md")),
        ("G2_CORRECTNESS", "ev-correctness", EvidenceType.CORRECTNESS_VERIFICATION_EVIDENCE,
         DeliveryRole.QA_ENGINEER, "qa-correctness", (f"tests/reference.py#sha256:{ARTIFACT_SHA}",)),
        ("G3_ADVERSARIAL", "ev-adversarial", EvidenceType.ADVERSARIAL_VERIFICATION_EVIDENCE,
         DeliveryRole.SENIOR_QA, "qa-adversarial", (f"tests/mutation.py#sha256:{ARTIFACT_SHA}",)),
        ("G4_INDEPENDENT", "ev-independent", EvidenceType.INDEPENDENT_EVIDENCE,
         DeliveryRole.UAT_REVIEWER, "uat-reviewer", (f"artifact/result.json#sha256:{ARTIFACT_SHA}",)),
    ]
    sealed = []
    previous_hash = "0" * 64
    for seq, (gate, evidence_id, evidence_type, role, author, refs) in enumerate(gate_evidence, start=1):
        author = authors.get(gate, author)
        evidence = Evidence(
            evidence_id=evidence_id, work_item_id=item.work_item_id, evidence_type=evidence_type,
            role=role, author=author, timestamp=f"2026-10-10T09:00:{seq:02d}+05:30",
            status=EvidenceStatus.FAIL if gate == failed_gate else EvidenceStatus.PASS,
            summary=f"Evidence for {gate}", references=refs,
        )
        evidence = seal_evidence(evidence, contract_hash, seq, previous_hash)
        sealed.append(evidence)
        previous_hash = evidence.content_hash
    if include_developer:
        evidence = Evidence(
            evidence_id="ev-developer", work_item_id=item.work_item_id,
            evidence_type=EvidenceType.DEV_TEST_EVIDENCE, role=DeliveryRole.BACKEND_DEVELOPER,
            author="same-person", timestamp="2026-10-10T09:00:05+05:30",
            status=EvidenceStatus.PASS, summary="Developer checks", references=("tests/unit.py",),
        )
        sealed.append(seal_evidence(evidence, contract_hash, len(sealed) + 1, previous_hash))
    return replace(item, evidence=tuple(sealed))


def _complete_lifecycle_item(candidate_sha: str, *, include_lifecycle_evidence: bool) -> WorkItem:
    """Build a test-only complete work item using the production delivery API."""
    standard = _standard(status="UNVERIFIED", subject_sha=candidate_sha)
    standard["assessed_paths"] = ["core/delivery/"]
    standard["claims"][0]["gate_evidence"] = {}
    item = WorkItem(
        work_item_id="TASK-COMPLETE-TEST", type=WorkItemType.TASK,
        parent_epic="EPIC-TEST", parent_feature="FEATURE-TEST", title="Lifecycle verifier fixture",
        priority="P1", business_goal="Verify lifecycle evidence enforcement",
        current_behavior="Verifier accepts incomplete work items",
        expected_behavior="Verifier requires completed lifecycle evidence",
        in_scope=("core/delivery/",), out_of_scope=("trading runtime",),
        acceptance_criteria=("incomplete lifecycle evidence is blocked",),
        safety_constraints=("read-only verification", "no trading actions"),
        architecture_impact="offline governance test fixture",
        allowed_paths=("core/delivery/",), forbidden_paths=("core/broker/",),
        expected_tests=("tests/governance/test_evidence_contract.py",),
        qa_attack_plan=("missing roles", "missing stage evidence"),
        uat_criteria=("missing evidence remains blocked",),
        release_gates=("required delivery evidence is present",),
        rollback_plan="Remove the offline verifier rule.", required_ci_checks=("unit",),
        extensions={"evidence_standard": standard},
    )
    orchestrator = DeliveryOrchestrator(item)
    if not include_lifecycle_evidence:
        return item

    def stamp(minute: int) -> str:
        return f"2026-02-01T00:{minute:02d}:00+00:00"

    def evidence(evidence_id: str, kind: EvidenceType, role: DeliveryRole, author: str,
                 minute: int) -> Evidence:
        candidate = Evidence(evidence_id, orchestrator.item.work_item_id, kind, role, author,
                             stamp(minute), EvidenceStatus.PASS, f"{evidence_id} test evidence",
                             (f"test-artifact://{evidence_id}",))
        orchestrator.add_evidence(candidate)
        return orchestrator.item.evidence[-1]

    def transition(target: DeliveryState, role: DeliveryRole, actor: str, minute: int,
                   evidence_ids: tuple[str, ...] = ()) -> None:
        orchestrator.transition(target, acting_role=role, actor=actor, timestamp=stamp(minute),
                                reason=f"test fixture evidence for {target.value}",
                                evidence_ids=evidence_ids)

    req_ba = evidence("req-ba", EvidenceType.REQUIREMENT_EVIDENCE,
                      DeliveryRole.BUSINESS_ANALYST, "ba", 0)
    transition(DeliveryState.REQUIREMENT_READY, DeliveryRole.BUSINESS_ANALYST, "ba", 1,
               (req_ba.evidence_id,))
    req_po = evidence("req-po", EvidenceType.REQUIREMENT_EVIDENCE,
                      DeliveryRole.PRODUCT_OWNER, "po", 2)
    architecture = evidence("architecture", EvidenceType.ARCHITECTURE_EVIDENCE,
                            DeliveryRole.SYSTEM_ARCHITECT, "architect", 3)
    transition(DeliveryState.DESIGN_READY, DeliveryRole.SYSTEM_ARCHITECT, "architect", 4,
               (req_ba.evidence_id, req_po.evidence_id, architecture.evidence_id))
    transition(DeliveryState.IN_DEVELOPMENT, DeliveryRole.BACKEND_DEVELOPER, "dev", 5)
    dev = evidence("dev-tests", EvidenceType.DEV_TEST_EVIDENCE,
                   DeliveryRole.BACKEND_DEVELOPER, "dev", 6)
    transition(DeliveryState.DEV_VERIFIED, DeliveryRole.BACKEND_DEVELOPER, "dev", 7,
               (dev.evidence_id,))
    transition(DeliveryState.QA_IN_PROGRESS, DeliveryRole.QA_ENGINEER, "qa", 8)
    qa = evidence("qa", EvidenceType.QA_EVIDENCE, DeliveryRole.QA_ENGINEER, "qa", 9)
    transition(DeliveryState.QA_PASSED, DeliveryRole.QA_ENGINEER, "qa", 10, (qa.evidence_id,))
    senior = evidence("senior-qa", EvidenceType.SENIOR_QA_EVIDENCE,
                      DeliveryRole.SENIOR_QA, "senior", 11)
    transition(DeliveryState.SENIOR_QA, DeliveryRole.SENIOR_QA, "senior", 12,
               (senior.evidence_id,))
    transition(DeliveryState.UAT, DeliveryRole.SENIOR_QA, "senior", 13, (senior.evidence_id,))
    uat = evidence("uat", EvidenceType.UAT_EVIDENCE, DeliveryRole.UAT_REVIEWER, "uat", 14)
    product = evidence("product", EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE,
                       DeliveryRole.PRODUCT_OWNER, "po", 15)
    transition(DeliveryState.PRODUCT_ACCEPTED, DeliveryRole.PRODUCT_OWNER, "po", 16,
               (uat.evidence_id, product.evidence_id))
    release = evidence("release", EvidenceType.RELEASE_EVIDENCE,
                       DeliveryRole.RELEASE_MANAGER, "release", 17)
    transition(DeliveryState.RELEASE_READY, DeliveryRole.RELEASE_MANAGER, "release", 18,
               (release.evidence_id,))
    return orchestrator.item


def _patch_current_material_record(monkeypatch, item: WorkItem, candidate_sha: str) -> None:
    monkeypatch.setattr(evidence_tool, "changed_paths",
                        lambda *args, **kwargs: ["core/delivery/models.py"])
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    monkeypatch.setattr(evidence_tool, "work_item_from_dict", lambda payload: item)
    monkeypatch.setattr(evidence_tool, "validate_source_registry", lambda registry: {
        "TEST-SOURCE": {"status": "VERIFIED", "locator": "governance/evidence/POLICY.md"}
    })
    standard = item.extensions["evidence_standard"]
    monkeypatch.setattr(evidence_tool, "validate_claim_registry", lambda registry, sources: {
        claim["claim_id"]: {"claim_kind": claim["claim_kind"], "statement": claim["statement"],
                            "status": claim["status"], "source_ids": claim["source_ids"],
                            "scope_paths": ["core/delivery/"],
                            "limitation": claim.get("limitation", "")}
        for claim in standard["claims"]
    })


def test_existing_delivery_model_validates_four_gate_work_item():
    item = _item()
    validate_evidence_standard_record(item)
    validate_work_item(item)
    assert set(GATES) == {"G1_SOURCE", "G2_CORRECTNESS", "G3_ADVERSARIAL", "G4_INDEPENDENT"}


def test_linked_evidence_cannot_be_reused_after_work_item_contract_changes():
    item = _item()
    changed_standard = dict(item.extensions["evidence_standard"])
    changed_standard["assessed_paths"] = ["core/changed.py"]
    changed = replace(item, extensions={"evidence_standard": changed_standard})
    with pytest.raises(ValueError, match="older work-item contract hash"):
        validate_work_item(changed)


def test_missing_gate_evidence_cannot_be_marked_verified():
    item = _item()
    standard = dict(item.extensions["evidence_standard"])
    claim = dict(standard["claims"][0])
    claim["gate_evidence"] = {k: v for k, v in claim["gate_evidence"].items() if k != "G3_ADVERSARIAL"}
    standard["claims"] = [claim]
    with pytest.raises(ValueError, match="all four gates"):
        validate_evidence_standard_record(replace(item, extensions={"evidence_standard": standard}))


def test_failed_gate_cannot_be_promoted_to_verified_claim():
    with pytest.raises(ValueError, match="conflicts with failed or blocked"):
        validate_evidence_standard_record(_item(failed_gate="G3_ADVERSARIAL"))


def test_contradicted_claim_requires_a_referenced_failing_result():
    with pytest.raises(ValueError, match="requires a failing referenced gate"):
        validate_evidence_standard_record(_item(status="CONTRADICTED"))
    validate_evidence_standard_record(_item(status="CONTRADICTED", failed_gate="G3_ADVERSARIAL"))


def test_correctness_adversarial_and_independent_authors_must_be_distinct():
    with pytest.raises(ValueError, match="reviewers must be distinct"):
        validate_evidence_standard_record(_item(authors={"G3_ADVERSARIAL": "qa-correctness"}))


def test_independent_reviewer_cannot_be_developer_author():
    item = _item(authors={"G4_INDEPENDENT": "same-person"}, include_developer=True)
    with pytest.raises(ValueError, match="cannot be a developer author"):
        validate_evidence_standard_record(item)


def test_verified_claim_needs_hash_bound_artifacts_for_g2_g3_g4():
    item = _item()
    changed = list(item.evidence)
    changed[1] = replace(changed[1], references=("tests/reference.py",))
    changed[1] = seal_evidence(changed[1], changed[1].work_item_hash,
                               changed[1].sequence, changed[1].previous_hash)
    with pytest.raises(ValueError, match="SHA-256-bound artifact"):
        validate_evidence_standard_record(replace(item, evidence=tuple(changed)))


def test_not_applicable_requires_reason_and_cannot_hide_claims():
    item = WorkItem(work_item_id="TASK-NA", type=WorkItemType.TASK, parent_epic="E",
                    parent_feature="F", title="N/A evidence",
                    extensions={"evidence_standard": {
                        "schema_version": 1, "enforcement_mode": "REPORT_ONLY",
                        "applicability": "NOT_APPLICABLE",
                        "applicability_reason": "", "evidence_refs": ["ev-source"], "claims": [],
                    }})
    with pytest.raises(ValueError, match="explicit applicability_reason"):
        validate_evidence_standard_record(item)


@pytest.mark.parametrize("refs", [None, [], ["unknown-evidence"]])
def test_work_item_not_applicable_requires_known_supporting_evidence(refs):
    item = _item(status="UNVERIFIED")
    standard = {"schema_version": 1, "enforcement_mode": "REPORT_ONLY",
                "applicability": "NOT_APPLICABLE", "applicability_reason": "No material claim applies.",
                "evidence_refs": refs, "claims": []}
    with pytest.raises(ValueError, match="evidence_refs to known work-item evidence"):
        validate_evidence_standard_record(replace(item, extensions={"evidence_standard": standard}))


def test_work_item_not_applicable_accepts_known_supporting_evidence():
    item = _item(status="UNVERIFIED")
    standard = {"schema_version": 1, "enforcement_mode": "REPORT_ONLY",
                "applicability": "NOT_APPLICABLE", "applicability_reason": "No material claim applies.",
                "evidence_refs": ["ev-source"], "claims": []}
    validate_evidence_standard_record(replace(item, extensions={"evidence_standard": standard}))


def test_claim_not_applicable_requires_a_supporting_reference():
    item = _item(status="NOT_APPLICABLE")
    standard = dict(item.extensions["evidence_standard"])
    claim = dict(standard["claims"][0])
    claim["evidence_refs"] = []
    standard["claims"] = [claim]
    with pytest.raises(ValueError, match="supporting evidence_refs"):
        validate_evidence_standard_record(replace(item, extensions={"evidence_standard": standard}))


def test_assumptions_cannot_blur_facts_theory_and_empirical_hypotheses():
    item = _item(status="UNVERIFIED")
    standard = dict(item.extensions["evidence_standard"])
    claim = dict(standard["claims"][0])
    claim["assumptions"] = [{"assumption_id": "A1", "statement": "An untyped claim.",
                             "classification": "MAYBE", "source_ids": []}]
    standard["claims"] = [claim]
    with pytest.raises(ValueError, match="PUBLISHED_FACT, THEORETICAL_ASSUMPTION, or EMPIRICAL_HYPOTHESIS"):
        validate_evidence_standard_record(replace(item, extensions={"evidence_standard": standard}))


def test_registered_sources_reject_duplicates_and_unknown_claim_sources():
    sources = validate_source_registry({"schema_version": 1, "sources": [
        {"source_id": "SRC", "locator": "docs/spec.md", "source_type": "repository_policy",
         "authority": "test source", "status": "VERIFIED", "limitations": "fixture only"}
    ]})
    with pytest.raises(ValueError, match="unknown source"):
        validate_claim_registry({"schema_version": 1, "claims": [{
            "claim_id": "C", "statement": "Test claim", "claim_kind": "mathematical",
            "scope_paths": ["core/example.py"], "status": "UNVERIFIED",
            "source_ids": ["MISSING"], "evidence_refs": [], "limitation": "Not assessed.",
        }]}, sources)
    with pytest.raises(ValueError, match="unique"):
        validate_source_registry({"schema_version": 1, "sources": [
            {"source_id": "SRC", "locator": "a", "source_type": "repository_policy",
             "authority": "test source", "status": "VERIFIED", "limitations": "fixture"},
            {"source_id": "SRC", "locator": "b", "source_type": "repository_policy",
             "authority": "test source", "status": "VERIFIED", "limitations": "fixture"},
        ]})


def test_source_paths_cannot_escape_repository(tmp_path: Path):
    assert not _local_source_exists(tmp_path, "../outside.md")
    assert not _local_source_exists(tmp_path, str(tmp_path / "outside.md"))


def test_candidate_paths_reject_symlinked_inputs(tmp_path: Path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    external = tmp_path / "external.json"
    external.write_text('{"outside": true}')
    (candidate / "registry.json").symlink_to(external)
    assert evidence_tool._safe_candidate_path(candidate, "registry.json") is None
    with pytest.raises(ValueError, match="symlink"):
        evidence_tool._read_candidate_json(candidate, "registry.json")


def test_path_matching_uses_directory_boundaries_and_preserves_hidden_paths():
    assert not _path_matches("core/secret2.py", ["core/secret"])
    assert _path_matches("core/secret/key.py", ["core/secret/"])
    assert _path_matches(".hidden/file.py", [".hidden/"])
    assert not _path_matches("../core/file.py", ["core/"])
    assert not _path_matches("/core/file.py", ["core/"])
    assert not _prefixes_overlap("core/secret", "core/secret2.py")
    assert _prefixes_overlap("core/secret/", "core/secret/file.py")


def test_stale_or_mismatched_subject_commit_is_rejected():
    with pytest.raises(ValueError, match="does not match"):
        validate_subject_commit(_standard(), "d" * 40)
    validate_subject_commit(_standard(subject_sha=None), SUBJECT_SHA)


def test_registry_report_binds_exact_head_and_marks_legacy_unverified():
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head)
    assert report["candidate_sha"] == head
    assert report["candidate_root_sha"] == head
    assert report["verifier_source_sha"] == head
    assert report["enforcement_stage"] == "BLOCK_NEW_MATERIAL"
    assert report["work_items"][0]["candidate_sha"] == head
    assert report["work_items"][0]["record_sha256"]
    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False
    assert report["allowed_for_live_execution"] is False
    assert all(row["status"] == "UNVERIFIED" for row in report["legacy_inventory"])


def test_separate_candidate_root_requires_and_records_trusted_verifier_source_sha():
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head,
                          root=evidence_tool.ROOT, candidate_root=evidence_tool.ROOT,
                          candidate_root_sha=head,
                          verifier_source_sha=head)
    assert report["candidate_root_sha"] == head
    assert report["verifier_source_sha"] == head
    assert not any(row["code"].startswith("VERIFIER_SOURCE_SHA_") for row in report["findings"])


def test_separate_candidate_root_without_source_sha_fails_closed():
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head,
                          root=evidence_tool.ROOT, candidate_root=evidence_tool.ROOT,
                          verifier_source_sha=head)
    assert any(row["code"] == "CANDIDATE_ROOT_SHA_REQUIRED" for row in report["findings"])


def test_cli_passes_candidate_root_and_verifier_source_sha_to_report_builder(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    head = "a" * 40
    candidate_root = tmp_path / "candidate-tree"
    captured = {}

    def fake_build_report(**kwargs):
        captured.update(kwargs)
        return {"candidate_sha": head, "enforcement_stage": "BLOCK_NEW_MATERIAL",
                 "base_ref": head, "candidate_ref": head, "material_path_count": 0,
                "finding_count": 0, "findings": []}

    monkeypatch.setattr(evidence_tool, "build_report", fake_build_report)
    report_path = tmp_path / "report.json"
    assert main(["--base-ref", head, "--candidate-ref", head, "--candidate-sha", head,
                 "--candidate-root", str(candidate_root), "--verifier-source-sha", head,
                 "--candidate-root-sha", head,
                 "--output", str(report_path), "--mode", "enforce-new-material"]) == 0
    assert captured["candidate_root"] == candidate_root
    assert captured["candidate_root_sha"] == head
    assert captured["verifier_source_sha"] == head


@pytest.mark.parametrize(("rel_path", "expected_code"), [
    ("tools/verify_evidence.py", "VERIFIER_NOT_AT_CANDIDATE"),
    ("governance/evidence/SOURCE_REGISTRY.json", "EVIDENCE_INPUT_NOT_AT_CANDIDATE"),
    ("governance/evidence/CLAIM_REGISTRY.json", "EVIDENCE_INPUT_NOT_AT_CANDIDATE"),
    ("governance/evidence/VERIFICATION_MATRIX.json", "EVIDENCE_INPUT_NOT_AT_CANDIDATE"),
    ("governance/evidence/work_items/EVS-001.json", "EVIDENCE_INPUT_NOT_AT_CANDIDATE"),
    ("core/delivery/validators.py", "VERIFIER_DEPENDENCY_NOT_AT_CANDIDATE"),
])
def test_report_rejects_worktree_inputs_that_differ_from_candidate_tree(
        rel_path: str, expected_code: str, monkeypatch: pytest.MonkeyPatch):
    """Dirty and untracked policy inputs cannot be presented as candidate evidence."""
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    candidate_match = evidence_tool._candidate_file_matches

    def candidate_match_except_target(candidate_ref, path, local_path, *, cwd, **kwargs):
        if path == rel_path:
            return False
        return candidate_match(candidate_ref, path, local_path, cwd=cwd, **kwargs)

    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", candidate_match_except_target)
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head)
    assert any(row["code"] == expected_code and row["path"] == rel_path
               for row in report["findings"])


def test_report_downgrades_declared_verified_claim_to_unverified(
        monkeypatch: pytest.MonkeyPatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(evidence_tool, "work_item_from_dict", lambda payload: _item())
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head)
    assessment = report["work_items"][0]["claim_assessments"][0]
    assert assessment["declared_status"] == "VERIFIED"
    assert assessment["assessment_status"] == "UNVERIFIED"
    assert assessment["verification_level"] == "STRUCTURAL_ONLY"


def test_delivery_summary_never_assesses_declared_verified_as_verified():
    from core.delivery.evidence_standard import summarize_evidence_standard
    summary = summarize_evidence_standard(_item())
    assert summary["claims"][0]["declared_status"] == "VERIFIED"
    assert summary["claims"][0]["assessment_status"] == "UNVERIFIED"
    assert summary["claims"][0]["verification_level"] == "STRUCTURAL_ONLY"


def test_report_only_mode_does_not_convert_findings_to_ci_failure(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    # The path is assessed by EVS-001, but the unchanged record has no matching
    # subject SHA, so it must not count as current coverage.
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: ["core/delivery/models.py"])
    report_path = tmp_path / "report.json"
    common = ["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
              "--output", str(report_path)]
    assert main([*common, "--mode", "report-only"]) == 0
    report = json.loads(report_path.read_text())
    assert report["finding_count"] > 0
    assert any(row["code"] == "MATERIAL_CHANGE_WITHOUT_RECORD" for row in report["findings"])
    assert main([*common, "--mode", "strict"]) == 1


def test_enforce_new_material_blocks_missing_coverage_but_preserves_report_only(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: ["core/delivery/models.py"])
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    report_path = tmp_path / "report.json"
    common = ["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
              "--output", str(report_path)]

    assert main([*common, "--mode", "report-only"]) == 0
    report_only = json.loads(report_path.read_text())
    assert report_only["blocking_finding_count"] >= 1
    assert any(row["code"] == "MATERIAL_CHANGE_WITHOUT_RECORD" for row in report_only["findings"])

    assert main([*common, "--mode", "enforce-new-material"]) == 1
    enforced = json.loads(report_path.read_text())
    assert enforced["mode"] == "ENFORCE_NEW_MATERIAL"
    assert enforced["blocking_finding_count"] >= 1
    assert any(row["code"] == "MATERIAL_CHANGE_WITHOUT_RECORD" for row in enforced["findings"])


def test_enforce_new_material_allows_explicit_unverified_claim_warning(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    item = _complete_lifecycle_item(head, include_lifecycle_evidence=True)
    standard = dict(item.extensions["evidence_standard"], subject_commit_sha=head)
    item = replace(item, extensions={"evidence_standard": standard})
    monkeypatch.setattr(evidence_tool, "work_item_from_dict", lambda payload: item)
    monkeypatch.setattr(evidence_tool, "validate_source_registry", lambda registry: {
        "TEST-SOURCE": {"status": "VERIFIED", "locator": "governance/evidence/POLICY.md"}
    })
    standard_claim = standard["claims"][0]
    monkeypatch.setattr(evidence_tool, "validate_claim_registry", lambda registry, sources: {
        standard_claim["claim_id"]: {"claim_kind": standard_claim["claim_kind"],
                                     "statement": standard_claim["statement"],
                                     "status": "UNVERIFIED", "source_ids": ["TEST-SOURCE"],
                                     "scope_paths": standard["assessed_paths"],
                                     "limitation": "Independent evidence remains pending."}
    })
    report_path = tmp_path / "report.json"
    common = ["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
              "--output", str(report_path), "--mode", "enforce-new-material"]

    assert main(common) == 0
    report = json.loads(report_path.read_text())
    assert any(row["code"] == "CLAIM_UNVERIFIED" and row["severity"] == "UNVERIFIED"
               for row in report["findings"])
    assert report["blocking_finding_count"] == 0


def test_current_material_record_requires_complete_definition_of_ready(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    base = _item(status="UNVERIFIED")
    standard = dict(base.extensions["evidence_standard"], subject_commit_sha=head,
                    assessed_paths=["core/delivery/"])
    standard["claims"][0]["gate_evidence"] = {}
    item = replace(base, evidence=(), extensions={"evidence_standard": standard})
    _patch_current_material_record(monkeypatch, item, head)
    report_path = tmp_path / "report.json"

    exit_code = main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                      "--output", str(report_path), "--mode", "enforce-new-material"])
    report = json.loads(report_path.read_text())
    finding = next(row for row in report["findings"] if row["code"] == "WORK_ITEM_DOR_INCOMPLETE")
    assert finding["severity"] == "ERROR"
    assert exit_code == 1


def test_current_material_record_requires_lifecycle_roles_and_stage_evidence(
        tmp_path: Path, monkeypatch, capsys):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    item = _complete_lifecycle_item(head, include_lifecycle_evidence=False)
    _patch_current_material_record(monkeypatch, item, head)
    report_path = tmp_path / "report.json"

    exit_code = main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                      "--output", str(report_path), "--mode", "enforce-new-material"])
    report = json.loads(report_path.read_text())
    finding = next(row for row in report["findings"]
                   if row["code"] == "WORK_ITEM_LIFECYCLE_INCOMPLETE")
    assert finding["severity"] == "ERROR"
    assert "G0_REQUIREMENT:BLOCKED" in finding["detail"]
    assert "G3_QA:BLOCKED" in finding["detail"]
    output = capsys.readouterr().out
    assert "Evidence verification blocked" in output
    assert "WORK_ITEM_LIFECYCLE_INCOMPLETE" in output
    assert exit_code == 1


def test_current_material_record_requires_lifecycle_state_history(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    complete = _complete_lifecycle_item(head, include_lifecycle_evidence=True)
    # Keep otherwise complete, sealed role evidence while stripping the
    # transition record. This models a forged evidence-only work item.
    backlog = replace(complete, current_state=DeliveryState.BACKLOG, state_history=())
    _patch_current_material_record(monkeypatch, backlog, head)
    report_path = tmp_path / "report.json"

    exit_code = main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                      "--output", str(report_path), "--mode", "enforce-new-material"])
    report = json.loads(report_path.read_text())
    codes = {row["code"] for row in report["findings"]}
    assert "WORK_ITEM_LIFECYCLE_STATE_INCOMPLETE" in codes
    assert "WORK_ITEM_LIFECYCLE_HISTORY_INCOMPLETE" in codes
    assert exit_code == 1


def test_current_material_record_accepts_complete_lifecycle_but_keeps_claim_unverified(
        tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    item = _complete_lifecycle_item(head, include_lifecycle_evidence=True)
    _patch_current_material_record(monkeypatch, item, head)
    report_path = tmp_path / "report.json"

    exit_code = main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                      "--output", str(report_path), "--mode", "enforce-new-material"])
    report = json.loads(report_path.read_text())
    assert not any(row["code"].startswith("WORK_ITEM_") for row in report["findings"])
    assert any(row["code"] == "CLAIM_UNVERIFIED" and row["severity"] == "UNVERIFIED"
               for row in report["findings"])
    assert exit_code == 0


def test_enforce_new_material_blocks_structural_errors(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "build_report", lambda **kwargs: {
        "candidate_sha": head,
        "enforcement_stage": "BLOCK_NEW_MATERIAL",
        "base_ref": "HEAD",
        "candidate_ref": "HEAD",
        "material_path_count": 0,
        "finding_count": 2,
        "findings": [
            {"severity": "UNVERIFIED", "code": "CLAIM_UNVERIFIED", "path": "", "detail": "Claim is unresolved."},
            {"severity": "ERROR", "code": "CLAIM_REGISTRY_INVALID", "path": "", "detail": "Malformed registry."},
        ],
    })
    report_path = tmp_path / "report.json"
    assert main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                 "--output", str(report_path), "--mode", "enforce-new-material"]) == 1
    report = json.loads(report_path.read_text())
    assert report["blocking_finding_count"] == 1


def test_enforce_new_material_blocks_claim_statement_mismatch(tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "build_report", lambda **kwargs: {
        "candidate_sha": head,
        "enforcement_stage": "BLOCK_NEW_MATERIAL",
        "base_ref": "HEAD",
        "candidate_ref": "HEAD",
        "material_path_count": 1,
        "finding_count": 1,
        "findings": [{"severity": "ERROR", "code": "CLAIM_STATEMENT_MISMATCH",
                      "path": "governance/evidence/work_items/TASK-TEST.json",
                      "detail": "Claim statement differs from the registered statement."}],
    })
    report_path = tmp_path / "report.json"

    exit_code = main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                      "--output", str(report_path), "--mode", "enforce-new-material"])
    report = json.loads(report_path.read_text())
    mismatch = next(row for row in report["findings"]
                    if row["code"] == "CLAIM_STATEMENT_MISMATCH")
    assert mismatch["severity"] == "ERROR"
    assert report["blocking_finding_count"] == 1
    assert exit_code == 1


def test_enforce_new_material_fails_when_candidate_matrix_stage_is_not_blocking(
        tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "build_report", lambda **kwargs: {
        "candidate_sha": head,
        "enforcement_stage": "REPORT_ONLY",
        "material_path_count": 0,
        "finding_count": 0,
        "findings": [],
    })
    report_path = tmp_path / "report.json"
    assert main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                 "--output", str(report_path), "--mode", "enforce-new-material"]) == 1
    report = json.loads(report_path.read_text())
    assert report["enforcement_stage"] == "REPORT_ONLY"
    assert report["mode"] == "ENFORCE_NEW_MATERIAL"
    assert report["findings"][0]["code"] == "ENFORCEMENT_STAGE_MISMATCH"


def test_report_rejects_inconsistent_matrix_report_only_flag(monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    read_json = evidence_tool._read_json

    def read_matrix_with_inconsistent_flag(path):
        payload = read_json(path)
        if Path(path).name == "VERIFICATION_MATRIX.json":
            payload["report_only"] = True
            payload["enforcement_stage"] = "BLOCK_NEW_MATERIAL"
        return payload

    monkeypatch.setattr(evidence_tool, "_read_json", read_matrix_with_inconsistent_flag)
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: [])
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head)
    assert any(row["code"] == "VERIFICATION_MATRIX_INVALID"
               and "report_only must be true exactly" in row["detail"]
               for row in report["findings"])


def test_required_material_prefixes_are_frozen_in_matrix_data():
    matrix = json.loads((evidence_tool.ROOT / "governance/evidence/VERIFICATION_MATRIX.json").read_text())
    assert matrix["protected_material_path_prefixes"]
    assert set(matrix["protected_material_path_prefixes"]) <= set(matrix["material_path_prefixes"])
    assert matrix["trusted_non_material_exemptions"] == []


@pytest.mark.parametrize("removed_prefix", [
    "core/", "strategies/", "research/", "scripts/research/", "config/", "data/",
    "governance/evidence/", "tests/governance/", "tests/delivery/",
    "tools/verify_evidence.py", "docs/tradebot_delivery/", "docs/agent_reviews/",
    ".agents/workflows/tradebot-delivery-orchestrator.md",
    ".github/workflows/evidence-gates.yml",
    ".github/workflows/frozen-head-exact-sha-certification.yml",
    ".github/workflows/ci.yml", ".github/workflows/tests.yml",
])
def test_report_rejects_candidate_matrix_removing_required_material_prefix(
        monkeypatch, removed_prefix):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    read_candidate_json = evidence_tool._read_candidate_json

    def read_matrix_without_required_prefix(root, path):
        payload = read_candidate_json(root, path)
        if path == evidence_tool.MATRIX_PATH:
            payload["material_path_prefixes"].remove(removed_prefix)
        return payload

    monkeypatch.setattr(evidence_tool, "_read_candidate_json", read_matrix_without_required_prefix)
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: ["strategies/example.py"])
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head)

    assert any(row["code"] == "VERIFICATION_MATRIX_INVALID"
               and "removes trusted protected material path prefixes" in row["detail"]
               for row in report["findings"])


@pytest.mark.parametrize("candidate_change", [
    lambda matrix: matrix["protected_material_path_prefixes"].pop(),
    lambda matrix: matrix["protected_material_path_prefixes"].append("untrusted/") ,
    lambda matrix: matrix["trusted_non_material_exemptions"].append(
        {"path": "unknown/", "rationale": "Candidate self-exemption", "owner": "candidate"}
    ),
])
def test_candidate_matrix_cannot_change_trusted_path_policy(
        monkeypatch, candidate_change):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    read_candidate_json = evidence_tool._read_candidate_json

    def candidate_policy_changed(root, path):
        payload = read_candidate_json(root, path)
        if path == evidence_tool.MATRIX_PATH:
            candidate_change(payload)
        return payload

    monkeypatch.setattr(evidence_tool, "_read_candidate_json", candidate_policy_changed)
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: ["unknown/new_file.py"])
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha=head)

    assert any(row["code"] == "VERIFICATION_MATRIX_INVALID" for row in report["findings"])
    assert any(row["code"] == "UNCLASSIFIED_CHANGED_PATH"
               and row["severity"] == "BLOCKING" for row in report["findings"])


def test_unclassified_changed_path_blocks_enforcement_but_unverified_claim_stays_nonblocking(
        tmp_path: Path, monkeypatch):
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(evidence_tool, "changed_paths", lambda *args, **kwargs: [
        "unknown/new_file.py", "governance/evidence/work_items/EVS-001.json",
    ])
    monkeypatch.setattr(evidence_tool, "_candidate_file_matches", lambda *args, **kwargs: True)
    report_path = tmp_path / "report.json"
    result = main(["--base-ref", "HEAD", "--candidate-ref", "HEAD", "--candidate-sha", head,
                   "--output", str(report_path), "--mode", "enforce-new-material"])
    report = json.loads(report_path.read_text())
    assert result == 1
    assert report["unclassified_paths"] == ["unknown/new_file.py"]
    assert any(row["code"] == "UNCLASSIFIED_CHANGED_PATH" and row["severity"] == "BLOCKING"
               for row in report["findings"])
    assert any(row["code"] == "CLAIM_UNVERIFIED" and row["severity"] == "UNVERIFIED"
               for row in report["findings"])


def test_trusted_non_material_exemption_requires_rationale_owner_and_no_material_overlap():
    valid = [{"path": "generated/reports/", "rationale": "Generated report output is non-source data.",
              "owner": "Release Manager"}]
    exemptions = evidence_tool._validate_trusted_exemptions(valid, ["core/"], ["core/"])
    assert _path_matches("generated/reports/daily.json", [exemptions[0]["path"]])

    with pytest.raises(ValueError, match="rationale"):
        evidence_tool._validate_trusted_exemptions(
            [{"path": "generated/", "rationale": " ", "owner": "Release Manager"}], [], [])
    with pytest.raises(ValueError, match="owner"):
        evidence_tool._validate_trusted_exemptions(
            [{"path": "generated/", "rationale": "Generated output.", "owner": ""}], [], [])
    with pytest.raises(ValueError, match="overlaps"):
        evidence_tool._validate_trusted_exemptions(
            [{"path": "core/", "rationale": "Not material.", "owner": "Release Manager"}],
            ["core/"], ["core/"])


def test_candidate_root_cannot_supply_or_change_trusted_path_exemptions(tmp_path: Path):
    trusted_matrix = json.loads((evidence_tool.ROOT / evidence_tool.MATRIX_PATH).read_text())
    trusted_exemption = {"path": "generated/reports/", "rationale": "Generated output only.",
                         "owner": "Release Manager"}
    trusted_matrix["trusted_non_material_exemptions"] = [trusted_exemption]
    trusted_root = tmp_path / "trusted-base"
    trusted_matrix_path = trusted_root / evidence_tool.MATRIX_PATH
    trusted_matrix_path.parent.mkdir(parents=True)
    trusted_matrix_path.write_text(json.dumps(trusted_matrix))

    protected, material, exemptions = evidence_tool._trusted_material_policy(
        trusted_root, dict(trusted_matrix)
    )
    assert exemptions == [trusted_exemption]
    assert not evidence_tool._is_material("generated/reports/daily.json", material)
    assert _path_matches("generated/reports/daily.json", [row["path"] for row in exemptions])

    candidate_matrix = dict(trusted_matrix)
    candidate_matrix["trusted_non_material_exemptions"] = [
        {"path": "unknown/", "rationale": "Candidate self-exemption.", "owner": "candidate"}
    ]
    with pytest.raises(ValueError, match="candidate cannot add"):
        evidence_tool._trusted_material_policy(trusted_root, candidate_matrix)


def test_current_pr_paths_are_material_and_assessed_by_evs_001():
    matrix = json.loads((evidence_tool.ROOT / "governance/evidence/VERIFICATION_MATRIX.json").read_text())
    registry = json.loads((evidence_tool.ROOT / "governance/evidence/CLAIM_REGISTRY.json").read_text())
    item = json.loads((evidence_tool.ROOT / "governance/evidence/work_items/EVS-001.json").read_text())
    claim = next(row for row in registry["claims"] if row["claim_id"] == "EVIDENCE_STANDARD_IMPLEMENTATION")
    path_examples = (
        ".github/workflows/ci.yml", ".github/workflows/tests.yml",
        "tests/delivery/test_delivery_orchestrator.py",
        "docs/agent_reviews/ci_test_tiering_feed_soak_separation.md",
    )
    assessed = item["extensions"]["evidence_standard"]["assessed_paths"]
    for path in path_examples:
        assert evidence_tool._path_matches(path, matrix["material_path_prefixes"])
        assert evidence_tool._path_matches(path, assessed)
        assert evidence_tool._path_matches(path, claim["scope_paths"])


def test_summary_marks_strict_and_blocking_findings_accurately():
    strict_report = {"candidate_sha": SUBJECT_SHA, "material_path_count": 1,
                     "finding_count": 2, "mode": "STRICT", "blocking_finding_count": 2,
                     "findings": [
                         {"severity": "BLOCKING", "code": "MATERIAL_CHANGE_WITHOUT_RECORD",
                          "path": "core/example.py", "detail": "No current record."},
                         {"severity": "UNVERIFIED", "code": "CLAIM_UNVERIFIED",
                          "path": "record.json", "detail": "Claim remains unverified."},
                     ]}
    summary = render_summary(strict_report)
    assert "strict enforcement" in summary
    assert "blocking findings: 2" in summary
    assert "| BLOCKING | MATERIAL_CHANGE_WITHOUT_RECORD |" in summary


def test_report_summary_surfaces_findings_without_claiming_approval(tmp_path: Path):
    report = {"candidate_sha": SUBJECT_SHA, "material_path_count": 1, "finding_count": 1,
              "findings": [{"severity": "UNVERIFIED", "code": "MATERIAL_CHANGE_WITHOUT_RECORD",
                            "path": "core/example.py", "detail": "No current record."}]}
    summary = render_summary(report)
    assert "informational" in summary
    assert "MATERIAL_CHANGE_WITHOUT_RECORD" in summary
    assert "does not establish merge, research, or runtime readiness" in summary


def test_cli_keeps_candidate_finding_text_only_in_explicit_report_file(
        tmp_path: Path, monkeypatch, capsys):
    marker = "CANDIDATE_SECRET_MARKER_7f91a2"
    head = "c" * 40
    monkeypatch.setattr(evidence_tool, "build_report", lambda **kwargs: {
        "candidate_sha": head,
        "candidate_root_sha": head,
        "verifier_source_sha": head,
        "base_ref": "base",
        "candidate_ref": "candidate",
        "enforcement_stage": "BLOCK_NEW_MATERIAL",
        "changed_path_count": 1,
        "material_path_count": 1,
        "material_paths": [marker],
        "trusted_non_material_exemptions": [],
        "exempted_paths": [],
        "unclassified_paths": [],
        "legacy_inventory": [],
        "work_items": [],
        "finding_count": 1,
        "findings": [{"severity": "BLOCKING", "code": "TEST_BLOCK",
                      "path": marker, "detail": marker}],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "authority": "test only",
    })
    report_path = tmp_path / "report.json"
    summary_path = tmp_path / "summary.md"

    exit_code = main(["--base-ref", "base", "--candidate-ref", "candidate",
                      "--candidate-sha", head, "--output", str(report_path),
                      "--summary-output", str(summary_path),
                      "--mode", "enforce-new-material"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert marker not in captured.out
    assert marker not in captured.err
    assert marker not in summary_path.read_text()
    stored = json.loads(report_path.read_text())
    assert stored["findings"][0]["path"] == marker
    assert stored["findings"][0]["detail"] == marker
    assert marker in stored["material_paths"]


def test_cli_without_output_never_writes_candidate_finding_text_to_stdout(monkeypatch, capsys):
    marker = "CANDIDATE_SECRET_MARKER_DEFAULT_STDOUT_4a82"
    head = "d" * 40
    monkeypatch.setattr(evidence_tool, "build_report", lambda **kwargs: {
        "candidate_sha": head,
        "candidate_root_sha": head,
        "verifier_source_sha": head,
        "base_ref": "base",
        "candidate_ref": "candidate",
        "enforcement_stage": "BLOCK_NEW_MATERIAL",
        "changed_path_count": 1,
        "material_path_count": 1,
        "material_paths": [marker],
        "trusted_non_material_exemptions": [],
        "exempted_paths": [],
        "unclassified_paths": [],
        "legacy_inventory": [],
        "work_items": [],
        "finding_count": 1,
        "findings": [{"severity": "BLOCKING", "code": "TEST_BLOCK",
                      "path": marker, "detail": marker}],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "authority": "test only",
    })

    exit_code = main(["--base-ref", "base", "--candidate-ref", "candidate",
                      "--candidate-sha", head, "--mode", "enforce-new-material"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert marker not in captured.out
    assert marker not in captured.err
    assert "Full structured evidence report omitted; pass --output <path> to retain it." in captured.out
    assert "Evidence verification blocked: 1 finding(s)." in captured.out
    assert "BLOCKING TEST_BLOCK" in captured.out


def _trusted_candidate_prep_script() -> str:
    workflow_path = evidence_tool.ROOT / ".github/workflows/frozen-head-exact-sha-certification.yml"
    lines = workflow_path.read_text().splitlines()
    step_line = lines.index("      - name: Validate event SHAs and prepare candidate as inert data")
    run_line = next(index for index in range(step_line + 1, len(lines))
                    if lines[index].strip() == "run: |")
    run_indent = len(lines[run_line]) - len(lines[run_line].lstrip())
    body = []
    for line in lines[run_line + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= run_indent:
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)).strip() + "\n"


def test_trusted_evidence_workflow_does_not_persist_checkout_credentials():
    workflow_path = evidence_tool.ROOT / ".github/workflows/frozen-head-exact-sha-certification.yml"
    workflow = workflow_path.read_text()
    trusted_job = workflow.split("  trusted-evidence-coverage:", 1)[1]
    checkout_step = trusted_job.split("      - name: Set up Python from the protected base workflow", 1)[0]

    assert "persist-credentials: false" in checkout_step


@pytest.mark.parametrize(("workflow_relpath", "event_name"), [
    (".github/workflows/frozen-head-exact-sha-certification.yml", "pull_request_target"),
    (".github/workflows/evidence-gates.yml", "pull_request"),
])
def test_evidence_workflows_rerun_when_pr_is_edited(workflow_relpath: str, event_name: str):
    workflow = (evidence_tool.ROOT / workflow_relpath).read_text(encoding="utf-8")
    lines = workflow.splitlines()
    event_line = lines.index(f"  {event_name}:")
    event_types = None
    for line in lines[event_line + 1:]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        if line.lstrip().startswith("types:"):
            value = line.split("[", 1)[1].split("]", 1)[0]
            event_types = {entry.strip().strip("'\"") for entry in value.split(",")}
            break

    assert event_types is not None
    assert {"opened", "reopened", "synchronize", "ready_for_review", "edited"} <= event_types


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()


def _trusted_git_fixture(tmp_path: Path, *, fake_fetch_head: bool = False) -> dict[str, str | Path]:
    bare = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    trusted = tmp_path / "trusted"
    bare.mkdir()
    seed.mkdir()
    subprocess.run(["git", "init", "--bare", "--quiet", str(bare)], check=True)
    subprocess.run(["git", "init", "--quiet"], cwd=seed, check=True)
    _git(seed, "config", "user.name", "Evidence Test")
    _git(seed, "config", "user.email", "evidence-test@example.invalid")
    (seed / "base.txt").write_text("protected base\n")
    _git(seed, "add", "base.txt")
    _git(seed, "commit", "--quiet", "-m", "protected base")
    base_sha = _git(seed, "rev-parse", "HEAD")
    _git(seed, "remote", "add", "origin", str(bare))
    _git(seed, "push", "--quiet", "origin", f"{base_sha}:refs/heads/main")

    execution_marker = tmp_path / "candidate-was-executed"
    candidate_script = seed / "candidate_payload.sh"
    candidate_script.write_text(f"#!/bin/sh\ntouch '{execution_marker}'\n")
    candidate_script.chmod(0o755)
    _git(seed, "add", "candidate_payload.sh")
    _git(seed, "commit", "--quiet", "-m", "candidate payload")
    candidate_sha = _git(seed, "rev-parse", "HEAD")
    _git(seed, "push", "--quiet", "origin", f"{candidate_sha}:refs/pull/42/head")
    subprocess.run(["git", "clone", "--quiet", "--branch", "main", str(bare), str(trusted)],
                   check=True)

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    github_output = tmp_path / "github-output"
    git_log = tmp_path / "git-invocations.log"
    env = {
        "BASE_SHA": base_sha,
        "HEAD_SHA": candidate_sha,
        "RUN_ID": "test-run",
        "RUN_ATTEMPT": "1",
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_OUTPUT": str(github_output),
    }
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    shim.write_text("#!/bin/bash\n"
                    "printf '%s\\n' \"$*\" >> \"$GIT_LOG\"\n"
                    "if [[ \"$1\" == fetch && \"$2\" == --no-tags && \"$3\" == origin && \"$4\" == \"$HEAD_SHA\" ]]; then\n"
                    "  hidden_head=$(\"$REAL_GIT\" --git-dir \"$ORIGIN_BARE\" rev-parse refs/pull/42/head) || exit 1\n"
                    "  [[ \"$hidden_head\" == \"$4\" ]] || exit 1\n"
                    "  exec \"$REAL_GIT\" fetch --no-tags origin +refs/pull/42/head:refs/remotes/origin/test-candidate\n"
                    "fi\n"
                    "if [[ \"$1 $2\" == 'rev-parse FETCH_HEAD' && -n \"${FAKE_FETCH_HEAD_SHA:-}\" ]]; then\n"
                    "  printf '%s\\n' \"$FAKE_FETCH_HEAD_SHA\"\n"
                    "  exit 0\n"
                    "fi\n"
                    "exec \"$REAL_GIT\" \"$@\"\n")
    shim.chmod(0o755)
    env.update({"PATH": f"{bin_dir}:{os.environ['PATH']}",
                "REAL_GIT": shutil.which("git") or "git",
                "GIT_LOG": str(git_log),
                "ORIGIN_BARE": str(bare),
                "FAKE_FETCH_HEAD_SHA": "e" * 40 if fake_fetch_head else ""})
    return {"trusted": trusted, "base_sha": base_sha, "candidate_sha": candidate_sha,
            "execution_marker": execution_marker, "runner_temp": runner_temp,
            "github_output": github_output, "git_log": git_log, "env": env}


def _run_candidate_prep(fixture: dict[str, str | Path], *, overrides: dict[str, str] | None = None):
    env = os.environ.copy()
    env.update(fixture["env"])
    if overrides:
        env.update(overrides)
    return subprocess.run(["bash", "-euo", "pipefail", "-c", _trusted_candidate_prep_script()],
                          cwd=fixture["trusted"], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_trusted_candidate_prep_materializes_exact_hidden_head_without_execution(tmp_path: Path):
    fixture = _trusted_git_fixture(tmp_path)
    result = _run_candidate_prep(fixture)

    assert result.returncode == 0, result.stderr
    output_line = Path(fixture["github_output"]).read_text().strip()
    assert output_line.startswith("candidate_root=")
    candidate_root = Path(output_line.removeprefix("candidate_root="))
    assert candidate_root == Path(fixture["runner_temp"]) / "trusted-evidence-candidate-test-run-1"
    materialized_script = candidate_root / "candidate_payload.sh"
    assert materialized_script.read_text().startswith("#!/bin/sh\n")
    assert materialized_script.read_text() == (Path(fixture["trusted"]).parent / "seed" /
                                                 "candidate_payload.sh").read_text()
    assert _git(Path(fixture["trusted"]), "rev-parse", "HEAD") == fixture["base_sha"]
    assert not Path(fixture["execution_marker"]).exists()
    git_calls = Path(fixture["git_log"]).read_text()
    assert f"fetch --no-tags origin {fixture['candidate_sha']}" in git_calls
    assert "archive --format=tar" in git_calls


@pytest.mark.parametrize("failure,overrides", [
    ("malformed_sha", {"HEAD_SHA": "not-a-full-commit-id"}),
    ("base_mismatch", {"BASE_SHA": "f" * 40}),
    ("fetched_head_mismatch", {}),
])
def test_trusted_candidate_prep_fails_closed_before_archive_or_output(
        tmp_path: Path, failure: str, overrides: dict[str, str]):
    fixture = _trusted_git_fixture(tmp_path, fake_fetch_head=(failure == "fetched_head_mismatch"))
    result = _run_candidate_prep(fixture, overrides=overrides)

    assert result.returncode != 0
    assert not Path(fixture["github_output"]).exists()
    assert not (Path(fixture["runner_temp"]) /
                "trusted-evidence-candidate-test-run-1").exists()
    assert not Path(fixture["execution_marker"]).exists()
    git_log_path = Path(fixture["git_log"])
    if git_log_path.exists():
        assert "archive" not in git_log_path.read_text()


def test_report_detects_candidate_sha_mismatch():
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha="e" * 40)
    assert report["candidate_sha"] != head
    assert any(row["code"] in {"CANDIDATE_SHA_MISMATCH", "CANDIDATE_REF_UNRESOLVED"}
               for row in report["findings"])
