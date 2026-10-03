#!/usr/bin/env python3
"""Verify the Issue 10 multiprocess writer regression detects a missing lock."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "locked_jsonl.py"
    test_path = repo / "tests" / "test_kite_read_only_observation_runtime.py"
    source = source_path.read_text(encoding="utf-8")
    source_digest = _sha256(source_path)
    test_digest = _sha256(test_path)
    anchor = "fcntl.flock(fd, fcntl.LOCK_EX)"
    if source.count(anchor) != 1:
        print("ERROR: expected exactly one exclusive-lock mutation anchor", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="issues711_issue10_writer_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests = root / "tests"
        core.mkdir()
        tests.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "locked_jsonl.py").write_text(
            source.replace(anchor, "pass  # isolated mutant: exclusive lock removed", 1),
            encoding="utf-8",
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())

        env = os.environ.copy()
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + old_pythonpath if old_pythonpath else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        node_id = f"{copied_test}::test_candidate_decision_batches_are_serialized_across_processes"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node_id],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: multiprocess writer mutation test timed out", file=sys.stderr)
            return 2

        if result.returncode == 0:
            print("SURVIVED: remove_exclusive_candidate_log_lock", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if "test_candidate_decision_batches_are_serialized_across_processes" not in result.stdout or "1 failed" not in result.stdout:
            print("INVALID MUTATION RESULT", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: remove_exclusive_candidate_log_lock")

    if _sha256(source_path) != source_digest or _sha256(test_path) != test_digest:
        print("ERROR: checkout source/test changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: writer-lock mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_digest}")
    print(f"test_sha256={test_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
