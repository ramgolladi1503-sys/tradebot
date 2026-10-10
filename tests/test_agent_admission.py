from __future__ import annotations

import hashlib
import json
import subprocess

from core.agent_admission import admit_agent_work
from core.delivery.models import WorkItem, WorkItemType
from core.delivery.validators import work_item_to_dict


def _spec() -> dict:
    return {
        "task_contract_id": "LOCAL-TEST-1",
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add admission behavior tests",
        "scope": "Prove local task admission fails closed.",
        "requested_paths": ["tests/test_agent_admission.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": [".env", "credentials.py", "core/broker/**"],
        "expected_tests": ["PYTHONPATH=. pytest -q tests/test_agent_admission.py"],
        "acceptance_proof": ["Committed item identity, hash, title, scope, and paths match."],
    }


def _payload(root, digest: str | None = None) -> dict:
    spec = _spec()
    return {
        "schema_version": 1,
        "source_agent": spec["source_agent"],
        "action": spec["action"],
        "title": spec["title"],
        "scope": spec["scope"],
        "requested_paths": spec["requested_paths"],
        "allowed_paths": spec["allowed_paths"],
        "forbidden_paths": spec["forbidden_paths"],
        "expected_tests": spec["expected_tests"],
        "acceptance_proof": spec["acceptance_proof"],
        "requires_human_approval": False,
        "metadata": {
            "delivery_work_item": {
                "work_item_id": "LOCAL-TEST-1",
                "path": "governance/evidence/work_items/LOCAL-TEST-1.json",
                "sha256": digest or "0" * 64,
                "task_contract_id": spec["task_contract_id"],
            }
        },
    }


def _repo(tmp_path):
    root = tmp_path / "repo"
    item_path = root / "governance/evidence/work_items/LOCAL-TEST-1.json"
    item_path.parent.mkdir(parents=True)
    spec = _spec()
    item = WorkItem(
        work_item_id="LOCAL-TEST-1",
        type=WorkItemType.TASK,
        parent_epic="LOCAL-EPIC",
        parent_feature="LOCAL-FEATURE",
        title=spec["title"],
        priority="P2",
        business_goal="Make task entry safe.",
        current_behavior="Local requests lack a committed admission binding.",
        expected_behavior=spec["scope"],
        in_scope=("local agent admission",),
        out_of_scope=("broker and runtime behavior",),
        acceptance_criteria=tuple(spec["acceptance_proof"]),
        safety_constraints=("No broker calls", "No live execution"),
        architecture_impact="Local validation only.",
        allowed_paths=("tests/",),
        forbidden_paths=(".env", "credentials.py", "core/broker/**"),
        expected_tests=tuple(spec["expected_tests"]),
        qa_attack_plan=("missing item", "dirty item", "stale hash"),
        uat_criteria=("A mismatched request is blocked.",),
        release_gates=("Focused tests pass.",),
        rollback_plan="Remove the local admission helper.",
        extensions={"agent_task_contracts": [spec]},
    )
    item_path.write_text(json.dumps(work_item_to_dict(item), indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "--", str(item_path.relative_to(root))], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "add canonical task"], check=True)
    digest = hashlib.sha256(item_path.read_bytes()).hexdigest()
    return root, item_path, _payload(root, digest)


def test_admission_accepts_exact_committed_item_and_task_scope(tmp_path):
    root, _, payload = _repo(tmp_path)

    decision = admit_agent_work(payload, repository_root=root)

    assert decision.accepted is True
    assert decision.state == "ADMITTED"
    assert decision.work_item_id == "LOCAL-TEST-1"
    assert decision.metadata["work_item_contract_hash"]


def test_admission_rejects_missing_reference_and_stale_hash(tmp_path):
    root, _, payload = _repo(tmp_path)

    missing = dict(payload, metadata={"project": "tradebot"})
    assert "WORK_ITEM_REFERENCE_REQUIRED" in admit_agent_work(missing, repository_root=root).blockers
    payload["metadata"]["delivery_work_item"]["sha256"] = "a" * 64
    assert "WORK_ITEM_HASH_MISMATCH" in admit_agent_work(payload, repository_root=root).blockers


def test_admission_rejects_dirty_or_deleted_canonical_item(tmp_path):
    root, item_path, payload = _repo(tmp_path)
    item_path.write_text(item_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert "WORK_ITEM_DIRTY" in admit_agent_work(payload, repository_root=root).blockers

    subprocess.run(["git", "-C", str(root), "checkout", "--", str(item_path.relative_to(root))], check=True)
    item_path.unlink()
    assert "WORK_ITEM_MISSING" in admit_agent_work(payload, repository_root=root).blockers


def test_admission_rejects_task_scope_and_path_escalation(tmp_path):
    root, _, payload = _repo(tmp_path)
    payload["scope"] = "A different task."
    assert "WORK_ITEM_TASK_CONTRACT_MISMATCH" in admit_agent_work(payload, repository_root=root).blockers

    _, _, payload = _repo(tmp_path / "second")
    payload["requested_paths"] = ["core/risk/live.py"]
    assert "WORK_ITEM_TASK_CONTRACT_MISMATCH" in admit_agent_work(payload, repository_root=tmp_path / "second/repo").blockers


def test_admission_rejects_malformed_canonical_item(tmp_path):
    root, item_path, payload = _repo(tmp_path)
    item_path.write_text('{"work_item_id":"broken"}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", str(item_path.relative_to(root))], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "malformed canonical item"], check=True)
    payload["metadata"]["delivery_work_item"]["sha256"] = hashlib.sha256(item_path.read_bytes()).hexdigest()

    assert "WORK_ITEM_INVALID" in admit_agent_work(payload, repository_root=root).blockers
