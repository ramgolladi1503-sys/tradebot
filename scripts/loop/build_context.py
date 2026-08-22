#!/usr/bin/env python3
"""Build a bounded continuation packet for the next worker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from loop_core import render_context, repo_root_from  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-bytes", type=int, default=8192)
    args = parser.parse_args()
    if args.max_bytes < 1024:
        parser.error("--max-bytes must be at least 1024")

    root = repo_root_from()
    task_dir = args.task_dir if args.task_dir.is_absolute() else root / args.task_dir
    text = render_context(task_dir.resolve(), max_bytes=args.max_bytes)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(output)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
