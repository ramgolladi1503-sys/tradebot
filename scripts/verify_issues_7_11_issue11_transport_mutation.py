#!/usr/bin/env python3
"""Prove contradictory effective/legacy transport evidence kills the old OR gate."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "runtime_snapshot_producer.py"
    test_path = repo / "tests" / "core" / "test_issue11_cas_dependency_adversarial.py"
    source = source_path.read_text(encoding="utf-8")
    old = '''    if not isinstance(cas_feed_payload, dict):
        cas_feed_healthy = False
    elif "effective_ws_connected" in cas_feed_payload:
        # The validated effective field is authoritative when present. A
        # contradictory legacy field must never resurrect unhealthy transport.
        cas_feed_healthy = cas_feed_payload.get("effective_ws_connected") is True
    else:
        # Compatibility for older validated artifacts that predate the field.
        cas_feed_healthy = cas_feed_payload.get("ws_connected") is True'''
    mutant = '''    cas_feed_healthy = isinstance(cas_feed_payload, dict) and (
        cas_feed_payload.get("effective_ws_connected") is True
        or cas_feed_payload.get("ws_connected") is True
    )'''
    if source.count(old) != 1:
        print("ERROR: expected exactly one authoritative transport gate", file=sys.stderr)
        return 2
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    test_hash = hashlib.sha256(test_path.read_bytes()).hexdigest()
    with TemporaryDirectory(prefix="issues711_issue11_transport_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests = root / "tests" / "core"
        core.mkdir()
        tests.mkdir(parents=True)
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "runtime_snapshot_producer.py").write_text(
            source.replace(old, mutant, 1), encoding="utf-8"
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        node_id = f"{copied_test}::test_cas_bridge_fails_closed_for_adversarial_dependency_evidence[spot15-cas_shared_feed_unhealthy_or_unknown]"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node_id], cwd=root, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: transport mutant timed out", file=sys.stderr)
            return 2
        if result.returncode == 0:
            print("SURVIVED: restore_or_transport_gate", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if "1 failed" not in result.stdout or "cas_shared_feed_unhealthy_or_unknown" not in result.stdout:
            print("INVALID MUTATION RESULT: expected one assertion failure", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: restore_or_transport_gate")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_hash or hashlib.sha256(test_path.read_bytes()).hexdigest() != test_hash:
        print("ERROR: checkout changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: transport mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_hash}")
    print(f"test_sha256={test_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
