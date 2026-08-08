#!/usr/bin/env python3
"""Fresh-context Codex backend adapter for the MROS local agent bridge.

The adapter passes the complete role packet as a positional prompt (not stdin),
uses an ephemeral Codex session, constrains the agent to a read-only repository
sandbox, and asks Codex itself to write only the last agent message to the output
artifact via --output-last-message.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one isolated MROS job with Codex")
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=os.environ.get("MROS_CODEX_MODEL", ""))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    worktree = args.worktree.resolve()
    packet = args.packet.resolve()
    output = args.output.resolve()

    if shutil.which("codex") is None:
        print("MROS_CODEX_BACKEND_BLOCKED: codex CLI not found", file=sys.stderr)
        return 20
    if not worktree.is_dir() or not (worktree / ".git").exists():
        print("MROS_CODEX_BACKEND_BLOCKED: detached worktree invalid", file=sys.stderr)
        return 21
    if not packet.is_file():
        print("MROS_CODEX_BACKEND_BLOCKED: packet missing", file=sys.stderr)
        return 22
    if output.exists():
        print("MROS_CODEX_BACKEND_BLOCKED: output already exists", file=sys.stderr)
        return 23

    prompt = packet.read_text(encoding="utf-8")
    if not prompt.strip():
        print("MROS_CODEX_BACKEND_BLOCKED: empty packet", file=sys.stderr)
        return 24

    candidate = os.environ.get("MROS_CANDIDATE_SHA", "")
    role_id = os.environ.get("MROS_ROLE_ID", "")
    job_type = os.environ.get("MROS_JOB_TYPE", "")
    job_id = os.environ.get("MROS_JOB_ID", "")
    boundary = f"""

---
MROS EXECUTION BOUNDARY (injected by the isolated bridge)
- job_id: {job_id}
- job_type: {job_type}
- role_id: {role_id}
- exact candidate SHA: {candidate}
- repository worktree: {worktree}
- runtime authority: NONE
- broker actions allowed: false

You are running in a fresh ephemeral process. Do not resume or import a prior
conversation. Do not read peer reviewer/auditor outputs unless the supplied
packet explicitly requires them for an auditor role. Do not repair or modify the
candidate. Your final response must be the complete review/audit artifact content
required by the packet; do not wrap it in chat commentary.
---
"""
    final_prompt = prompt + boundary

    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--output-last-message",
        str(output),
    ]
    if args.model:
        command.extend(["--model", args.model])
    command.append(final_prompt)

    completed = subprocess.run(
        command,
        cwd=worktree,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=int(os.environ.get("MROS_CODEX_TIMEOUT_SECONDS", "3600")),
        check=False,
    )
    sys.stdout.write(completed.stdout or "")
    if completed.returncode != 0:
        return completed.returncode
    if not output.is_file() or not output.read_text(encoding="utf-8").strip():
        print("MROS_CODEX_BACKEND_BLOCKED: Codex returned no final artifact", file=sys.stderr)
        return 25
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
