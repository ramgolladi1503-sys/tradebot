from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/premium_compression_historical_acquisition_v1")
MECHANISM = "premium_compression_release_with_underlying_state_filter"


def read_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_used_date_ledger_freezes_prior_universe() -> None:
    ledger = read_json("used_date_ledger.json")
    assert ledger["used_date_span"] == ["2024-09-26", "2026-07-21"]
    assert ledger["unused_preferred_expansion"]["before"] == "2024-09-26"
    assert ledger["unused_prospective_expansion"]["after"] == "2026-07-21"
    assert ledger["unused_prospective_expansion"]["insufficient_elapsed_time_for_15_month_target"] is True


def test_authorized_upstox_probe_is_recorded_without_kite() -> None:
    pre = read_json("pre_change_manifest.json")
    provider = read_json("provider_feasibility_report.json")
    raw = read_json("raw_evidence_manifest.json")
    assert pre["credential_presence"]["KITE_API_KEY"] is True
    assert provider["kite_excluded_by_user"] is True
    assert provider["provider_calls_made"] is True
    assert provider["provider_call_scope"] == "UPSTOX_ONLY_AUTHORIZED_RANGE_PROBE"
    assert provider["upstox_expired_options"]["earliest_obtainable_date"] == "2024-10-03"
    assert raw["provider_requests_executed"] is True
    assert raw["provider"] == "UPSTOX_ONLY"
    assert raw["conclusion"]["pre_2024_09_26_expired_option_contract_count"] == 0
    assert len(raw["artifacts"]) == 3


def test_local_recovery_inventory_is_metadata_only() -> None:
    inventory = read_json("local_recovery_inventory.json")
    assert inventory["candidate_count"] > 0
    assert inventory["trusted_non_overlapping_ready_count"] == 0
    assert "certification" in inventory["conclusion"].lower()
    assert inventory["items_sample_limit"] == 1000
    assert all(item["provenance"] == "METADATA_ONLY_NO_OUTCOME_TEST" for item in inventory["items_sample"][:50])


def test_no_certification_or_event_count_without_raw_evidence() -> None:
    normalized = read_json("normalized_warehouse_manifest.json")
    certification = read_json("certification_report.json")
    events = read_json("event_count_only_feasibility_report.json")
    assert normalized["warehouses_built"] is False
    assert certification["status"] == "NOT_RUN"
    assert events["event_count_only_detector_run"] is False


def test_audit_determinism_and_final_verdict() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    final = read_json("final_verdict.json")
    assert audit["status"] == "PASS"
    assert determinism["status"] == "PASS"
    assert final["final_verdict"] == "HISTORICAL_RANGE_INSUFFICIENT"
    assert final["mechanism_called_edge"] is False
    assert final["pnl_tested"] is False
    assert final["algotest_used"] is False
