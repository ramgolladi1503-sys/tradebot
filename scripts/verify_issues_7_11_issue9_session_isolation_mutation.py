#!/usr/bin/env python3
"""Prove the Issue 9 rollover regression detects cross-session bar leakage."""
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
    source_path = repo / "core" / "market_session_memory_contract.py"
    test_path = repo / "tests" / "core" / "test_market_session_runtime_bridge.py"
    source = source_path.read_text(encoding="utf-8")
    source_sha, test_sha = _sha256(source_path), _sha256(test_path)
    anchor = "            local = [dict(row) for row in local if _is_same_ist_session_date(row, as_of)]"
    mutant = "            local = [dict(row) for row in local]  # mutant: leak prior-date local bars"
    if source.count(anchor) != 1:
        print("ERROR: expected one local Issue 9 session-date filter", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="issues711_issue9_session_isolation_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests = root / "tests" / "core"
        core.mkdir()
        tests.mkdir(parents=True)
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "market_session_memory_contract.py").write_text(
            source.replace(anchor, mutant, 1), encoding="utf-8"
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        previous = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + previous if previous else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        test_name = "test_same_process_session_rollover_excludes_prior_date_bars_from_runtime_view"
        node = f"{copied_test}::{test_name}"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: session-isolation mutant timed out", file=sys.stderr)
            return 2
        expected = 'assert [bar["ts"] for bar in completed] == [current_open]'
        if result.returncode == 0:
            print("SURVIVED: prior_session_local_bars_accepted", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if (
            test_name not in result.stdout
            or "1 failed" not in result.stdout
            or expected not in result.stdout
            or "AssertionError" not in result.stdout
        ):
            print("INVALID MUTATION RESULT: expected date-set assertion failure", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: prior_session_local_bars_accepted")

    if _sha256(source_path) != source_sha or _sha256(test_path) != test_sha:
        print("ERROR: checkout source/test hashes changed during mutation", file=sys.stderr)
        return 2
    print("PASS: Issue 9 rollover mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_sha}")
    print(f"test_sha256={test_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
