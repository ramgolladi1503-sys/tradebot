from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
import subprocess
import sys

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
from scripts.agent_supervisor import main as supervisor_cli_main
from core.delivery.models import WorkItem, WorkItemType
from core.delivery.validators import work_item_to_dict


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
    (repo / ".gitignore").write_text(".env\n.runtime/\n", encoding="utf-8")
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
                "argv": ["python3", "-m", "pytest", "tests/test_feature.py", "-q"],
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
        "expected_tests": ["PYTHONPATH=. pytest -q tests/test_feature.py"],
        "acceptance_proof": ["The committed item and scope match before claim."],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
        "supervisor": supervisor,
    }


def _admitted_payload(repo: Path, *, request_overrides=None, task_contract_id="SUPERVISOR-TEST-1", **supervisor_overrides):
    payload = _payload(repo, **supervisor_overrides)
    payload.update(request_overrides or {})
    spec = {key: payload[key] for key in (
        "source_agent", "action", "title", "scope", "requested_paths", "allowed_paths",
        "forbidden_paths", "expected_tests", "acceptance_proof",
    )}
    spec["task_contract_id"] = task_contract_id
    item = WorkItem(
        work_item_id="SUPERVISOR-TEST-1",
        type=WorkItemType.TASK,
        parent_epic="LOCAL-EPIC",
        parent_feature="LOCAL-FEATURE",
        title=payload["title"],
        priority="P2",
        business_goal="Safely admit local supervisor work.",
        current_behavior="Supervisor accepts unbound contract files.",
        expected_behavior=payload["scope"],
        in_scope=("local supervisor admission",),
        out_of_scope=("trading runtime",),
        acceptance_criteria=tuple(payload["acceptance_proof"]),
        safety_constraints=("No broker calls", "No live execution"),
        architecture_impact="Local CLI admission only.",
        allowed_paths=tuple(payload["allowed_paths"]),
        forbidden_paths=tuple(payload["forbidden_paths"]),
        expected_tests=tuple(payload["expected_tests"]),
        qa_attack_plan=("missing item", "caller approval flags"),
        uat_criteria=("Mismatched task contract is blocked.",),
        release_gates=("Focused tests pass.",),
        rollback_plan="Remove local admission gate.",
        extensions={"agent_task_contracts": [spec]},
    )
    item_path = repo / "governance/evidence/work_items/SUPERVISOR-TEST-1.json"
    item_path.parent.mkdir(parents=True)
    item_path.write_text(json.dumps(work_item_to_dict(item), indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", str(item_path.relative_to(repo)))
    _git(repo, "commit", "-m", "add canonical supervisor task")
    payload["metadata"]["delivery_work_item"] = {
        "work_item_id": item.work_item_id,
        "path": str(item_path.relative_to(repo)),
        "sha256": hashlib.sha256(item_path.read_bytes()).hexdigest(),
        "task_contract_id": spec["task_contract_id"],
    }
    return payload


def _commit_test(repo: Path, *, passing: bool = True, credentials_must_be_absent: bool = False) -> str:
    assertion = "assert 1 + 1 == 2" if passing else "assert 1 + 1 == 3"
    lines = ["import os", "from pathlib import Path", "", "def test_feature():", f"    {assertion}"]
    if credentials_must_be_absent:
        lines.extend(
            [
                '    assert Path(".env").exists() is False',
                '    assert os.environ["PYTHONPATH"] == str(Path.cwd())',
            ]
        )
    (repo / "tests" / "test_feature.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _git(repo, "add", "tests/test_feature.py")
    _git(repo, "commit", "-m", "test: add feature proof")
    return _git(repo, "rev-parse", "HEAD")


def _reproduction_from_manifest(manifest: dict) -> list[dict]:
    return [
        {
            "name": item["name"],
            "argv": item["argv"],
            "exit_code": 0,
        }
        for item in manifest["acceptance_commands"]
    ]


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
    assert "ACCEPTANCE_COMMAND_DIRECT_PYTHON_BLOCKED" in blockers


def test_shape_blocks_arbitrary_python_module_and_path_escape(tmp_path):
    repo = _repo(tmp_path)
    arbitrary = normalize_supervisor_contract(
        _payload(
            repo,
            acceptance_commands=[
                {"name": "bad", "argv": ["python", "-m", "unsafe_module"], "timeout_seconds": 10}
            ],
        )
    )
    arbitrary_blockers, _ = validate_contract_shape(arbitrary)
    assert "ACCEPTANCE_COMMAND_PYTHON_MODULE_NOT_ALLOWED" in arbitrary_blockers

    absolute_executable = normalize_supervisor_contract(
        _payload(
            repo,
            acceptance_commands=[
                {"name": "bad", "argv": ["/tmp/python", "-m", "pytest"], "timeout_seconds": 10}
            ],
        )
    )
    executable_blockers, _ = validate_contract_shape(absolute_executable)
    assert "ACCEPTANCE_COMMAND_EXECUTABLE_PATH_BLOCKED" in executable_blockers

    escaped_argument = normalize_supervisor_contract(
        _payload(
            repo,
            acceptance_commands=[
                {"name": "bad", "argv": ["pytest", "/tmp/test_external.py"], "timeout_seconds": 10}
            ],
        )
    )
    argument_blockers, _ = validate_contract_shape(escaped_argument)
    assert "ACCEPTANCE_COMMAND_PATH_ESCAPE_BLOCKED" in argument_blockers


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
    assert manifest["acceptance_commands"][0]["execution_root"] == "credential_isolated_git_worktree"
    assert Path(manifest["acceptance_commands"][0]["resolved_executable"]).resolve() == Path(sys.executable).resolve()
    assert manifest["acceptance_execution"]["network_sandboxed"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["manifest_sha256"])
    assert Path(result.details["manifest_path"]).exists()


def test_verify_does_not_copy_ignored_env_or_inherit_pythonpath(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    (repo / ".env").write_text("KITE_ACCESS_TOKEN=secret\n", encoding="utf-8")
    _commit_test(repo, credentials_must_be_absent=True)

    result = verify_contract(contract)

    assert result.accepted is True
    command = result.details["manifest"]["acceptance_commands"][0]
    assert command["ignored_source_credentials_copied"] is False
    assert command["inherited_pythonpath_used"] is False


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
            "reproduction_results": _reproduction_from_manifest(manifest),
            "findings": [],
        },
    )
    assert approved.state == SupervisorState.REVIEW_APPROVED.value
    assert approved.accepted is True


def test_review_rejects_mismatched_reproduction_command(tmp_path):
    repo = _repo(tmp_path)
    contract = normalize_supervisor_contract(_payload(repo))
    assert claim_contract(contract, enforce_tradebot_guard=False).accepted is True
    head = _commit_test(repo)
    verified = verify_contract(contract)
    manifest = verified.details["manifest"]
    reproduction = _reproduction_from_manifest(manifest)
    reproduction[0]["argv"] = ["python", "-m", "pytest", "tests/other.py"]

    reviewed = record_independent_review(
        contract,
        {
            "schema_version": 1,
            "task_id": "test-task",
            "reviewer": "antigravity",
            "decision": "APPROVE",
            "summary": "Wrong command was reproduced.",
            "base_commit": manifest["base_commit"],
            "head_commit": head,
            "implementation_manifest_sha256": manifest["manifest_sha256"],
            "reproduction_results": reproduction,
        },
    )

    assert reviewed.accepted is False
    assert "REVIEW_REPRODUCTION_COMMAND_MISMATCH" in reviewed.blockers


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
            "reproduction_results": _reproduction_from_manifest(manifest),
        },
    )
    assert reviewed.accepted is False
    assert "IMPLEMENTATION_MANIFEST_HASH_INVALID" in reviewed.blockers


