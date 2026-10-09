from __future__ import annotations

import json
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
from core.delivery.models import Evidence, EvidenceStatus, EvidenceType, WorkItem, WorkItemType
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
    assert report["work_items"][0]["candidate_sha"] == head
    assert report["work_items"][0]["record_sha256"]
    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False
    assert report["allowed_for_live_execution"] is False
    assert all(row["status"] == "UNVERIFIED" for row in report["legacy_inventory"])


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

    def candidate_match_except_target(candidate_ref, path, local_path, *, cwd):
        if path == rel_path:
            return False
        return candidate_match(candidate_ref, path, local_path, cwd=cwd)

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


def test_report_summary_surfaces_findings_without_claiming_approval(tmp_path: Path):
    report = {"candidate_sha": SUBJECT_SHA, "material_path_count": 1, "finding_count": 1,
              "findings": [{"severity": "UNVERIFIED", "code": "MATERIAL_CHANGE_WITHOUT_RECORD",
                            "path": "core/example.py", "detail": "No current record."}]}
    summary = render_summary(report)
    assert "informational" in summary
    assert "MATERIAL_CHANGE_WITHOUT_RECORD" in summary
    assert "does not establish merge, research, or runtime readiness" in summary


def test_report_detects_candidate_sha_mismatch():
    head = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = build_report(base_ref="HEAD", candidate_ref="HEAD", candidate_sha="e" * 40)
    assert report["candidate_sha"] != head
    assert any(row["code"] in {"CANDIDATE_SHA_MISMATCH", "CANDIDATE_REF_UNRESOLVED"}
               for row in report["findings"])
