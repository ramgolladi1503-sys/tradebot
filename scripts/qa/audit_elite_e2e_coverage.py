#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REQUIRED_EXECUTION_GUARD_TESTS = (
    Path("tests/test_execution_guard.py"),
    Path("tests/behavior/execution/test_execution_guard_no_room_for_error.py"),
    Path("tests/regression/test_execution_guard_truth_no_regression.py"),
)


def _execution_guard_status(repo_root: Path) -> tuple[str, list[str]]:
    missing = [str(path) for path in REQUIRED_EXECUTION_GUARD_TESTS if not (repo_root / path).exists()]
    if missing:
        return "PARTIALLY_COVERED", missing
    return "FULLY_COVERED", []


def build_report(*, repo_root: Path) -> dict[str, object]:
    execution_guard_status, missing = _execution_guard_status(repo_root)
    score = 100
    hard_caps: list[str] = []
    if execution_guard_status != "FULLY_COVERED":
        score = min(score, 94)
        hard_caps.append("execution_guard_partial_caps_below_95")
    return {
        "execution_guard_status": execution_guard_status,
        "execution_guard_required_tests_missing": missing,
        "critical_behavior_coverage_score": score,
        "elite_audit_score": score,
        "hard_caps_applied": hard_caps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit elite QA coverage with hard caps for critical gaps.")
    parser.add_argument("--threshold", type=int, default=95)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(repo_root=Path.cwd())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"execution_guard_status: {report['execution_guard_status']}")
        print(f"critical_behavior_coverage_score: {report['critical_behavior_coverage_score']}/100")
        print(f"elite_audit_score: {report['elite_audit_score']}/100")
        if report["execution_guard_required_tests_missing"]:
            print("execution_guard_required_tests_missing:")
            for path in report["execution_guard_required_tests_missing"]:
                print(f"- {path}")
        if report["hard_caps_applied"]:
            print("hard_caps_applied:")
            for cap in report["hard_caps_applied"]:
                print(f"- {cap}")

    return 0 if int(report["elite_audit_score"]) >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
