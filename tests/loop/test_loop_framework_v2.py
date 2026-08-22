from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.loop.loop_core import (
    path_in_scope,
    read_json,
    recommend_next_action,
    redact_text,
    render_context,
    repo_root_from,
    validate_task,
)


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _task(tmp_path: Path, *, task_id: str = "LOOP-20260731-001") -> Path:
    task_dir = tmp_path / task_id
    contract = {
        "schema_version": 1,
        "task_id": task_id,
        "title": "Test bounded task",
        "objective": "Prove loop behavior without touching runtime.",
        "repository": "ramgolladi1503-sys/tradebot",
        "base_branch": "main",
        "work_branch": "test/loop",
        "pr_number": None,
        "owner": "human",
        "preferred_worker": "codex",
        "reviewer": "chatgpt-or-antigravity",
        "allowed_paths": ["docs/test/**"],
        "forbidden_paths": ["secrets/**"],
        "acceptance_gates": ["GATE-1"],
        "required_tests": ["pytest -q tests/loop"],
        "human_gates": [],
        "stop_conditions": ["external_blocker"],
        "max_implementation_cycles": 3,
        "max_review_cycles": 2,
        "created_at_utc": "2026-07-31T00:00:00Z",
        "frozen": True,
    }
    state = {
        "schema_version": 1,
        "task_id": task_id,
        "state": "NEW",
        "previous_state": None,
        "cycle": 0,
        "code_sha": "a" * 40,
        "base_sha": "b" * 40,
        "branch": "test/loop",
        "worker": "human",
        "started_at_utc": "2026-07-31T00:00:00Z",
        "checkpointed_at_utc": "2026-07-31T00:00:00Z",
        "completed_gate_ids": [],
        "failed_gate_ids": [],
        "blockers": [],
        "next_action": "Implement one bounded change.",
        "next_worker": "codex",
        "human_approval_required": False,
    }
    handoff = {
        "schema_version": 1,
        "task_id": task_id,
        "worker": "human",
        "code_sha": "a" * 40,
        "branch": "test/loop",
        "pr_number": None,
        "changed_paths": [],
        "files_intentionally_not_touched": [],
        "commands": [],
        "test_results": [],
        "claims_created": [],
        "claims_retired": [],
        "unresolved_findings": [],
        "blockers": [],
        "next_action": "Implement one bounded change.",
        "next_worker": "codex",
        "local_only_evidence": [],
        "all_continuation_critical_artifacts_in_github": True,
        "checkpointed_at_utc": "2026-07-31T00:00:00Z",
    }
    _write(task_dir / "contract.json", contract)
    _write(task_dir / "state.json", state)
    _write(task_dir / "handoff.json", handoff)
    _write(task_dir / "claims.json", {"schema_version": 1, "claims": []})
    _write(task_dir / "evidence" / "manifest.json", {"schema_version": 1, "task_id": task_id, "proofs": []})
    (task_dir / "CONTINUE.md").write_text("placeholder\n", encoding="utf-8")
    return task_dir


def _errors(task_dir: Path) -> list[str]:
    return validate_task(task_dir, repo_root=repo_root_from(), check_git=False)


def test_valid_task_contract_passes(tmp_path):
    assert _errors(_task(tmp_path)) == []


def test_empty_allowed_paths_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    contract = read_json(task_dir / "contract.json")
    contract["allowed_paths"] = []
    _write(task_dir / "contract.json", contract)
    assert any("allowed_paths" in error for error in _errors(task_dir))


def test_legal_and_illegal_transitions(tmp_path):
    legal = _task(tmp_path / "legal")
    state = read_json(legal / "state.json")
    state.update({"previous_state": "NEW", "state": "IMPLEMENTING", "cycle": 1})
    _write(legal / "state.json", state)
    assert not any("illegal transition" in error for error in _errors(legal))

    illegal = _task(tmp_path / "illegal")
    state = read_json(illegal / "state.json")
    state.update({"previous_state": "NEW", "state": "DONE", "cycle": 1})
    _write(illegal / "state.json", state)
    assert any("illegal transition" in error for error in _errors(illegal))


def test_scope_decisions_include_dot_prefixed_paths():
    assert path_in_scope("docs/test/report.md", ["docs/test/**"], ["secrets/**"])[0] is True
    assert path_in_scope("secrets/key.txt", ["**"], ["secrets/**"])[1] == "forbidden"
    assert path_in_scope("core/feed/runtime.py", ["docs/**"], [])[1] == "outside_allowed_paths"
    assert path_in_scope(".loop/README.md", [".loop/**"], [])[0] is True
    assert path_in_scope(
        ".github/workflows/loop-handoff-gate.yml",
        [".github/workflows/loop-handoff-gate.yml"],
        [],
    )[0] is True
    assert path_in_scope(".env", ["**"], [".env"])[1] == "forbidden"


