#!/usr/bin/env python3
"""Kill targeted Issue 9 completed-bar source mutants in temporary copies."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


MUTANTS = (
    (
        "commit_completed_bar_before_context_exit",
        'row["open"], row["high"], row["low"], row["close"], row["volume"],\n                    _json(row["provenance"]), row["row_hash"], float(now_utc_epoch())))',
        'row["open"], row["high"], row["low"], row["close"], row["volume"],\n                    _json(row["provenance"]), row["row_hash"], float(now_utc_epoch())))\n                conn.commit()',
        "test_process_death_before_store_context_commit_rolls_back_insert",
    ),
    (
        "remove_event_time_completion_cutoff",
        "if ts + timedelta(minutes=1) > cutoff:",
        "if False:",
        "test_store_rejects_bar_before_event_time_completion",
    ),
    (
        "remove_immutable_duplicate_hash_guard",
        'if str(old[\"row_hash\"]) != row[\"row_hash\"]:',
        "if False:",
        "test_session_store_rejects_mutation_of_completed_bar",
    ),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "market_session_store.py"
    test_path = repo / "tests" / "core" / "test_market_session_store.py"
    source = source_path.read_text(encoding="utf-8")
    tests = test_path.read_text(encoding="utf-8")
    source_digest = _sha256(source_path)
    test_digest = _sha256(test_path)

    with TemporaryDirectory(prefix="issues711_issue9_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        test_root = root / "tests" / "core"
        core.mkdir()
        test_root.mkdir(parents=True)
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        copied_source = core / "market_session_store.py"
        copied_test = test_root / "test_market_session_store.py"
        copied_test.write_text(tests, encoding="utf-8")

        env = os.environ.copy()
        prior_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + prior_path if prior_path else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        for name, original, replacement, test_name in MUTANTS:
            count = source.count(original)
            if count != 1:
                print(
                    f"ERROR: expected one mutation anchor for {name}, found {count}",
                    file=sys.stderr,
                )
                return 2
            copied_source.write_text(source.replace(original, replacement, 1), encoding="utf-8")
            node_id = f"{copied_test}::{test_name}"
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", node_id],
                    cwd=root,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=90,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                print(f"ERROR: timed out running mutant {name}", file=sys.stderr)
                return 2

            if result.returncode == 0:
                print(f"SURVIVED: {name}", file=sys.stderr)
                print(result.stdout[-3000:], file=sys.stderr)
                return 1
            if test_name not in result.stdout or "1 failed" not in result.stdout:
                print(f"INVALID MUTATION RESULT: {name}", file=sys.stderr)
                print(result.stdout[-3000:], file=sys.stderr)
                return 2
            print(f"KILLED: {name}")

    if _sha256(source_path) != source_digest or _sha256(test_path) != test_digest:
        print("ERROR: checkout source or test file changed during mutation run", file=sys.stderr)
        return 2
    print(f"PASS: {len(MUTANTS)}/{len(MUTANTS)} targeted Issue 9 mutants killed; checkout hashes unchanged")
    print(f"source_sha256={source_digest}")
    print(f"test_sha256={test_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
