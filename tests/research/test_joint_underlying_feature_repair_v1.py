from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/joint_warehouse_underlying_feature_repair_v1")


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_final_verdict_is_repaired_and_safe() -> None:
    final = read_json("final_verdict.json")
    assert final["final_verdict"] == "JOINT_UNDERLYING_FEATURES_REPAIRED"
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False


def test_source_populated_and_joint_ret_1_repaired() -> None:
    source = read_json("source_feature_population_report.json")
    schema = read_json("schema_null_rate_report.json")
    assert source["ret_1_non_null_count"] > 0
    assert schema["ret_1_non_null_count"] > 0
    assert schema["ret_1_eligible_non_null_count"] > 0


def test_lineage_records_disappearance_and_repair() -> None:
    rows = read_json("field_lineage_report.json")["fields"]
    ret = next(row for row in rows if row["field"] == "ret_1")
    assert ret["source_non_null_count"] > 0
    assert ret["current_joint_non_null_count"] == 0
    assert ret["final_non_null_count"] > 0


def test_event_feasibility_smoke_has_events_without_pnl() -> None:
    smoke = read_json("downstream_event_feasibility_smoke_report.json")
    assert set(smoke) == {
        "delayed_option_convexity_after_underlying_confirmation",
        "premium_compression_release_with_underlying_state_filter",
    }
    assert any(row["development_event_count"] + row["holdout_event_count"] > 0 for row in smoke.values())


def test_audit_and_determinism_pass() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    assert audit["status"] == "PASS"
    assert audit["checks"]["no_production_modifications"] is True
    assert determinism["status"] == "PASS"
