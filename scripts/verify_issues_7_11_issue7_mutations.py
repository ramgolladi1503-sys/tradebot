#!/usr/bin/env python3
"""Kill targeted Issue 7 T-1 assembler mutants in isolated temporary copies.

The checkout's production module and test file are copied to a temporary package;
only that copy is mutated. The script never reads market data or starts runtime,
broker, or order paths.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


TEST_NAME = "test_t1_assembler_fails_closed_on_incomplete_or_mismatched_evidence"
MUTANTS = (
    (
        "accept_wrong_prior_trading_date",
        "source_session.get(\"trading_date\") != prior_day.isoformat()",
        "False",
        f"{TEST_NAME}[wrong_source_session-SOURCE_ANCESTOR_IDENTITY_MISMATCH]",
    ),
    (
        "accept_future_available_evidence",
        "float(available) > epoch",
        "False",
        f"{TEST_NAME}[future_evidence-T1_EVIDENCE_NOT_AVAILABLE_AT_DECISION]",
    ),
    (
        "accept_missing_required_field",
        "if set(observed) != set(expected):",
        "if False:",
        f"{TEST_NAME}[missing-MISSING_T1_PREREQUISITE_FIELD]",
    ),
    (
        "infer_monday_predecessor_by_calendar_day",
        "prior = max(dates)",
        "prior = date.fromordinal(target_date.toordinal() - 1)",
        "test_previous_eligible_session_skips_weekends_and_exchange_holidays[monday_after_weekend]",
    ),
    (
        "infer_post_holiday_predecessor_by_calendar_day",
        "prior = max(dates)",
        "prior = date.fromordinal(target_date.toordinal() - 1)",
        "test_previous_eligible_session_skips_weekends_and_exchange_holidays[wednesday_after_exchange_holiday]",
    ),
)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "market_heritage_graph.py"
    test_path = repo / "tests" / "test_market_heritage_graph.py"
    source = source_path.read_text(encoding="utf-8")
    source_digest = __import__("hashlib").sha256(source.encode("utf-8")).hexdigest()
    tests = test_path.read_text(encoding="utf-8")
    test_digest = __import__("hashlib").sha256(tests.encode("utf-8")).hexdigest()

    with TemporaryDirectory(prefix="issues711_issue7_mutation_") as directory:
        root = Path(directory)
        temp_core = root / "core"
        temp_tests = root / "tests"
        temp_core.mkdir()
        temp_tests.mkdir()
        (temp_core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (temp_tests / "test_market_heritage_graph.py").write_text(
            tests, encoding="utf-8"
        )
        mutant_module = temp_core / "market_heritage_graph.py"
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        copied_test = temp_tests / "test_market_heritage_graph.py"

        for name, original, replacement, case_id in MUTANTS:
            count = source.count(original)
            if count != 1:
                print(
                    f"ERROR: expected one mutation anchor for {name}, found {count}",
                    file=sys.stderr,
                )
                return 2
            mutant_module.write_text(source.replace(original, replacement, 1), encoding="utf-8")
            node_id = f"{copied_test}::{case_id}"
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
                print(f"ERROR: timed out running mutant {name}", file=sys.stderr)
                return 2
            if result.returncode == 0:
                print(f"SURVIVED: {name}", file=sys.stderr)
                print(result.stdout[-3000:], file=sys.stderr)
                return 1
            selected_test = case_id.split("[", 1)[0]
            if selected_test not in result.stdout or "1 failed" not in result.stdout:
                print(f"INVALID MUTATION RESULT: {name}", file=sys.stderr)
                print(result.stdout[-3000:], file=sys.stderr)
                return 2
            print(f"KILLED: {name}")

    final_digest = __import__("hashlib").sha256(
        source_path.read_bytes()
    ).hexdigest()
    final_test_digest = __import__("hashlib").sha256(test_path.read_bytes()).hexdigest()
    if final_digest != source_digest or final_test_digest != test_digest:
        print("ERROR: repository source or test changed during isolated mutation run", file=sys.stderr)
        return 2
    print(f"PASS: {len(MUTANTS)}/{len(MUTANTS)} Issue 7 calendar/assembler mutants killed; checkout hashes unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
