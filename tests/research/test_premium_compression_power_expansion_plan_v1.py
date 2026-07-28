from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/premium_compression_power_expansion_plan_v1")
MECHANISM = "premium_compression_release_with_underlying_state_filter"


def read_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_only_premium_compression_contract_is_planned() -> None:
    proof = read_json("contract_identity_proof.json")
    prior = read_json("prior_result_verification.json")
    assert proof["mechanism"] == MECHANISM
    assert proof["unchanged"] is True
    assert prior["delayed_status"] == "REJECTED_POWERED_NEGATIVE_NOT_RETESTED"
    assert prior["premium_status"] == "UNRESOLVED_POSITIVE_UNDERPOWERED"


def test_effective_sample_size_matches_prior_underpowered_holdout() -> None:
    report = read_json("effective_sample_size_report.json")
    assert report["raw_trades"] == 21
    assert report["unique_sessions"] == 8
    assert report["unique_expiries"] == 6
    assert sum(report["ce_pe_counts"].values()) == 21
    assert report["cluster_bootstrap_ci_by_session"]["ci95_low"] < 0


def test_required_evidence_uses_shrinkage_scenarios() -> None:
    required = read_json("required_additional_evidence_table.json")
    assert set(required) == {"25pct_observed", "50pct_observed", "75pct_observed", "full_observed"}
    assert required["50pct_observed"]["additional_for_research_grade"]["sessions"] >= 10
    assert required["25pct_observed"]["additional_for_research_grade"]["trades"] > required["50pct_observed"]["additional_for_research_grade"]["trades"]


def test_inventory_and_provider_plan_are_non_executing() -> None:
    inventory = read_json("exhaustive_local_data_inventory.json")
    provider = read_json("provider_feasibility_report.json")
    assert inventory["item_count"] > 0
    assert provider["provider_calls_made"] is False


def test_audit_determinism_and_final_verdict() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    final = read_json("final_verdict.json")
    assert audit["status"] == "PASS"
    assert determinism["status"] == "PASS"
    assert final["final_campaign_verdict"] in {
        "EXISTING_LOCAL_DATA_CAN_EXTEND_TEST",
        "AUTHORIZED_HISTORICAL_ACQUISITION_REQUIRED",
        "MECHANISM_NOT_PRACTICALLY_TESTABLE",
        "INVALID_POWER_EXPANSION_PLAN",
    }
    assert final["mechanism_called_edge"] is False
    assert final["broker_api_called"] is False
    assert final["algotest_used"] is False
