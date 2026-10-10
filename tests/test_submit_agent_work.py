from __future__ import annotations

import hashlib
import json
import subprocess

from core.delivery.models import WorkItem, WorkItemType
from core.delivery.validators import work_item_to_dict
from scripts.submit_agent_work import (
    CLI_APPROVAL_REJECTED,
    CLI_CONTRACT_OR_SCOPE_BLOCKED,
    CLI_OK,
    CLI_PAYLOAD_ERROR,
    main,
    submit_agent_work_payload,
)


def _payload(**overrides):
    payload = {
        "schema_version": 1,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add local admission tests",
        "scope": "Prove the local task admission contract.",
        "requested_paths": ["tests/test_agent_admission.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker/**"],
        "expected_tests": ["PYTHONPATH=. pytest -q tests/test_agent_admission.py"],
        "acceptance_proof": ["A committed task contract must match before acceptance."],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return payload


def _admitted_payload(tmp_path, **overrides):
    payload = _payload(**overrides)
    spec = {key: payload[key] for key in (
        "source_agent", "action", "title", "scope", "requested_paths", "allowed_paths",
        "forbidden_paths", "expected_tests", "acceptance_proof",
    )}
    spec["task_contract_id"] = "SUBMIT-TEST-1"
    item = WorkItem(
        work_item_id="SUBMIT-TEST-1",
        type=WorkItemType.TASK,
        parent_epic="LOCAL-EPIC",
        parent_feature="LOCAL-FEATURE",
        title=payload["title"],
        priority="P2",
        business_goal="Make local agent intake safe.",
        current_behavior="Submissions are unbound JSON.",
        expected_behavior=payload["scope"],
        in_scope=("local task submission",),
        out_of_scope=("broker and runtime behavior",),
        acceptance_criteria=tuple(payload["acceptance_proof"]),
        safety_constraints=("No broker calls", "No live execution"),
        architecture_impact="Offline CLI admission only.",
        allowed_paths=tuple(payload["allowed_paths"]),
        forbidden_paths=tuple(payload["forbidden_paths"]),
        expected_tests=tuple(payload["expected_tests"]),
        qa_attack_plan=("missing item", "unauthenticated approval"),
        uat_criteria=("Nonmatching requests are blocked.",),
        release_gates=("Focused tests pass.",),
        rollback_plan="Revert the local CLI admission check.",
        extensions={"agent_task_contracts": [spec]},
    )
    root = tmp_path / "repo"
    item_path = root / "governance/evidence/work_items/SUBMIT-TEST-1.json"
    item_path.parent.mkdir(parents=True)
    item_path.write_text(json.dumps(work_item_to_dict(item), indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "--", str(item_path.relative_to(root))], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "add task record"], check=True)
    payload["metadata"]["delivery_work_item"] = {
        "work_item_id": item.work_item_id,
        "path": str(item_path.relative_to(root)),
        "sha256": hashlib.sha256(item_path.read_bytes()).hexdigest(),
        "task_contract_id": spec["task_contract_id"],
    }
    return root, payload


def test_submit_payload_accepts_low_risk_work_and_persists_bound_evidence(tmp_path):
    root, payload = _admitted_payload(tmp_path)
    evidence_root = tmp_path / "evidence"
    exit_code, result = submit_agent_work_payload(
        payload, repository_root=root, evidence_root=evidence_root
    )

    assert exit_code == CLI_OK
    assert result["admission_decision"]["accepted"] is True
    assert result["contract_decision"]["accepted"] is True
    assert result["scope_decision"]["accepted"] is True
    assert result["approval_decision"]["approved"] is True
    assert result["approval_decision"]["allowed_for_patch"] is True
    assert result["safety"]["read_only"] is True
    assert result["safety"]["is_order_action"] is False
    assert result["safety"]["broker_api_called"] is False
    assert result["safety"]["live_mode_touched"] is False
    assert result["safety"]["allowed_for_live_execution"] is False
    assert result["evidence_result"]["latest_path"] == str(evidence_root / "agent_work_latest.json")
    saved = json.loads((evidence_root / "agent_work_latest.json").read_text(encoding="utf-8"))
    assert saved["request"]["admission_decision"]["work_item_sha256"] == payload["metadata"]["delivery_work_item"]["sha256"]
    assert list(evidence_root.glob("agent_work_*.jsonl"))


