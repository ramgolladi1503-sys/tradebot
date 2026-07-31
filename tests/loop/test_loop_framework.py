from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

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
        "objective": "Prove the loop contracts without touching runtime.",
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


def test_legal_transition_is_accepted(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "NEW", "state": "IMPLEMENTING", "cycle": 1})
    _write(task_dir / "state.json", state)
    assert not any("illegal transition" in error for error in _errors(task_dir))


def test_illegal_transition_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "NEW", "state": "DONE", "cycle": 1})
    _write(task_dir / "state.json", state)
    assert any("illegal transition" in error for error in _errors(task_dir))


def test_allowed_and_forbidden_path_decisions():
    assert path_in_scope("docs/test/report.md", ["docs/test/**"], ["secrets/**"])[0] is True
    assert path_in_scope("secrets/key.txt", ["**"], ["secrets/**"])[1] == "forbidden"
    assert path_in_scope("core/feed/runtime.py", ["docs/**"], [])[1] == "outside_allowed_paths"


def test_proven_claim_without_proof_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    _write(task_dir / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-1", "statement": "Claim", "status": "PROVEN", "proof_ids": []}]})
    assert any("has no proof_ids" in error for error in _errors(task_dir))


def test_missing_proof_reference_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    _write(task_dir / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-1", "statement": "Claim", "status": "PROVEN", "proof_ids": ["NOPE"]}]})
    assert any("missing proof IDs" in error for error in _errors(task_dir))


def test_file_evidence_hash_mismatch_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    (task_dir / "proof.txt").write_text("truth\n", encoding="utf-8")
    _write(task_dir / "evidence" / "manifest.json", {"schema_version": 1, "task_id": task_dir.name, "proofs": [{"proof_id": "P-1", "tier": "A", "evidence_class": "test", "evidence_type": "file", "reference": "proof.txt", "sha256": "0" * 64, "exit_code": 0, "required": True}]})
    assert any("sha256 mismatch" in error for error in _errors(task_dir))


def test_valid_file_evidence_and_claim_pass(tmp_path):
    task_dir = _task(tmp_path)
    proof = task_dir / "proof.txt"
    proof.write_text("truth\n", encoding="utf-8")
    digest = hashlib.sha256(proof.read_bytes()).hexdigest()
    _write(task_dir / "evidence" / "manifest.json", {"schema_version": 1, "task_id": task_dir.name, "proofs": [{"proof_id": "P-1", "tier": "A", "evidence_class": "test", "evidence_type": "file", "reference": "proof.txt", "sha256": digest, "exit_code": 0, "required": True}]})
    _write(task_dir / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-1", "statement": "Claim", "status": "PROVEN", "proof_ids": ["P-1"]}]})
    assert _errors(task_dir) == []


def test_absolute_local_path_cannot_be_authoritative(tmp_path):
    task_dir = _task(tmp_path)
    _write(task_dir / "evidence" / "manifest.json", {"schema_version": 1, "task_id": task_dir.name, "proofs": [{"proof_id": "P-1", "tier": "B", "evidence_class": "ci", "evidence_type": "artifact", "reference": "/Users/example/local.log", "exit_code": 0}]})
    assert any("absolute/local path" in error for error in _errors(task_dir))


def test_replay_evidence_cannot_prove_live_claim(tmp_path):
    task_dir = _task(tmp_path)
    _write(task_dir / "evidence" / "manifest.json", {"schema_version": 1, "task_id": task_dir.name, "proofs": [{"proof_id": "P-1", "tier": "B", "evidence_class": "replay", "evidence_type": "artifact", "reference": "github-actions:run-1/artifact-1", "exit_code": 0}]})
    _write(task_dir / "claims.json", {"schema_version": 1, "claims": [{"claim_id": "CLM-LIVE", "statement": "Live gate passed", "status": "PROVEN", "proof_ids": ["P-1"], "requires_live_evidence": True}]})
    assert any("lacks live evidence" in error for error in _errors(task_dir))


def test_success_state_with_blocker_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "REVIEWING", "state": "OFFLINE_CERTIFIED", "cycle": 2, "blockers": ["missing proof"]})
    _write(task_dir / "state.json", state)
    assert any("cannot have unresolved blockers" in error for error in _errors(task_dir))


def test_blocked_state_requires_blocker(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "NEW", "state": "BLOCKED", "cycle": 1, "blockers": []})
    _write(task_dir / "state.json", state)
    assert any("requires at least one blocker" in error for error in _errors(task_dir))


def test_cycle_budget_exhaustion_is_rejected(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state["cycle"] = 6
    _write(task_dir / "state.json", state)
    assert any("cycle budget exhausted" in error for error in _errors(task_dir))


def test_failed_required_test_blocks_success(tmp_path):
    task_dir = _task(tmp_path)
    state = read_json(task_dir / "state.json")
    state.update({"previous_state": "REVIEWING", "state": "OFFLINE_CERTIFIED", "cycle": 2})
    _write(task_dir / "state.json", state)
    handoff = read_json(task_dir / "handoff.json")
    handoff["test_results"] = [{"test_id": "TEST-1", "required": True, "exit_code": 1}]
    _write(task_dir / "handoff.json", handoff)
    assert any("failed required test" in error for error in _errors(task_dir))


def test_compact_context_respects_size_guard(tmp_path):
    task_dir = _task(tmp_path)
    contract = read_json(task_dir / "contract.json")
    contract["objective"] = "x" * 20000
    _write(task_dir / "contract.json", contract)
    context = render_context(task_dir, max_bytes=2048)
    assert len(context.encode("utf-8")) <= 2200
    assert "Context truncated" in context


def test_redaction_masks_common_credentials():
    text = redact_text("api_key=abc123 password:secret access_token=qwerty")
    assert "abc123" not in text
    assert "secret" not in text
    assert "qwerty" not in text
    assert text.count("<redacted>") == 3


def test_next_action_routes_failed_test_to_repair(tmp_path):
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


def test_checkpoint_push_requires_explicit_commit_flag():
    root = repo_root_from()
    source = (root / "scripts/loop/checkpoint.py").read_text(encoding="utf-8")
    assert "if args.push and not args.commit" in source
    assert "if args.push:" in source


def test_framework_has_no_merge_or_auto_merge_invocation():
    root = repo_root_from()
    for path in (root / "scripts/loop").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "merge_pull_request(" not in source
        assert "enable_auto_merge(" not in source
        assert '["git", "merge"' not in source
