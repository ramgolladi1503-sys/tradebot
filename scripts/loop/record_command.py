#!/usr/bin/env python3
"""Run one command and record a bounded, redacted result for loop evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from loop_core import current_head, redact_text, repo_root_from, sha256_file, utc_now  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--command-id", required=True)
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--save-full-output", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    root = repo_root_from()
    task_dir = (args.task_dir if args.task_dir.is_absolute() else root / args.task_dir).resolve()
    evidence_dir = task_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    monotonic_start = time.monotonic()
    proc = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    ended = utc_now()
    duration = time.monotonic() - monotonic_start
    stdout = redact_text(proc.stdout or "")
    stderr = redact_text(proc.stderr or "")
    result = {
        "command_id": args.command_id,
        "command": [redact_text(part, max_chars=512) for part in command],
        "working_directory": ".",
        "started_at_utc": started,
        "ended_at_utc": ended,
        "duration_seconds": round(duration, 6),
        "exit_code": int(proc.returncode),
        "required": bool(args.required),
        "stdout_summary": stdout,
        "stderr_summary": stderr,
        "code_sha": current_head(root),
    }
    if args.save_full_output:
        output_path = evidence_dir / f"{args.command_id}.log"
        output_path.write_text(f"STDOUT\n{redact_text(proc.stdout or '', max_chars=200000)}\nSTDERR\n{redact_text(proc.stderr or '', max_chars=200000)}\n", encoding="utf-8")
        result["full_output_reference"] = output_path.relative_to(task_dir).as_posix()
        result["full_output_sha256"] = sha256_file(output_path)

    index_path = evidence_dir / "commands.json"
    existing = []
    if index_path.exists():
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            existing = loaded
    existing = [item for item in existing if item.get("command_id") != args.command_id]
    existing.append(result)
    index_path.write_text(json.dumps(existing, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