def test_no_evidence_cannot_return_accepted(tmp_path):
    root, payload = _admitted_payload(tmp_path)
    exit_code, result = submit_agent_work_payload(
        payload, repository_root=root, write_evidence=False
    )

    assert exit_code == CLI_CONTRACT_OR_SCOPE_BLOCKED
    assert result["acceptance_blocker"] == "EVIDENCE_PERSISTENCE_REQUIRED"
    assert result["evidence_result"] is None


def test_high_risk_patch_is_blocked_even_with_caller_approval_flags(tmp_path):
    root, payload = _admitted_payload(
        tmp_path,
        action="GENERATE_PATCH",
        requested_paths=["core/risk/position_sizing.py"],
        allowed_paths=["core/risk/"],
        forbidden_paths=["credentials.py", ".env", "core/broker/**"],
    )

    exit_code, result = submit_agent_work_payload(
        payload,
        repository_root=root,
        human_approved=True,
        approved_by="caller-asserted-user",
        evidence_root=tmp_path / "evidence",
    )

    assert exit_code == CLI_APPROVAL_REJECTED
    assert result["admission_decision"]["accepted"] is True
    assert result["scope_decision"]["requires_human_approval"] is True
    assert result["approval_decision"]["approved"] is False
    assert result["approval_decision"]["approved_by"] is None
    assert "HUMAN_APPROVAL_REQUIRED" in result["approval_decision"]["blockers"]


def test_evidence_persistence_exception_blocks_acceptance(tmp_path, monkeypatch):
    root, payload = _admitted_payload(tmp_path)

    def fail_write(**_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("scripts.submit_agent_work.write_agent_evidence", fail_write)
    exit_code, result = submit_agent_work_payload(payload, repository_root=root)

    assert exit_code == CLI_CONTRACT_OR_SCOPE_BLOCKED
    assert result["evidence_result"] is None
    assert result["evidence_error"].startswith("OSError:")


def test_main_prints_json_and_returns_success(tmp_path, capsys, monkeypatch):
    root, payload = _admitted_payload(tmp_path)
    payload_path = tmp_path / "payload.json"
    evidence_root = tmp_path / "evidence"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(root)

    exit_code = main(["--payload", str(payload_path), "--evidence-root", str(evidence_root)])
    captured = capsys.readouterr()
    printed = json.loads(captured.out)

    assert exit_code == CLI_OK
    assert printed["admission_decision"]["accepted"] is True
    assert printed["evidence_result"]["latest_path"] == str(evidence_root / "agent_work_latest.json")


def test_main_returns_payload_error_for_invalid_json(tmp_path, capsys):
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("not-json", encoding="utf-8")

    exit_code = main(["--payload", str(payload_path), "--no-evidence"])
    captured = capsys.readouterr()
    printed = json.loads(captured.out)

    assert exit_code == CLI_PAYLOAD_ERROR
    assert printed["error"].startswith("failed_to_read_payload:")
    assert printed["safety"]["read_only"] is True
    assert printed["safety"]["allowed_for_live_execution"] is False


def test_main_blocks_forbidden_action_and_uncommitted_item(tmp_path, capsys, monkeypatch):
    root, payload = _admitted_payload(tmp_path, action="ENABLE_LIVE")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(root)

    exit_code = main(["--payload", str(payload_path)])
    printed = json.loads(capsys.readouterr().out)
    assert exit_code == CLI_CONTRACT_OR_SCOPE_BLOCKED
    assert "ACTION_FORBIDDEN" in printed["contract_decision"]["blockers"]

    payload["action"] = "GENERATE_TESTS"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    item_path = root / payload["metadata"]["delivery_work_item"]["path"]
    item_path.write_text(item_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    exit_code = main(["--payload", str(payload_path), "--approve", "--approved-by", "caller"])
    printed = json.loads(capsys.readouterr().out)
    assert exit_code == CLI_CONTRACT_OR_SCOPE_BLOCKED
    assert "WORK_ITEM_DIRTY" in printed["admission_decision"]["blockers"]
