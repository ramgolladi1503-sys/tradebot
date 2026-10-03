#!/usr/bin/env python3
"""Verify both Issue 11 registry coverage guards with isolated mutants."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchor(lines: tuple[str, ...]) -> str:
    return "\n".join(lines) + "\n"


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "candidate_feed_dependencies.py"
    test_path = repo / "tests" / "test_candidate_feed_dependencies.py"
    source = source_path.read_text(encoding="utf-8")
    source_digest = _sha256(source_path)
    test_digest = _sha256(test_path)
    mutants = {
        "remove_registry_validator_coverage_check": (
            _anchor((
            "        if not _required_identity_domains_match(",
            "            entry.required_domains,",
            "            entry.required_identities,",
            "        ):",
            '            errors.append("REGISTRY_REQUIRED_DOMAIN_IDENTITY_COVERAGE_MISMATCH")',
            )),
            "registry_coverage_assertion",
        ),
        "remove_execution_eligibility_coverage_check": (
            _anchor((
            "            and _required_identity_domains_match(",
            "                self.required_domains,",
            "                self.required_identities,",
            "            )",
            )),
            "eligibility_coverage_assertion",
        ),
    }
    for label, (anchor, _expected_failure) in mutants.items():
        if source.count(anchor) != 1:
            print(f"ERROR: expected exactly one source anchor for {label}", file=sys.stderr)
            return 2

    test_name = "test_verified_candidate_missing_required_domain_identity_fails_closed"
    for label, (anchor, expected_failure) in mutants.items():
        with TemporaryDirectory(prefix="issues711_issue11_registry_identity_mutation_") as temp_dir:
            root = Path(temp_dir)
            core = root / "core"
            tests = root / "tests"
            core.mkdir()
            tests.mkdir()
            (core / "__init__.py").write_text(
                f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
            )
            (core / source_path.name).write_text(source.replace(anchor, "", 1), encoding="utf-8")
            copied_test = tests / test_path.name
            copied_test.write_bytes(test_path.read_bytes())
            env = os.environ.copy()
            old_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
                os.pathsep + old_pythonpath if old_pythonpath else ""
            )
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            node_id = f"{copied_test}::{test_name}"
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
                print(f"ERROR: {label} timed out", file=sys.stderr)
                return 2
            if result.returncode == 0:
                print(f"SURVIVED: {label}", file=sys.stderr)
                print(result.stdout[-3000:], file=sys.stderr)
                return 1
            if (
                test_name not in result.stdout
                or "1 failed" not in result.stdout
                or expected_failure not in result.stdout
            ):
                print(f"INVALID MUTATION RESULT: {label} missed {expected_failure}", file=sys.stderr)
                print(result.stdout[-3000:], file=sys.stderr)
                return 2
            print(f"KILLED: {label}")

    if _sha256(source_path) != source_digest or _sha256(test_path) != test_digest:
        print("ERROR: checkout source/test hashes changed during isolated mutation", file=sys.stderr)
        return 2
    print("PASS: both Issue 11 registry-coverage mutants killed; checkout hashes unchanged")
    print(f"source_sha256={source_digest}")
    print(f"test_sha256={test_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
