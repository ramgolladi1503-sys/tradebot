#!/usr/bin/env python3
import subprocess
import sys
from typing import List


CHECKS = [
    (
        "manual-approval-invariant",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_order_approval_store.py",
            "tests/test_manual_approval_enforcement.py",
            "tests/test_manual_approval_sample_run.py",
        ],
    ),
]


def _run(name: str, cmd: List[str]) -> int:
    print(f"[RUN] {name}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[FAIL] {name}: {' '.join(cmd)}")
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip())
        return proc.returncode
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    print(f"[PASS] {name}")
    return 0


def main() -> int:
    for name, cmd in CHECKS:
        code = _run(name, cmd)
        if code != 0:
            return code
    print("[PASS] manual approval regression gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

