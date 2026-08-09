#!/usr/bin/env python3
"""Run the source-complete behavioral regression gate for registered strategies.

This gate is intentionally narrower than the full repository suite. It targets the
strategy implementations and support/meta layers changed by the structural repair
campaign. It writes a machine-readable artifact bound to the exact Git HEAD.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TEST_FILES = (
    "tests/research/test_registered_strategy_structure_audit.py",
    "tests/strategies/test_production_strategy_gates.py",
    "tests/test_exhaustion_mean_reversion_strategies.py",
    "tests/test_compression_trend_movement_strategies.py",
    "tests/test_vwap_trap_movement_strategies.py",
    "tests/strategies/test_ensemble_wiring.py",
    "tests/strategies/test_pro_strategy_engine_elite.py",
    "tests/strategy_truth/test_pro_engine_strategies.py",
)

REQUIRED_SOURCE_PATHS = ("core", "strategies", "config", "tests")


def git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def run(root: Path, output: Path) -> dict:
    missing = [p for p in TEST_FILES if not (root / p).exists()]
    source_missing = [p for p in REQUIRED_SOURCE_PATHS if not (root / p).exists()]
    head = git_head(root)
    result = {
        "schema_version": "tradebot-registered-strategy-behavioral-gate-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": head,
        "test_files": list(TEST_FILES),
        "required_source_paths": list(REQUIRED_SOURCE_PATHS),
        "missing_test_files": missing,
        "missing_source_paths": source_missing,
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "profitability_evaluated": False,
    }
    if missing or source_missing:
        result.update({
            "status": "SOURCE_NOT_MATERIALIZED",
            "pytest_exit_code": None,
            "next_action": "MATERIALIZE_CORE_STRATEGIES_CONFIG_AND_TESTS_IN_EXISTING_SPARSE_WORKTREE",
        })
    else:
        cmd = [sys.executable, "-m", "pytest", "-q", *TEST_FILES]
        proc = subprocess.run(cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        result.update({
            "status": "BEHAVIORAL_GATE_PASS" if proc.returncode == 0 else "BEHAVIORAL_GATE_FAIL",
            "pytest_exit_code": proc.returncode,
            "pytest_output": proc.stdout,
            "next_action": "STRUCTURAL_CLOSURE_ELIGIBLE" if proc.returncode == 0 else "REPAIR_BEHAVIORAL_FAILURES",
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="research/hypotheses/strategy_structural_audit/registered_strategy_behavioral_gate.json")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    result = run(root, root / args.output)
    print(json.dumps({
        "status": result["status"],
        "source_commit": result["source_commit"],
        "pytest_exit_code": result.get("pytest_exit_code"),
        "missing_test_files": result.get("missing_test_files", []),
        "missing_source_paths": result.get("missing_source_paths", []),
        "output": str(root / args.output),
        "runtime_authority": "NONE",
    }, indent=2, sort_keys=True))
    return 0 if result["status"] == "BEHAVIORAL_GATE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
