#!/usr/bin/env python3
"""Run the offline pre-market certification gates without broker access."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from core.offline_certification_session import (
    OfflineSessionEvidence,
    independently_verify_session_manifest,
    write_final_session_manifest,
)


RELEVANT_TESTS = [
    "tests/test_daily_instrument_authority.py",
    "tests/test_instruments_registry.py",
    "tests/test_kite_autologin_credential_provenance.py",
    "tests/test_read_only_consumer_cycle.py",
    "tests/test_cas_v2_consumer_contract.py",
    "tests/test_cas_morning_reversal_advisory.py",
    "tests/test_cas_runtime.py",
    "tests/test_lifecycle_shutdown.py",
    "tests/test_lifecycle_shutdown_manager.py",
    "tests/test_feed_runtime_states.py",
    "tests/test_kite_read_only_observation_runtime.py",
    "tests/test_sqlite_snapshot_parquet_exporter.py",
    "tests/test_offline_certification_session.py",
]


def _run_tests(root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *RELEVANT_TESTS],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-12000:]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--soak-minutes", type=float, default=0.0)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    actual_sha = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain")
    exact = actual_sha == args.expected_sha
    clean = not status
    tests_ok, test_output = _run_tests(root) if exact and clean else (False, "tests_not_run_due_to_authority_failure")
    soak_pass = False
    soak_note = "not_run"
    if args.soak_minutes > 0:
        # The full production-equivalence soak must be implemented as a real fixture campaign;
        # this runner refuses to convert elapsed wall time into a PASS.
        soak_note = "BLOCKED_REQUIRES_PRODUCTION_EQUIVALENCE_CAMPAIGN"

    session_id = f"offline-cert-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    manifest = output / "SESSION_MANIFEST.json"
    write_final_session_manifest(
        manifest,
        OfflineSessionEvidence(
            session_id=session_id,
            session_date=datetime.now().astimezone().date().isoformat(),
            release_sha=actual_sha,
            worktree_root=str(root),
            runtime_root=str(output),
            start_utc=datetime.fromtimestamp(started, timezone.utc).isoformat(),
            stop_utc=datetime.now(timezone.utc).isoformat(),
            metrics={
                "exact_sha_binding_pass": exact,
                "clean_worktree_pass": clean,
                "relevant_tests_pass": tests_ok,
                "soak_duration_minutes": args.soak_minutes if args.soak_minutes > 0 else "UNKNOWN",
                "soak_test_pass": soak_pass,
                "broker_calls": 0,
                "order_calls": 0,
            },
        ),
    )
    verified = independently_verify_session_manifest(manifest)
    report = {
        "OFFLINE_PRODUCTION_EQUIVALENCE_PASS": bool(exact and clean and tests_ok and soak_pass),
        "EXACT_SHA_BINDING_PASS": exact,
        "CLEAN_WORKTREE_PASS": clean,
        "RELEVANT_OFFLINE_TESTS_PASS": tests_ok,
        "SOAK_TEST_PASS": soak_pass,
        "SOAK_NOTE": soak_note,
        "PARQUET_EXPORT_READS_LIVE_SQLITE": False,
        "KITE_CALLS": 0,
        "BROKER_WRITE_CALLS": 0,
        "BROKER_ORDER_CALLS": 0,
        "ORDERS_PLACED": 0,
        "ORDERS_MODIFIED": 0,
        "ORDERS_CANCELLED": 0,
        "CURRENT_SHA": actual_sha,
        "EXPECTED_SHA": args.expected_sha,
        "SESSION_MANIFEST": str(manifest),
        "SESSION_MANIFEST_VERIFIED": bool(verified.get("ok")),
        "TEST_OUTPUT": test_output,
    }
    report_path = output / "offline_production_equivalence_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["OFFLINE_PRODUCTION_EQUIVALENCE_PASS"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