def test_proven_claim_requires_existing_proof(tmp_path):
    no_proof = _task(tmp_path / "no-proof")
    _write(no_proof / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-1", "statement": "Claim", "status": "PROVEN", "proof_ids": []}]})
    assert any("has no proof_ids" in error for error in _errors(no_proof))

    missing = _task(tmp_path / "missing")
    _write(missing / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-1", "statement": "Claim", "status": "PROVEN", "proof_ids": ["NOPE"]}]})
    assert any("missing proof IDs" in error for error in _errors(missing))


def test_file_evidence_hash_is_verified(tmp_path):
    mismatched = _task(tmp_path / "mismatch")
    (mismatched / "proof.txt").write_text("truth\n", encoding="utf-8")
    _write(mismatched / "evidence" / "manifest.json", {"schema_version": 1, "task_id": mismatched.name, "proofs": [{"proof_id": "P-1", "tier": "A", "evidence_class": "test", "evidence_type": "file", "reference": "proof.txt", "sha256": "0" * 64, "exit_code": 0, "required": True}]})
    assert any("sha256 mismatch" in error for error in _errors(mismatched))

    valid = _task(tmp_path / "valid")
    proof = valid / "proof.txt"
    proof.write_text("truth\n", encoding="utf-8")
    digest = hashlib.sha256(proof.read_bytes()).hexdigest()
    _write(valid / "evidence" / "manifest.json", {"schema_version": 1, "task_id": valid.name, "proofs": [{"proof_id": "P-1", "tier": "A", "evidence_class": "test", "evidence_type": "file", "reference": "proof.txt", "sha256": digest, "exit_code": 0, "required": True}]})
    _write(valid / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-1", "statement": "Claim", "status": "PROVEN", "proof_ids": ["P-1"]}]})
    assert _errors(valid) == []


def test_local_reference_and_replay_live_claim_are_rejected(tmp_path):
    local = _task(tmp_path / "local")
    _write(local / "evidence" / "manifest.json", {"schema_version": 1, "task_id": local.name, "proofs": [{"proof_id": "P-1", "tier": "B", "evidence_class": "ci", "evidence_type": "artifact", "reference": "/tmp/local.log", "exit_code": 0}]})
    assert any("absolute/local path" in error for error in _errors(local))

    replay = _task(tmp_path / "replay")
    _write(replay / "evidence" / "manifest.json", {"schema_version": 1, "task_id": replay.name, "proofs": [{"proof_id": "P-1", "tier": "B", "evidence_class": "replay", "evidence_type": "artifact", "reference": "github-actions:run-1/artifact-1", "exit_code": 0}]})
    _write(replay / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-LIVE", "statement": "Live gate passed", "status": "PROVEN", "proof_ids": ["P-1"], "requires_live_evidence": True}]})
    assert any("lacks live evidence" in error for error in _errors(replay))


def test_state_blockers_and_cycle_budget_fail_closed(tmp_path):
    certified = _task(tmp_path / "certified")
    state = read_json(certified / "state.json")
    state.update({"previous_state": "REVIEWING", "state": "OFFLINE_CERTIFIED", "cycle": 2, "blockers": ["missing proof"]})
    _write(certified / "state.json", state)
    assert any("cannot have unresolved blockers" in error for error in _errors(certified))

    blocked = _task(tmp_path / "blocked")
    state = read_json(blocked / "state.json")
    state.update({"previous_state": "NEW", "state": "BLOCKED", "cycle": 1, "blockers": []})
    _write(blocked / "state.json", state)
    assert any("requires at least one blocker" in error for error in _errors(blocked))

    exhausted = _task(tmp_path / "exhausted")
    state = read_json(exhausted / "state.json")
    state["cycle"] = 6
    _write(exhausted / "state.json", state)
    assert any("cycle budget exhausted" in error for error in _errors(exhausted))


def test_failed_required_test_blocks_success(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "REVIEWING", "state": "OFFLINE_CERTIFIED", "cycle": 2})
    _write(task_dir / "state.json", state)
    handoff = read_json(task_dir / "handoff.json")
    handoff["test_results"] = [{"test_id": "TEST-1", "required": True, "exit_code": 1}]
    _write(task_dir / "handoff.json", handoff)
    assert any("failed required test" in error for error in _errors(task_dir))


def test_compact_context_is_bounded_and_marks_truncation(tmp_path):
    task_dir = _task(tmp_path)
    contract = read_json(task_dir / "contract.json")
    contract["objective"] = "x" * 20000
    _write(task_dir / "contract.json", contract)
    context = render_context(task_dir, max_bytes=2048)
    context_size = len(context.encode("utf-8"))
    assert context_size <= 2200
    assert "Context truncated" in context


def test_redaction_masks_credential_fields():
    text = redact_text("api_" + "key=alpha pass" + "word=beta access_" + "token=gamma")
    assert "alpha" not in text
    assert "beta" not in text
    assert "gamma" not in text
    assert text.count("<redacted>") == 3


def test_next_action_routes_required_failure_to_repair(tmp_path):
    task_dir = _task(tmp_path)
    contract = read_json(task_dir / "contract.json")
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "IMPLEMENTING", "state": "TESTING", "cycle": 1})
    handoff = read_json(task_dir / "handoff.json")
    handoff["test_results"] = [{"test_id": "TEST-1", "required": True, "exit_code": 1}]
    result = recommend_next_action(contract, state, handoff)
    assert result["state"] == "REPAIRING"


def test_init_task_rejects_duplicate(tmp_path):
    root = repo_root_from()
    command = [
        sys.executable,
        "scripts/loop/init_task.py",
        "--task-id", "LOOP-20260731-999",
        "--title", "Duplicate test",
        "--objective", "Test duplicate rejection",
        "--allowed-path", "docs/test/**",
        "--task-root", str(tmp_path),
    ]
    first = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    assert first.returncode == 0
    assert second.returncode != 0


def test_checkpoint_requires_explicit_commit_before_push():
    root = repo_root_from()
    source = (root / "scripts/loop/checkpoint.py").read_text(encoding="utf-8")
    assert "if args.push and not args.commit" in source
    assert "if args.push:" in source


def test_framework_contains_no_merge_invocation():
    root = repo_root_from()
    for path in (root / "scripts/loop").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "merge_pull_request(" not in source
        assert "enable_auto_merge(" not in source
        assert '["git", "merge"' not in source
