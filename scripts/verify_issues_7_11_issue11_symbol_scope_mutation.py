#!/usr/bin/env python3
"""Prove fail-closed tests detect forced healthy symbol-scope mutation."""
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
    source_path = repo / "core" / "feed_hold_gate.py"
    test_path = repo / "tests" / "test_pr_feed_03_feed_hold_gate.py"
    source = source_path.read_text(encoding="utf-8")
    source_sha = _sha256(source_path)
    test_sha = _sha256(test_path)
    start = source.find("def _scope_certified_symbol_truth(")
    end = source.find("\ndef _coerce_feed_health(", start)
    if start < 0 or end < 0:
        print("ERROR: symbol-scope helper anchor missing", file=sys.stderr)
        return 2
    mutant_helper = '''def _scope_certified_symbol_truth(feed_health, symbol):
    # Sabotage mutant: pretend every requested symbol is healthy, regardless
    # of shared transport, global latches, missing identity, or local health.
    if not symbol:
        return None
    return FeedHealthTruthDecision(
        feed_ok=True,
        reason_code="ok",
        reasons=(),
        global_feed_ok=True,
        websocket_ok=True,
        symbols=(),
        context={"ranking_scope": "mutant_forced_healthy"},
        domains={},
        overall_state="HEALTHY",
    )
'''
    with TemporaryDirectory(prefix="issues711_issue11_symbol_scope_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests = root / "tests"
        core.mkdir()
        tests.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "feed_hold_gate.py").write_text(
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
        node_id = f"{copied_test}::test_symbol_isolation_fails_closed_for_shared_or_unknown_health"
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
            print("ERROR: symbol-scope mutant timed out", file=sys.stderr)
            return 2
        if result.returncode == 0:
            print("SURVIVED: force_all_symbol_scopes_healthy", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if "1 failed" not in result.stdout:
            print("INVALID MUTATION RESULT: expected one assertion failure", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: force_all_symbol_scopes_healthy")
    if _sha256(source_path) != source_sha or _sha256(test_path) != test_sha:
        print("ERROR: checkout changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: forced-healthy mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_sha}")
    print(f"test_sha256={test_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