def test_load_contract_file(tmp_path: Path):
    payload_path = tmp_path / "task.json"
    payload_path.write_text(json.dumps({"task_id": "demo-task"}), encoding="utf-8")

    assert load_contract_file(payload_path) == {"task_id": "demo-task"}


def test_supervisor_cli_admission_accepts_committed_contract_and_claims(tmp_path, capsys):
    repo = _repo(tmp_path)
    payload = _admitted_payload(repo)
    contract_path = tmp_path / "supervisor.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    preflight_code = supervisor_cli_main(["preflight", "--contract", str(contract_path)])
    preflight = json.loads(capsys.readouterr().out)
    assert preflight_code == 0
    assert preflight["accepted"] is True

    claim_code = supervisor_cli_main(["claim", "--contract", str(contract_path)])
    claim = json.loads(capsys.readouterr().out)
    assert claim_code == 0
    assert claim["accepted"] is True
    assert claim["details"]["admission_decision"]["accepted"] is True


def test_supervisor_cli_blocks_missing_item_and_unauthenticated_approval(tmp_path, capsys):
    repo = _repo(tmp_path)
    payload = _payload(repo)
    contract_path = tmp_path / "supervisor.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    code = supervisor_cli_main([
        "claim", "--contract", str(contract_path), "--approve", "--approved-by", "caller"
    ])
    result = json.loads(capsys.readouterr().out)
    assert code != 0
    assert result["accepted"] is False
    assert "WORK_ITEM_REFERENCE_REQUIRED" in result["blockers"]

    risky = _admitted_payload(
        repo,
        request_overrides={
            "action": "GENERATE_PATCH",
            "title": "Patch risk control",
            "scope": "Modify a risk-control file.",
            "requested_paths": ["core/risk/position_sizing.py"],
            "allowed_paths": ["core/risk/"],
            "acceptance_proof": ["Risk boundary remains intact."],
        },
        ownership_paths=["core/risk/position_sizing.py"],
        required_artifacts=["core/risk/position_sizing.py"],
    )
    contract_path.write_text(json.dumps(risky), encoding="utf-8")
    code = supervisor_cli_main([
        "preflight", "--contract", str(contract_path), "--approve", "--approved-by", "caller"
    ])
    result = json.loads(capsys.readouterr().out)
    assert code != 0
    assert result["accepted"] is False
    assert "HUMAN_APPROVAL_REQUIRED" in result["blockers"]


