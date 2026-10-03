#!/usr/bin/env python3
"""Kill the Issue 11 canonical loader-origin guard in an isolated copy."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


TEST_NAME = "test_canonical_loader_origin_blocks_marker_stripping_and_legacy_feed_ok"
MUTATION_ANCHOR = (
    "        payload[FEED_TRUTH_LOADER_ORIGIN_KEY] = "
    "FEED_TRUTH_CANONICAL_LOADER_ORIGIN\n"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "orchestrator.py"
    test_path = repo / "tests" / "test_feed_truth_snapshot_ranking_contract.py"
    source = source_path.read_text(encoding="utf-8")
    tests = test_path.read_text(encoding="utf-8")
    source_digest = _sha256(source_path)
    test_digest = _sha256(test_path)

    if source.count(MUTATION_ANCHOR) != 1:
        print("ERROR: expected exactly one loader-origin mutation anchor", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="issues711_issue11_origin_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests_root = root / "tests"
        core.mkdir()
        tests_root.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n",
            encoding="utf-8",
        )
        (core / "orchestrator.py").write_text(
            source.replace(MUTATION_ANCHOR, "", 1),
            encoding="utf-8",
        )
        copied_test = tests_root / "test_feed_truth_snapshot_ranking_contract.py"
        copied_test.write_text(tests, encoding="utf-8")

        env = os.environ.copy()
        previous_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + previous_pythonpath if previous_pythonpath else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        node_id = f"{copied_test}::{TEST_NAME}"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node_id],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: loader-origin mutant timed out", file=sys.stderr)
            return 2

        if result.returncode == 0:
            print("SURVIVED: remove_canonical_loader_origin", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if TEST_NAME not in result.stdout or "1 failed" not in result.stdout:
            print("INVALID MUTATION RESULT: regression did not fail by assertion", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: remove_canonical_loader_origin")

    if _sha256(source_path) != source_digest or _sha256(test_path) != test_digest:
        print("ERROR: checkout source/test changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: loader-origin mutant killed; checkout hashes unchanged")
    print(f"orchestrator_sha256={source_digest}")
    print(f"test_sha256={test_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
