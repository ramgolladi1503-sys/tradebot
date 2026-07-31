#!/usr/bin/env python3
"""Create an interrupt-safe task checkpoint after an implementation commit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from loop_core import (  # noqa: E402
    changed_paths,
    current_branch,
    current_head,
    git_is_clean,
    read_json,
    render_context,
    repo_root_from,
    utc_now,
    validate_task,
    write_json,
)


def _load_list(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"expected a JSON list of objects: {path}")
    return payload


def _git(repo_root: Path, *args: str) -> None:
    proc = subprocess.run(["git", *args], cwd=repo_root, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--state", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--next-action", required=True)
    parser.add_argument("--next-worker", default="codex")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--blocker", action="append", default=[])
    parser.add_argument("--completed-gate", action="append", default=[])
    parser.add_argument("--failed-gate", action="append", default=[])
    parser.add_argument("--unresolved-finding", action="append", default=[])
    parser.add_argument("--intentionally-not-touched", action="append", default=[])
    parser.add_argument("--local-only-evidence", action="append", default=[])
    parser.add_argument("--continuation-critical-local-evidence", action="store_true")
    parser.add_argument("--test-results-file", type=Path)
    parser.add_argument("--commands-file", type=Path)
    parser.add_argument("--human-approval-required", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    if args.push and not args.commit:
        parser.error("--push requires --commit")

    root = repo_root_from()
    task_dir = (args.task_dir if args.task_dir.is_absolute() else root / args.task_dir).resolve()
    if not git_is_clean(root):
        parser.error("worktree must be clean before checkpoint generation; commit implementation changes first")

    contract = read_json(task_dir / "contract.json")
    old_state = read_json(task_dir / "state.json")
    code_sha = current_head(root)
    base_sha = str(old_state.get("base_sha") or "")
    if not base_sha:
        parser.error("state.base_sha is required")
    paths = changed_paths(root, base_sha, code_sha)
    now = utc_now()
    cycle = int(old_state.get("cycle", 0)) + 1
    state = {
        **old_state,
        "state": args.state,
        "previous_state": old_state.get("state"),
        "cycle": cycle,
        "code_sha": code_sha,
        "branch": current_branch(root),
        "worker": args.worker,
        "checkpointed_at_utc": now,
        "completed_gate_ids": sorted(set(args.completed_gate or old_state.get("completed_gate_ids") or [])),
        "failed_gate_ids": sorted(set(args.failed_gate or [])),
        "blockers": list(args.blocker),
        "next_action": args.next_action,
        "next_worker": args.next_worker,
        "human_approval_required": bool(args.human_approval_required),
    }
    test_results = _load_list(args.test_results_file)
    commands = _load_list(args.commands_file)
    handoff = {
        "schema_version": 1,
        "task_id": contract["task_id"],
        "worker": args.worker,
        "code_sha": code_sha,
        "branch": current_branch(root),
        "pr_number": args.pr_number if args.pr_number is not None else contract.get("pr_number"),
        "changed_paths": paths,
        "files_intentionally_not_touched": list(args.intentionally_not_touched),
        "commands": commands,
        "test_results": test_results,
        "claims_created": [],
        "claims_retired": [],
        "unresolved_findings": list(args.unresolved_finding),
        "blockers": list(args.blocker),
        "next_action": args.next_action,
        "next_worker": args.next_worker,
        "local_only_evidence": list(args.local_only_evidence),
        "all_continuation_critical_artifacts_in_github": not bool(args.continuation_critical_local_evidence),
        "checkpointed_at_utc": now,
    }
    write_json(task_dir / "state.json", state)
    write_json(task_dir / "handoff.json", handoff)
    (task_dir / "CONTINUE.md").write_text(render_context(task_dir), encoding="utf-8")

    errors = validate_task(task_dir, repo_root=root, check_git=True)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, "task_id": contract["task_id"], "code_sha": code_sha, "cycle": cycle}, sort_keys=True))
    if args.commit:
        relative = task_dir.relative_to(root).as_posix()
        _git(root, "add", "--", relative)
        _git(root, "commit", "-m", f"checkpoint(loop): {contract['task_id']} cycle {cycle}")
        if args.push:
            _git(root, "push", "-u", "origin", current_branch(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
