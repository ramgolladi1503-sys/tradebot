from __future__ import annotations

import json
from pathlib import Path
import subprocess

from core.agent_supervisor import (
    SupervisorState,
    claim_contract,
    get_contract_status,
    load_contract_file,
    normalize_supervisor_contract,
    preflight_contract,
    record_independent_review,
    release_contract,
    validate_contract_shape,
    verify_contract,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "core").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()
    (repo / "core" / "frozen.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    _git(repo, "checkout", "-b", "agent/test-task")
    return repo


def _payload(repo: Path, **supervisor_overrides):
    supervisor = {
        "schema_version": 1,
        "task_id": "test-task",
        "implementer": "codex",
        "reviewer": "antigravity",
        "worktree_path": str(repo),
        "branch": "agent/test-task",
        "base_ref": "main",
        "ownership_paths": ["tests/test_feature.py"],
        "frozen_paths": ["core/frozen.py"],
        "acceptance_commands": [
            {
                "name": "focused-tests",
                "argv": ["python", "-m", "pytest", "tests/test_feature.py", "-q"],
                "timeout_seconds": 30,
            }
        ],
        "required_artifacts": ["tests/test_feature.py"],
        "require_clean_worktree": True,
        "require_committed_head": True,
    }
    supervisor.update(supervisor_overrides)
    return {
        "schema_version": 1,
        "source_agent": "codex",
        "action": "GENERATE_TESTS",
        "title": "Add feature tests",
        "scope": "Add one deterministic feature test.",
        "requested_paths": ["tests/test_feature.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": [".env", "credentials.py", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
        "supervisor": supervisor,
    }


def _commit_test(repo: Path, *, passing: bool = True) -> str:
    assertion = "assert 1 + 1 == 2" if passing else "assert 1 + 1 == 3"
    (repo / "tests" / "test_feature.py").write_text(
        f"def test_feature():\n    {assertion}\n", encoding="utf-8"
    )
    _git(repo, "add", "tests/test_feature.py")
    _git(repo, "commit", "-m", "test: add feature proof")
    return _git(repo, "rev-parse", "HEAD")


def test_shape_rejects_same_implementer_and_reviewer(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo, reviewer="codex"))
    blockers, _ = validate_contract_shape(contract)
    assert "REVIEWER_MUST_BE_INDEPENDENT" in blockers


def test_shape_blocks_live_script_acceptance_command(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(
        _payload(
            repo,
            acceptance_commands=[
                {"name": "bad", "argv": ["python", "main.py"], "timeout_seconds": 10}
            ],
        )
    )
    blockers, _ = validate_contract_shape(contract)
    assert "ACCEPTANCE_COMMAND_LIVE_SCRIPT_BLOCKED" in blockers


def test_preflight_requires_clean_matching_isolated_branch(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    result = preflight_contract(contract, enforce_tradebot_guard=False)
    assert result.state == SupervisorState.PREFLIGHT_READY.value
    assert result.accepted is True
    (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
    dirty = preflight_contract(contract, enforce_tradebot_guard=False)
    assert dirty.accepted is False
    assert "WORKTREE_NOT_CLEAN" in dirty.blockers


def test_claim_is_idempotent_for_same_task_and_identity(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    first = claim_contract(contract, enforce_tradebot_guard=False)
    second = claim_contract(contract, enforce_tradebot_guard=False)
    assert first.accepted is True
    assert second.accepted is True
    assert "CLAIM_ALREADY_ACTIVE" in second.warnings


def test_claim_blocks_overlapping_ownership_across_worktrees(tmp_path):
    repo = _repo(tmp_path)
    first = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(first, enforce_tradebot_guard=False).accepted is True

    worktree = tmp_path / "other-worktree"
    _git(repo, "branch", "agent/other-task")
    _git(repo, "worktree", "add", str(worktree), "agent/other-task")
    second_payload = _payload(
        worktree,
        task_id="other-task",
        branch="agent/other-task",
        ownership_paths=["tests/"],
    )
    second = normalize_supervisor_contract(second_payload)
    result = claim_contract(second, enforce_tradebot_guard=False)
    assert result.accepted is False
    assert "OWNERSHIP_CONFLICT" in result.blockers


def test_verify_records_hashes_and_passes_safe_commands(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    head = _commit_test(repo, passing=True)
    result = verify_contract(contract)
    assert result.state == SupervisorState.VERIFIED.value
    assert result.accepted is True
    manifest = result.details["manifest"]
    assert manifest["head_commit"] == head
    assert manifest["changed_paths"] == ["tests/test_feature.py"]
    assert manifest["acceptance_commands"][0]["exit_code"] == 0
    assert len(manifest["manifest_sha256"]) == 64
    assert Path(result.details["manifest_path"]).exists()


def test_verify_fails_when_acceptance_command_fails(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    _commit_test(repo, passing=False)
    result = verify_contract(contract)
    assert result.accepted is False
    assert "ACCEPTANCE_COMMAND_FAILED" in result.blockers


def test_verify_fails_when_frozen_contract_changes(tmp_path):
    repo = _repo(tmp_path)
    payload = _payload(repo)
    payload["requested_paths"] = ["tests/test_feature.py", "core/frozen.py"]
    payload["allowed_paths"] = ["tests/", "core/"]
    payload["supervisor"]["ownership_paths"] = ["tests/test_feature.py"]
    contract = normalize_supervisor_contract(payload)
    blockers, _ = validate_contract_shape(contract)
    assert "REQUESTED_PATH_FROZEN" in blockers

    safe_contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(safe_contract, enforce_tradebot_guard=False).accepted is True
    _commit_test(repo, passing=True)
    (repo / "core" / "frozen.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "core/frozen.py")
    _git(repo, "commit", "-m", "bad: mutate frozen contract")
    result = verify_contract(safe_contract)
    assert result.accepted is False
    assert "FROZEN_PATH_CHANGED" in result.blockers
    assert "CHANGED_PATH_OUTSIDE_ALLOWED_PATHS" in result.blockers


def test_review_requires_matching_manifest_and_reproduction_evidence(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    head = _commit_test(repo)
    verified = verify_contract(contract)
    manifest = verified.details["manifest"]

    missing_reproduction = record_independent_review(
        contract,
        {
            "schema_version": 1,
            "task_id": "test-task",
            "reviewer": "antigravity",
            "decision": "APPROVE",
            "summary": "Looks good.",
            "base_commit": manifest["base_commit"],
            "head_commit": head,
            "implementation_manifest_sha256": manifest["manifest_sha256"],
            "reproduction_results": [],
        },
    )
    assert missing_reproduction.accepted is False
    assert "REVIEW_REPRODUCTION_EVIDENCE_MISSING" in missing_reproduction.blockers

    approved = record_independent_review(
        contract,
        {
            "schema_version": 1,
            "task_id": "test-task",
            "reviewer": "antigravity",
            "decision": "APPROVE",
            "summary": "Reproduced the focused test and inspected scope.",
            "base_commit": manifest["base_commit"],
            "head_commit": head,
            "implementation_manifest_sha256": manifest["manifest_sha256"],
            "reproduction_results": [{"name": "focused-tests", "exit_code": 0}],
            "findings": [],
        },
    )
    assert approved.state == SupervisorState.REVIEW_APPROVED.value
    assert approved.accepted is True


def test_release_requires_approved_independent_review(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    blocked = release_contract(contract)
    assert blocked.accepted is False
    assert "REVIEW_APPROVAL_REQUIRED_BEFORE_RELEASE" in blocked.blockers

    forced = release_contract(contract, force=True)
    assert forced.accepted is True
    assert "FORCED_RELEASE" in forced.warnings
    status = get_contract_status(contract)
    assert status.details["claim"]["state"] == "RELEASED"


def test_contract_and_results_are_json_serializable(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    result = preflight_contract(contract, enforce_tradebot_guard=False)
    json.dumps(contract.to_dict(), sort_keys=True)
    json.dumps(result.to_dict(), sort_keys=True)


def test_review_rejects_tampered_implementation_manifest(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    head = _commit_test(repo)
    verified = verify_contract(contract)
    manifest_path = Path(verified.details["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["changed_paths"] = ["forged.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    reviewed = record_independent_review(
        contract,
        {
            "schema_version": 1,
            "task_id": "test-task",
            "reviewer": "antigravity",
            "decision": "APPROVE",
            "summary": "Attempted review.",
            "base_commit": manifest["base_commit"],
            "head_commit": head,
            "implementation_manifest_sha256": manifest["manifest_sha256"],
            "reproduction_results": [{"name": "focused-tests", "exit_code": 0}],
        },
    )
    assert reviewed.accepted is False
    assert "IMPLEMENTATION_MANIFEST_HASH_INVALID" in reviewed.blockers


def test_load_contract_file(tmp_path: Path):
    payload_path = tmp_path / "task.json"
    payload_path.write_text(json.dumps({"task_id": "demo-task"}), encoding="utf-8")

    assert load_contract_file(payload_path) == {"task_id": "demo-task"}
