from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/module_robustness_ranking_audit_v1/vertical_slice_certification_v1"


def test_vertical_slice_campaign_generates_deterministic_oracle_artifacts():
    result = subprocess.run(
        [sys.executable, "scripts/run_vertical_slice_certification_v1.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    oracle = json.loads((OUT / "independent_oracle_report.json").read_text())
    assert oracle["principal_verdict"] == "VERTICAL_SLICE_NOT_CERTIFIED"
    assert oracle["checks"]["deterministic_rerun_equivalence"] is True
    assert oracle["checks"]["identity_chain_complete"] is True
    assert oracle["passed"] is True

    comparison = json.loads((OUT / "determinism_comparison.json").read_text())
    assert comparison["match"] is True
    assert comparison["allowed_differences"] == []

    rows = list(csv.DictReader((OUT / "scenario_matrix.csv").open()))
    assert len(rows) == 33
    assert {row["fixture_id"] for row in rows} >= {
        "valid_ce_buy",
        "valid_pe_buy",
        "empty_ranked_snapshot_ui_fallback",
        "duplicate_broker_request_idempotency",
        "restart_recovery_final_reconciliation",
    }

    fallback = next(row for row in rows if row["fixture_id"] == "empty_ranked_snapshot_ui_fallback")
    assert fallback["actual_outcome"] == "approval_blocked_or_advisory"
    assert fallback["certified"] == "False"

    broker_rows = list(csv.DictReader((OUT / "broker_mock_results.csv").open()))
    retry = next(row for row in broker_rows if row["fixture_id"] == "retry_after_timeout")
    timeout = next(row for row in broker_rows if row["fixture_id"] == "broker_timeout_before_ack")
    assert retry["status"] == "timeout_unresolved"
    assert timeout["status"] == "timeout_unresolved"

    sha_check = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=OUT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert sha_check.returncode == 0, sha_check.stderr
