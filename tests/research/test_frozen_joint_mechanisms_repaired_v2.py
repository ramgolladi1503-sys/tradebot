from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/frozen_joint_mechanisms_repaired_v2")
EXPECTED = {
    "delayed_option_convexity_after_underlying_confirmation",
    "premium_compression_release_with_underlying_state_filter",
}


def read_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_exactly_two_prior_contracts_are_preserved() -> None:
    proof = read_json("contract_identity_proof.json")
    results = read_json("mechanism_results.json")
    assert set(proof["contracts"]) == EXPECTED
    assert set(results) == EXPECTED
    assert proof["contracts_modified_for_rerun"] is False


def test_repaired_input_integrity() -> None:
    manifest = read_json("repaired_input_manifest.json")
    assert manifest["rows"] == 392006
    assert manifest["ret_1_non_null"] == 392006
    assert manifest["duplicate_contract_timestamp_keys"] == 0
    assert manifest["certified_for_replay_true"] == 392006


def test_event_reconstruction_after_feature_repair() -> None:
    funnel = read_json("event_funnel_report.json")
    assert set(funnel) == EXPECTED
    assert all(row["final_event"] > 0 for row in funnel.values())
    assert all(row["holdout_event_count"] > 0 for row in funnel.values())


def test_final_verdict_is_allowed_and_safe() -> None:
    final = read_json("final_verdict.json")
    assert final["final_verdict"] in {
        "FROZEN_MECHANISM_SURVIVED",
        "NO_FROZEN_MECHANISM_SURVIVED",
        "INSUFFICIENT_POWER_AFTER_REPAIR",
        "INVALID_FROZEN_RERUN",
    }
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False
    assert final["is_order_action"] is False


def test_audit_and_determinism_pass() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    assert audit["status"] == "PASS"
    assert audit["checks"].get("contract_identity_matches_prior", audit["checks"].get("contract_identity_preserved")) is True
    assert audit["checks"]["no_production_modifications"] is True
    assert determinism["status"] == "PASS"


def test_no_algotest_spec_when_no_survivor() -> None:
    final = read_json("final_verdict.json")
    algotest = read_json("algotest_translation_specification.json")
    if not final["surviving_mechanisms"]:
        assert algotest["specifications"] == []
