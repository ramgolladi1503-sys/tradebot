from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/frequency_qualified_structural_discovery_v2")
PARKED = "premium_compression_release_with_underlying_state_filter"


def read_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_hypotheses_are_bounded_and_exclude_prior_mechanisms() -> None:
    hypotheses = read_json("hypothesis_catalogue.json")
    prior = read_json("prior_mechanism_exclusion_manifest.json")
    ids = {row["id"] for row in hypotheses}
    assert len(hypotheses) <= 12
    assert PARKED not in ids
    assert PARKED in prior["parked_not_reusable"]
    assert "delayed_option_convexity_after_underlying_confirmation" in prior["rejected"]


def test_frequency_gate_precedes_frozen_contracts() -> None:
    frequency = read_json("frequency_gate_report.json")
    frozen = read_json("frozen_candidate_contracts.json")
    assert len(frozen) <= 3
    assert all(frequency[row["id"]]["passed"] is True for row in frozen)
    assert all(row["entry_timing"] == "next_observable_bar" for row in frozen)
    assert all(row["costs"]["round_trip_points"] == 1.0 for row in frozen)


def test_frozen_candidates_have_adequate_holdout_but_negative_results() -> None:
    holdout = read_json("holdout_report.json")
    assert holdout
    assert all(row["trades"] >= 100 for row in holdout.values())
    assert all(row["session_count"] >= 30 for row in holdout.values())
    assert all(row["expiry_count"] >= 12 for row in holdout.values())
    assert all(row["net_expectancy_points"] < 0 for row in holdout.values())


def test_audit_determinism_and_final_verdict() -> None:
    audit = read_json("independent_audit.json")
    determinism = read_json("determinism_report.json")
    final = read_json("final_verdict.json")
    assert audit["status"] == "PASS"
    assert audit["checks"]["pnl_after_frequency_freeze_only"] is True
    assert audit["checks"]["prior_rejected_and_parked_excluded"] is True
    assert determinism["status"] == "PASS"
    assert final["final_verdict"] in {
        "FREQUENCY_QUALIFIED_EDGE_CANDIDATE_FOUND",
        "NO_FREQUENCY_QUALIFIED_EDGE_FOUND",
        "NO_MECHANISM_PASSED_FREQUENCY_GATE",
        "INVALID_DISCOVERY_PIPELINE",
    }
    assert final["final_verdict"] == "NO_FREQUENCY_QUALIFIED_EDGE_FOUND"
    assert final["broker_api_called"] is False
    assert final["algotest_used"] is False


def test_no_algotest_spec_without_survivor() -> None:
    final = read_json("final_verdict.json")
    algotest = read_json("algotest_specifications.json")
    if not final["surviving_candidates"]:
        assert algotest["specifications"] == []
