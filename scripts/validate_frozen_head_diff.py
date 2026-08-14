from __future__ import annotations

import argparse
import re
import subprocess
import sys


def classify_diff_check(output: str) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    blocking: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path, _, message = line.partition(":")
        evidence_markdown = (
            path.startswith("docs/")
            or bool(re.match(r"PR\d+_.*(EVIDENCE|AUTHORITY|CERTIFICATION).*\.md$", path))
        )
        if evidence_markdown and "new blank line at EOF" in message:
            allowed.append(line)
        else:
            blocking.append(line)
    return allowed, blocking


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("candidate")
    args = parser.parse_args()
    proc = subprocess.run(
        ["git", "diff", "--check", args.base, args.candidate],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    allowed, blocking = classify_diff_check(proc.stdout)
    for line in allowed:
        print(f"NON_RUNTIME_EVIDENCE_FORMATTING={line}")
    for line in blocking:
        print(f"BLOCKING_DIFF_CHECK={line}", file=sys.stderr)
    if blocking:
        return 1
    print("FROZEN_HEAD_DIFF_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
