#!/usr/bin/env python3
"""Fresh-context Codex backend adapter for the MROS local agent bridge.

Reviewer/auditor jobs run through an ephemeral read-only Codex sandbox. The one
special case is the deterministic S003 Board calibration packet: that packet is
not a review job semantically and requires writable temporary Git state, so the
adapter executes one fixed allowlisted calibration command natively in the exact
candidate worktree and writes a machine-readable Markdown result. No arbitrary
packet command is executed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CALIBRATION_MARKER = "# S003 autonomous exact-head Board calibration"
CALIBRATION_SCRIPT = "scripts/mros/calibrate_review_audit_board_v2.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one isolated MROS job with Codex")
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=os.environ.get("MROS_CODEX_MODEL", ""))
    return parser.parse_args()


def _run_native_calibration(*, worktree: Path, output: Path, candidate: str) -> int:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    actual_head = (head.stdout or "").strip()
    if head.returncode != 0 or actual_head != candidate:
        print("MROS_NATIVE_CALIBRATION_BLOCKED: exact candidate mismatch", file=sys.stderr)
        return 26

    py = subprocess.run(
        [sys.executable, "--version"],
        cwd=worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    pyver = (py.stdout or "").strip()
    command = [sys.executable, CALIBRATION_SCRIPT, "--candidate-head", candidate]
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="mros-native-cal-") as td:
        env["TMPDIR"] = td
        completed = subprocess.run(
            command,
            cwd=worktree,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=int(os.environ.get("MROS_NATIVE_CALIBRATION_TIMEOUT_SECONDS", "1200")),
            check=False,
        )
    stdout = completed.stdout or ""
    passed = completed.returncode == 0 and "S003_BOARD_DETERMINISTIC_CALIBRATION_PASS" in stdout
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(
            [
                f"CANDIDATE_HEAD: `{actual_head}`",
                "",
                f"PYTHON_VERSION: `{pyver}`",
                "",
                "COMMAND:",
                "",
                "```bash",
                f"{sys.executable} {CALIBRATION_SCRIPT} --candidate-head {candidate}",
                "```",
                "",
                "COMPLETE STDOUT:",
                "",
                "```text",
                stdout.rstrip(),
                "```",
                "",
                f"EXIT_CODE: `{completed.returncode}`",
                "",
                "RUNTIME_AUTHORITY=NONE",
                "",
                "BROKER_ACTIONS=NONE",
                "",
                f"CALIBRATION_EXECUTION_RESULT={'PASS' if passed else 'FAIL'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    # The isolated job itself succeeded even when deterministic validation says FAIL.
    # The controller consumes CALIBRATION_EXECUTION_RESULT and decides repair vs pass.
    return 0


def main() -> int:
    args = parse_args()
    worktree = args.worktree.resolve()
    packet = args.packet.resolve()
    output = args.output.resolve()

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

    if prompt.startswith(CALIBRATION_MARKER):
        return _run_native_calibration(worktree=worktree, output=output, candidate=candidate)

    if shutil.which("codex") is None:
        print("MROS_CODEX_BACKEND_BLOCKED: codex CLI not found", file=sys.stderr)
        return 20

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

TRANSPORT FACTS (authoritative and fail-closed):
- The complete frozen review/audit packet is the prompt text immediately above
  this boundary. It is transported from the queue branch by the bridge and is
  intentionally NOT committed into the detached exact-candidate worktree.
- Therefore, absence of packet_path inside the candidate worktree is expected
  transport isolation and MUST NOT by itself produce UNKNOWN, MAJOR, or CRITICAL.
  Packet population/freeze/provenance is validated independently by the
  controller/aggregator against queue-branch receipts and manifests.
- The sandbox is intentionally read-only. A test that requires a writable temp
  directory may be unavailable here. Do not convert that sandbox property into
  UNKNOWN when deterministic exact-head native evidence is supplied and can be
  inspected. Static/adversarial inspection remains mandatory and blocking code
  defects must still be reported.
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
