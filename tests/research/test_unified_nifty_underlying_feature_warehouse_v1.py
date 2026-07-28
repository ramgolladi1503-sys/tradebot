from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ARTIFACT_ROOT = Path("research/unified_nifty_underlying_feature_warehouse_v1")


def read_json(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text())


def test_underlying_final_verdict_is_partial_with_real_joint_rows() -> None:
    final = read_json("final_verdict.json")
    assert final["primary_verdict"] == "UNDERLYING_WAREHOUSE_PARTIALLY_READY"
    assert final["joint_rows"] > 0
    assert final["joint_sessions"] > 0
    assert "incomplete_one_minute_sessions" in final["blockers"]
    assert final["read_only"] is True
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False


def test_coverage_audit_records_incomplete_sessions() -> None:
    coverage = read_json("coverage_integrity_report.json")
    ledger = pd.read_csv(ARTIFACT_ROOT / "daily_coverage_ledger.csv")
    assert coverage["session_count"] == 445
    assert coverage["complete_sessions"] == 434
    assert coverage["incomplete_sessions"] == 11
    assert int((ledger["status"] == "INCOMPLETE").sum()) == 11


def test_option_alignment_is_nonzero_and_causal_5m() -> None:
    alignment = read_json("option_alignment_report.json")
    assert alignment["joint_rows"] == 392832
    assert alignment["joint_sessions"] == 386
    assert alignment["matched_option_5m_rows"] > 0
    assert alignment["timestamp_overlap"] is True


def test_local_parquet_payloads_are_not_required_for_report_integrity() -> None:
    manifest = read_json("artifact_manifest.json")
    committed_names = {entry["path"] for entry in manifest["artifacts"]}
    assert "final_verdict.json" in committed_names
    assert all(not name.endswith(".parquet") for name in committed_names)
