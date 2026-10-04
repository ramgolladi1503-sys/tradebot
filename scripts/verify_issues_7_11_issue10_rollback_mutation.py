#!/usr/bin/env python3
"""Verify Issue 10 foreign-append rollback guard with an isolated mutant."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "locked_jsonl.py"
    test_path = repo / "tests" / "test_kite_read_only_observation_runtime.py"
    source = source_path.read_text(encoding="utf-8")
    source_digest = sha256(source_path)
    test_digest = sha256(test_path)
    anchor = 'logger.error(\n                "JSONL append failed; in-place rollback skipped'
    mutant = 'os.ftruncate(fd, 0)  # mutant: destructive rollback despite bypass writer\n            logger.error(\n                "JSONL append failed; in-place rollback skipped'
    if source.count(anchor) != 1:
        print("ERROR: expected exactly one no-truncate mutation anchor", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="issues711_issue10_rollback_mutation_") as tmp:
        root = Path(tmp)
        core = root / "core"
        tests = root / "tests"
        core.mkdir()
        tests.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "locked_jsonl.py").write_text(
            source.replace(anchor, mutant, 1), encoding="utf-8"
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        prior = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + prior if prior else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        test_name = "test_failed_batch_preserves_interleaved_noncooperating_append"
        node = f"{copied_test}::{test_name}"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node], cwd=root, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: rollback mutant test timed out", file=sys.stderr)
            return 2
        if result.returncode == 0:
            print("SURVIVED: destructive_external_append_rollback", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if test_name not in result.stdout or "1 failed" not in result.stdout:
            print("INVALID MUTATION RESULT", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: destructive_external_append_rollback")

    if sha256(source_path) != source_digest or sha256(test_path) != test_digest:
        print("ERROR: checkout source/test changed during mutation", file=sys.stderr)
        return 2
    print("PASS: destructive rollback mutant killed; checkout hashes unchanged")
    print(f"source_sha256={source_digest}")
    print(f"test_sha256={test_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
