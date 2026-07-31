#!/usr/bin/env python3
"""Initialize a bounded GitHub-first loop task."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from loop_core import (  # noqa: E402
    current_branch,
    current_head,
    read_json,
    render_context,
    repo_root_from,
    utc_now,
    validate_contract,
    write_json,
)


def _display_path(path: Path, root: Path) -> Path:
    """Prefer a repository-relative path without rejecting external test roots."""
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--work-branch")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--owner", default="human")
    parser.add_argument("--preferred-worker", default="codex")
    parser.add_argument("--reviewer", default="chatgpt-or-antigravity")
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--forbidden-path", action="append", default=[])
    parser.add_argument("--acceptance-gate", action="append", default=[])
    parser.add_argument("--required-test", action="append", default=[])
    parser.add_argument("--human-gate", action="append", default=[])
    parser.add_argument("--stop-condition", action="append", default=[])
    parser.add_argument("--max-implementation-cycles", type=int, default=3)
    parser.add_argument("--max-review-cycles", type=int, default=2)
    parser.add_argument("--task-root", type=Path, default=Path("loop_tasks"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    root = repo_root_from()
    task_dir = (root / args.task_root / args.task_id).resolve()
    if task_dir.exists():
        if not args.resume:
            parser.error(f"task already exists: {task_dir}")
        contract = read_json(task_dir / "contract.json")
        errors = validate_contract(contract)
        if errors:
            parser.error("existing task is invalid: " + "; ".join(errors))
        print(_display_path(task_dir, root))
        return 0

    now = utc_now()
    base_sha = current_head(root)
    branch = args.work_branch or current_branch(root)
    contract = {
        "schema_version": 1,
        "task_id": args.task_id,
        "title": args.title,
        "objective": args.objective,
        "repository": "ramgolladi1503-sys/tradebot",
        "base_branch": args.base_branch,
        "work_branch": branch,
        "pr_number": None,
        "owner": args.owner,
        "preferred_worker": args.preferred_worker,
        "reviewer": args.reviewer,
        "allowed_paths": args.allowed_path,
        "forbidden_paths": args.forbidden_path,
        "acceptance_gates": args.acceptance_gate,
        "required_tests": args.required_test,
        "human_gates": args.human_gate,
        "stop_conditions": args.stop_condition,
        "max_implementation_cycles": args.max_implementation_cycles,
        "max_review_cycles": args.max_review_cycles,
        "created_at_utc": now,
        "frozen": True,
    }
    errors = validate_contract(contract)
    if errors:
        parser.error("invalid contract: " + "; ".join(errors))

    state = {
        "schema_version": 1,
        "task_id": args.task_id,
        "state": "NEW",
        "previous_state": None,
        "cycle": 0,
        "code_sha": base_sha,
        "base_sha": base_sha,
        "branch": branch,
        "worker": "human",
        "started_at_utc": now,
        "checkpointed_at_utc": now,
        "completed_gate_ids": [],
        "failed_gate_ids": [],
        "blockers": [],
        "next_action": "Perform one bounded implementation cycle within allowed_paths.",
        "next_worker": args.preferred_worker,
        "human_approval_required": False,
    }
    handoff = {
        "schema_version": 1,
        "task_id": args.task_id,
        "worker": "human",
        "code_sha": base_sha,
        "branch": branch,
        "pr_number": None,
        "changed_paths": [],
        "files_intentionally_not_touched": [],
        "commands": [],
        "test_results": [],
        "claims_created": [],
        "claims_retired": [],
        "unresolved_findings": [],
        "blockers": [],
        "next_action": state["next_action"],
        "next_worker": args.preferred_worker,
        "local_only_evidence": [],
        "all_continuation_critical_artifacts_in_github": True,
        "checkpointed_at_utc": now,
    }
    task_dir.mkdir(parents=True)
    (task_dir / "evidence").mkdir()
    write_json(task_dir / "contract.json", contract)
    write_json(task_dir / "state.json", state)
    write_json(task_dir / "handoff.json", handoff)
    write_json(task_dir / "claims.json", {"schema_version": 1, "claims": []})
    write_json(task_dir / "evidence" / "manifest.json", {"schema_version": 1, "task_id": args.task_id, "proofs": []})
    (task_dir / "CONTINUE.md").write_text(render_context(task_dir), encoding="utf-8")
    print(_display_path(task_dir, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
