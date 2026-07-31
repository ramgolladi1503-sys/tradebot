#!/usr/bin/env python3
"""Validate one GitHub-first loop task and return nonzero on any defect."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from loop_core import framework_paths_have_merge_actions, repo_root_from, validate_task  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--no-git", action="store_true", help="Skip ancestry and diff scope checks.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = repo_root_from()
    task_dir = args.task_dir if args.task_dir.is_absolute() else root / args.task_dir
    errors = validate_task(task_dir, repo_root=root, check_git=not args.no_git)
    errors.extend(framework_paths_have_merge_actions(root))
    payload = {
        "ok": not errors,
        "task_dir": str(task_dir.relative_to(root)),
        "errors": errors,
    }
    if args.as_json:
        print(json.dumps(payload, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(f"PASS: {payload['task_dir']}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
