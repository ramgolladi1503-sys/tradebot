#!/usr/bin/env python3
"""Kill a miswired verified T-1 value at the shadow-adapter boundary."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "paper_shadow" / "strategy_shadow_adapter.py"
    test_path = repo / "tests" / "test_market_heritage_graph.py"
    source = source_path.read_text(encoding="utf-8")
    source_sha, test_sha = digest(source_path), digest(test_path)
    anchor = "self.target_expiry = target_expiry"
    if source.count(anchor) != 1:
        print("ERROR: expected exactly one adapter input assignment", file=sys.stderr)
        return 2
    mutant = source.replace(anchor, "self.target_expiry = None", 1)
    with TemporaryDirectory(prefix="issues711_issue7_adapter_mutation_") as directory:
        root = Path(directory)
        core = root / "core"
        shadow = core / "paper_shadow"
        tests = root / "tests"
        shadow.mkdir(parents=True)
        tests.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (shadow / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core' / 'paper_shadow')!r})\n", encoding="utf-8"
        )
        (shadow / source_path.name).write_text(mutant, encoding="utf-8")
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + old_pythonpath if old_pythonpath else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        node_id = f"{copied_test}::test_scenario_a_verified_t1_clean_boot_reaches_shadow_evaluators"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node_id],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: adapter-input mutant timed out", file=sys.stderr)
            return 2
        if result.returncode == 0:
            print("SURVIVED: opening_drive_target_expiry_miswired", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        expected_assertion = "assert opening_drive_adapter.target_expiry == target_expiry_from_launch_plan"
        if (
            "test_scenario_a_verified_t1_clean_boot_reaches_shadow_evaluators" not in result.stdout
            or "1 failed" not in result.stdout
            or expected_assertion not in result.stdout
            or "AssertionError" not in result.stdout
        ):
            print("INVALID MUTATION RESULT", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: opening_drive_target_expiry_miswired_at_expected_assertion")
    if digest(source_path) != source_sha or digest(test_path) != test_sha:
        print("ERROR: checkout source/test hashes changed", file=sys.stderr)
        return 2
    print("PASS: adapter-input mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_sha}")
    print(f"test_sha256={test_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
