from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/joint_underlying_option_structural_discovery_v1")


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_pipeline_verdict_is_valid_and_audited() -> None:
    final = read_json("final_verdict.json")
    audit = read_json("independent_audit_report.json")
    assert final["final_verdict"] in {
        "JOINT_STRUCTURAL_EDGE_CANDIDATE_FOUND",
        "NO_JOINT_STRUCTURAL_EDGE_FOUND",
        "INSUFFICIENT_STATISTICAL_POWER",
        "INVALID_DISCOVERY_PIPELINE",
    }
    assert audit["status"] == "PASS"
    assert audit["checks"]["no_production_modifications"] is True
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False


def test_research_universe_uses_governed_joint_warehouse() -> None:
    manifest = read_json("trusted_input_manifest.json")
    contract = read_json("discovery_contract.json")
    assert manifest["rows"] == 392006
    assert manifest["semantic_hash"] == "48ae9f351b6ca0f0f1a970ae8a10c863be90d5c127d841b29193a3e71d8cd954"
    assert "true bid/ask spread" in contract["unsupported"]
    assert contract["entry_clock"] == "next_observable_bar"


def test_no_survivor_goes_to_algotest_when_rejected() -> None:
    final = read_json("final_verdict.json")
    algotest = read_json("algotest_translation_specifications.json")
    if final["final_verdict"] == "NO_JOINT_STRUCTURAL_EDGE_FOUND":
        assert algotest["candidates"] == []


def test_multiple_testing_and_holdout_reports_exist() -> None:
    mt = read_json("multiple_testing_report.json")
    holdout = read_json("holdout_results.json")
    walk = read_json("walk_forward_results.json")
    assert mt["evaluated_candidate_count"] >= mt["frozen_candidate_count"]
    assert "candidates" in holdout
    assert "candidates" in walk


def test_two_directory_determinism_passes() -> None:
    determinism = read_json("determinism_report.json")
    assert determinism["status"] == "PASS"
    assert determinism["two_directory_determinism"] == "PASS"