def test_supervisor_cli_gates_every_mutation_before_writes(tmp_path, capsys):
    task_contract_id = "EVS-SUPERVISOR-MUTATION-ADMISSION-2026-10"
    command_cases = (
        ("preflight", []),
        ("claim", []),
        ("verify", []),
        ("review", ["--review", "review.json"]),
        ("release", []),
        ("release", ["--force"]),
    )
    for command_index, (command, extra_args) in enumerate(command_cases):
        for failure_index, failure in enumerate(("missing", "dirty", "stale", "mismatched")):
            repo = _repo(tmp_path, name=f"mutation-{command_index}-{failure_index}")
            payload = _admitted_payload(repo, task_contract_id=task_contract_id)
            item_path = repo / payload["metadata"]["delivery_work_item"]["path"]
            ref = payload["metadata"]["delivery_work_item"]
            if failure == "missing":
                payload["metadata"].pop("delivery_work_item")
                expected_blocker = "WORK_ITEM_REFERENCE_REQUIRED"
            elif failure == "dirty":
                item_path.write_text(item_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
                expected_blocker = "WORK_ITEM_DIRTY"
            elif failure == "stale":
                item_path.write_text(item_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
                _git(repo, "update-index", "--assume-unchanged", str(item_path.relative_to(repo)))
                expected_blocker = "WORK_ITEM_STALE"
            else:
                ref["sha256"] = "0" * 64
                expected_blocker = "WORK_ITEM_HASH_MISMATCH"
            contract_path = tmp_path / f"mutation-{command_index}-{failure_index}.json"
            contract_path.write_text(json.dumps(payload), encoding="utf-8")
            before = _git(repo, "status", "--porcelain=v1")
            review_arg = str(tmp_path / "review.json") if command == "review" else None
            if review_arg:
                Path(review_arg).write_text("{}", encoding="utf-8")
            argv = [command, "--contract", str(contract_path), *extra_args]
            if command == "review":
                argv[argv.index("review.json")] = review_arg
            code = supervisor_cli_main(argv)
            result = json.loads(capsys.readouterr().out)
            assert code == 2
            assert result["accepted"] is False
            assert expected_blocker in result["blockers"]
            assert _git(repo, "status", "--porcelain=v1") == before
            common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
            if not common_dir.is_absolute():
                common_dir = (repo / common_dir).resolve()
            assert not (common_dir / "agent-supervisor").exists()
            assert not (repo / ".runtime/agent_supervisor/evidence").exists()


def test_supervisor_cli_status_is_read_only_and_not_admitted(tmp_path, capsys):
    repo = _repo(tmp_path)
    payload = _payload(repo)
    contract_path = tmp_path / "status.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    before = _git(repo, "status", "--porcelain=v1")
    common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (repo / common_dir).resolve()
    claim_root = common_dir / "agent-supervisor"
    assert not claim_root.exists()

    code = supervisor_cli_main(["status", "--contract", str(contract_path)])

    result = json.loads(capsys.readouterr().out)
    assert code == 2  # Status reports the absent claim as blocked; it still performs no writes.
    assert result["state"] == SupervisorState.STATUS.value
    assert result["details"]["admission_decision"]["state"] == "NOT_CHECKED_READ_ONLY_STATUS"
    assert result["details"]["admission_decision"]["accepted"] is None
    assert _git(repo, "status", "--porcelain=v1") == before
    assert not claim_root.exists()
    assert not (repo / ".runtime/agent_supervisor/evidence").exists()


def test_supervisor_status_does_not_change_existing_claim_store(tmp_path, capsys):
    repo = _repo(tmp_path)
    payload = _payload(repo)
    contract = normalize_supervisor_contract(payload)
    common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (repo / common_dir).resolve()
    claim_root = common_dir / "agent-supervisor"
    claim_root.mkdir(parents=True)
    claims_path = claim_root / "claims.json"
    claims_path.write_text(
        '{"schema_version": 1, "claims": {"test-task": {"task_id": "test-task", "state": "ACTIVE"}}}',
        encoding="utf-8",
    )
    before = {path.name: path.read_bytes() for path in claim_root.iterdir() if path.is_file()}

    assert get_contract_status(contract).accepted is True
    contract_path = tmp_path / "status-existing.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    code = supervisor_cli_main(["status", "--contract", str(contract_path)])
    result = json.loads(capsys.readouterr().out)

    after = {path.name: path.read_bytes() for path in claim_root.iterdir() if path.is_file()}
    assert code == 0
    assert result["accepted"] is True  # A claim was found; admission remains explicitly unchecked.
    assert result["details"]["admission_decision"]["accepted"] is None
    assert after == before
    assert not (claim_root / "claims.lock").exists()


def test_supervisor_claim_write_creates_claim_store(tmp_path):
    repo = _repo(tmp_path)
    payload = _payload(repo)
    (repo / "tests/test_feature.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "tests/test_feature.py")
    _git(repo, "commit", "-m", "add required test artifact")
    contract = normalize_supervisor_contract(payload)
    common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (repo / common_dir).resolve()
    claim_root = common_dir / "agent-supervisor"
    assert not claim_root.exists()

    result = claim_contract(contract, human_approved=True, approved_by="test-operator", enforce_tradebot_guard=False)

    assert result.accepted is True
    assert (claim_root / "claims.lock").exists()
    assert (claim_root / "claims.json").exists()


def test_supervisor_cli_admitted_mutations_reach_existing_state_logic(tmp_path, capsys):
    repo = _repo(tmp_path)
    payload = _admitted_payload(repo, task_contract_id="EVS-SUPERVISOR-MUTATION-ADMISSION-2026-10")
    contract_path = tmp_path / "admitted.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    (repo / "tests/test_feature.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "tests/test_feature.py")
    _git(repo, "commit", "-m", "add test artifact")

    for command, extra_args in (("verify", []), ("review", ["--review", str(tmp_path / "review.json")]), ("release", ["--force"])):
        if command == "verify":
            code = supervisor_cli_main([command, "--contract", str(contract_path)])
            result = json.loads(capsys.readouterr().out)
            assert code == 2  # Existing state logic blocks before claim, after successful admission.
            assert result["details"]["admission_decision"]["accepted"] is True
            assert "ACTIVE_CLAIM_REQUIRED" in result["blockers"]
            continue
        if command == "review":
            review_path = Path(extra_args[1])
            review_path.write_text("{}", encoding="utf-8")
        code = supervisor_cli_main([command, "--contract", str(contract_path), *extra_args])
        result = json.loads(capsys.readouterr().out)
        assert code == 2
        assert result["details"]["admission_decision"]["accepted"] is True
        assert result["state"] in {SupervisorState.REVIEW_BLOCKED.value, SupervisorState.RELEASE_BLOCKED.value}
