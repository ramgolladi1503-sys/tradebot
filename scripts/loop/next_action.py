#!/usr/bin/env python3
"""Return the deterministic next state/action recommendation for a loop task."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from loop_core import read_json, recommend_next_action, repo_root_from  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    args = parser.parse_args()
    root = repo_root_from()
    task_dir = args.task_dir if args.task_dir.is_absolute() else root / args.task_dir
    result = recommend_next_action(
        read_json(task_dir / "contract.json"),
        read_json(task_dir / "state.json"),
        read_json(task_dir / "handoff.json"),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
