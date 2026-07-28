from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/frozen_joint_mechanisms_v1")
EXPECTED = {
    "delayed_option_convexity_after_underlying_confirmation",
    "premium_compression_release_with_underlying_state_filter",
}


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_exactly_two_frozen_mechanisms() -> None:
    contracts = read_json("mechanism_contracts.json")
    results = read_json("mechanism_results.json")
    assert set(contracts) == EXPECTED
    assert set(results) == EXPECTED


def test_final_verdict_is_allowed_and_safe() -> None:
    final = read_json("final_verdict.json")
    assert final["final_verdict"] in {
        "FROZEN_MECHANISM_SURVIVED",
        "NO_FROZEN_MECHANISM_SURVIVED",
        "INSUFFICIENT_POWER_FOR_FROZEN_MECHANISMS",
        "INVALID_FROZEN_MECHANISM_TEST",
    }
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False


def test_audit_and_determinism_pass() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    assert audit["status"] == "PASS"
    assert audit["checks"]["exactly_two_contracts"] is True
    assert determinism["status"] == "PASS"


def test_no_algotest_spec_when_no_survivor() -> None:
    final = read_json("final_verdict.json")
    algotest = read_json("algotest_translation_specification.json")
    if not final["surviving_mechanisms"]:
        assert algotest["specifications"] == []
