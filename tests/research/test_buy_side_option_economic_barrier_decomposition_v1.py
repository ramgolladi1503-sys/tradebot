from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/buy_side_option_economic_barrier_decomposition_v1")
EXPECTED = {
    "FQSDV2_PAIR_ASYM_01",
    "FQSDV2_LADDER_CONFIRM_02",
    "FQSDV2_EXPIRY_TRANSITION_03",
}


def read_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_prior_artifacts_and_candidate_set_are_fixed() -> None:
    prior = read_json("prior_artifact_verification.json")
    pre = read_json("pre_change_manifest.json")
    assert prior["status"] == "PASS"
    assert prior["prior_final_verdict"]["final_verdict"] == "NO_FREQUENCY_QUALIFIED_EDGE_FOUND"
    assert set(pre["candidate_contract_hashes"]) == EXPECTED


def test_gross_expectancy_is_negative_before_costs() -> None:
    gross = read_json("gross_versus_net_decomposition.json")
    assert set(gross) == EXPECTED
    assert gross["FQSDV2_PAIR_ASYM_01"]["trades"] == 5004
    assert gross["FQSDV2_LADDER_CONFIRM_02"]["trades"] == 6010
    assert gross["FQSDV2_EXPIRY_TRANSITION_03"]["trades"] == 2145
    assert all(row["gross_expectancy_before_costs"] < 0 for row in gross.values())
    assert all(row["net_expectancy_after_costs"] < row["gross_expectancy_before_costs"] for row in gross.values())


def test_classification_and_verdict_are_not_rescue_language() -> None:
    classifications = read_json("per_candidate_classification.json")
    final = read_json("final_verdict.json")
    assert set(classifications) == EXPECTED
    assert set(classifications.values()) == {"INTRINSICALLY_NEGATIVE"}
    assert final["final_campaign_verdict"] == "CURRENT_BUY_SIDE_SEARCH_SPACE_EXHAUSTED"
    assert final["new_mechanisms_generated"] is False
    assert final["thresholds_tuned"] is False


def test_cost_model_audit_finds_no_defect() -> None:
    cost = read_json("cost_model_audit.json")
    assert cost["status"] == "PASS"
    assert cost["frozen_round_trip_cost_points"] == 1.0
    assert cost["defect_found"] is False


def test_audit_and_determinism_pass() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    assert audit["status"] == "PASS"
    assert audit["checks"]["no_new_mechanisms"] is True
    assert audit["checks"]["no_provider_calls"] is True
    assert audit["checks"]["no_algotest"] is True
    assert audit["checks"]["no_production_modifications"] is True
    assert determinism["status"] == "PASS"
