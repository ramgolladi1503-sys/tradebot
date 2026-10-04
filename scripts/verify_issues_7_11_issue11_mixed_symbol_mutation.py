#!/usr/bin/env python3
"""Prove mixed-symbol ranking regression detects over-broad feed scope."""
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
    source_path = repo / "core" / "ranking_orchestrator.py"
    test_path = repo / "tests" / "test_ranking_orchestrator.py"
    source = source_path.read_text(encoding="utf-8")
    source_sha, test_sha = _sha256(source_path), _sha256(test_path)
    start = source.find("def _homogeneous_scoring_symbol(")
    end = source.find("\ndef _pipeline_stage_order(", start)
    if start < 0 or end < 0:
        print("ERROR: homogeneous-symbol helper anchor missing", file=sys.stderr)
        return 2
    mutant_helper = '''def _homogeneous_scoring_symbol(scoring, pool_symbol):
    # Sabotage mutant: trust pool symbol without checking score identities.
    expected = str(pool_symbol or "").strip().upper()
    return expected or None
'''
    with TemporaryDirectory(prefix="issues711_issue11_mixed_symbol_mutation_") as temp_dir:
        root = Path(temp_dir)
        core, tests = root / "core", root / "tests"
        core.mkdir()
        tests.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "ranking_orchestrator.py").write_text(
            source[:start] + mutant_helper + source[end:], encoding="utf-8"
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + old_pythonpath if old_pythonpath else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        node_id = f"{copied_test}::test_mixed_symbol_candidate_pool_cannot_use_context_symbol_health_scope"
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
            print("ERROR: mixed-symbol mutant timed out", file=sys.stderr)
            return 2
        if result.returncode == 0:
            print("SURVIVED: trust_pool_symbol_without_score_identity_check", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        expected_assertion = "assert report.ranked_candidate_count == 0"
        if (
            "1 failed" not in result.stdout
            or expected_assertion not in result.stdout
            or "AssertionError" not in result.stdout
        ):
            print("INVALID MUTATION RESULT: expected one assertion failure", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: trust_pool_symbol_without_score_identity_check")
    if _sha256(source_path) != source_sha or _sha256(test_path) != test_sha:
        print("ERROR: checkout changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: mixed-symbol mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_sha}")
    print(f"test_sha256={test_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
