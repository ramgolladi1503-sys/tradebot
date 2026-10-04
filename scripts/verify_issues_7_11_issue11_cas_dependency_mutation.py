#!/usr/bin/env python3
"""Verify the Issue 11 stale-spot scenario kills removal of the CAS gate."""
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
    source_path = repo / "core" / "runtime_snapshot_producer.py"
    test_path = repo / "tests" / "core" / "test_runtime_snapshot_producer.py"
    source = source_path.read_text(encoding="utf-8")
    test_digest = _sha256(test_path)
    source_digest = _sha256(source_path)
    anchor = """                cas_gate_reason = _cas_spot_dependency_block_reason(
                    market_payload,
                    expected_token=token,
                    now_epoch=time.time(),
                )"""
    if source.count(anchor) != 1:
        print("ERROR: expected exactly one required-spot gate anchor", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="issues711_issue11_cas_gate_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests = root / "tests" / "core"
        core.mkdir()
        tests.mkdir(parents=True)
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "runtime_snapshot_producer.py").write_text(
            source.replace(anchor, "                cas_gate_reason = None", 1), encoding="utf-8"
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + old_pythonpath if old_pythonpath else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        test_name = "test_scenario_d_unhealthy_or_unbound_nifty_blocks_cas_evaluator"
        node_id = f"{copied_test}::{test_name}[spot0-None-cas_required_spot_unhealthy]"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node_id], cwd=root, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: Issue 11 dependency mutant timed out", file=sys.stderr)
            return 2
        if result.returncode == 0:
            print("SURVIVED: remove_required_nifty_spot_gate", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if test_name not in result.stdout or "1 failed" not in result.stdout:
            print("INVALID MUTATION RESULT: expected scenario assertion failure", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: remove_required_nifty_spot_gate")

    if _sha256(source_path) != source_digest or _sha256(test_path) != test_digest:
        print("ERROR: checkout hashes changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: Issue 11 gate mutant killed; checkout hashes unchanged")
    print(f"source_sha256={source_digest}")
    print(f"test_sha256={test_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
