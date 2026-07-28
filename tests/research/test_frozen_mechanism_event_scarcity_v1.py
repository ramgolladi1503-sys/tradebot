from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/frozen_mechanism_event_scarcity_audit_v1")


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_final_verdict_and_safety_flags() -> None:
    final = read_json("final_verdict.json")
    assert final["final_verdict"] == "ADDITIONAL_MICROSTRUCTURE_DATA_REQUIRED"
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False


def test_event_funnel_shows_zero_final_events() -> None:
    funnels = read_json("event_funnel_report.json")
    for rows in funnels.values():
        holdout_final = [row for row in rows if row["split"] == "holdout" and row["stage"] == "final_event"][0]
        assert holdout_final["rows_after"] == 0


def test_support_report_identifies_missing_underlying_state() -> None:
    support = read_json("development_vs_holdout_support_report.json")
    ret_rows = [row for row in support["distribution_shift"] if row["feature"] == "ret_1"]
    assert ret_rows
    assert all(row["nonnull_rows"] == 0 for row in ret_rows)


def test_feasibility_classification_is_data_support_insufficient() -> None:
    feasibility = read_json("per_mechanism_feasibility_classification.json")
    assert feasibility["delayed_option_convexity_after_underlying_confirmation"] == "DATA_SUPPORT_INSUFFICIENT"
    assert feasibility["premium_compression_release_with_underlying_state_filter"] == "DATA_SUPPORT_INSUFFICIENT"


def test_audit_and_determinism_pass() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    assert audit["status"] == "PASS"
    assert audit["checks"]["no_production_modifications"] is True
    assert determinism["status"] == "PASS"
