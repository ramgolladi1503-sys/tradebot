from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/refetch_four_nifty_sessions_final_certification_v1")
AUTHORIZED = ["2024-12-12", "2025-03-25", "2025-04-04", "2025-04-23"]


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_refetch_records_authorized_api_failure_without_patch() -> None:
    final = read_json("final_verdict.json")
    audit = read_json("independent_audit_report.json")
    assert final["final_verdict"] == "REPAIR_FAILED"
    assert final["authorized_dates"] == AUTHORIZED
    assert len(final["api_calls"]) == 4
    assert all(row["http_status"] == 200 for row in final["api_calls"])
    assert all(row["response_row_count"] == 374 for row in final["api_calls"])
    assert audit["api_call_count"] == 4
    assert audit["patch_rows_inserted"] == 0
    assert final["broker_api_called"] is True
    assert final["broker_api_scope"] == "historical_market_data_only"
    assert final["allowed_for_live_execution"] is False


def test_pre_refetch_defects_are_the_four_authorized_gaps() -> None:
    defects = read_json("pre_refetch_defect_manifest.json")
    missing = {row["session_date"]: row["verified_missing_timestamps"] for row in defects}
    assert missing == {
        "2024-12-12": ["09:42"],
        "2025-03-25": ["10:42"],
        "2025-04-04": ["11:57"],
        "2025-04-23": ["10:36"],
    }


def test_overlap_matches_but_required_bars_are_absent() -> None:
    comparison = read_json("overlap_comparison_report.json")
    assert comparison["status"] == "PASS"
    assert len(comparison["comparisons"]) == 4
    for row in comparison["comparisons"]:
        assert row["overlap_count"] == 374
        assert row["ohlc_mismatch_count"] == 0
        assert row["required_missing_timestamp_found"] is False
        assert row["patch_decision"] == "REQUIRED_BAR_ABSENT_IN_AUTHORIZED_RESPONSE"
