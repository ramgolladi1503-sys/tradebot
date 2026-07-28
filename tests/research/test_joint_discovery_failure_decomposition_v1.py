from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/joint_discovery_failure_decomposition_v1")


def read_json(name: str):
    return json.loads((ROOT / name).read_text())


def test_prior_valid_result_is_verified() -> None:
    prior = read_json("prior_artifact_verification.json")
    final = read_json("final_verdict.json")
    assert prior["status"] == "PASS"
    assert final["source_commit"] == "37b49f85bb9d3f7791816289ccebfb063702b3a0"
    assert final["broker_api_called"] is False
    assert final["allowed_for_live_execution"] is False


def test_candidate_space_reconstructs_prior_grammar() -> None:
    coverage = read_json("candidate_space_coverage_map.json")
    assert coverage["development_evaluable_candidates"] == 72
    assert coverage["frozen_candidates"] == 4
    assert coverage["entry_clock"] == "next_observable_bar"
    assert "dte_interactions" in coverage["not_explored"]


def test_four_candidate_autopsy_classifies_each_failure() -> None:
    autopsy = read_json("four_candidate_failure_autopsy.json")["candidates"]
    assert len(autopsy) == 4
    for row in autopsy:
        assert row["development"]["trades"] > 0
        assert row["holdout"]["trades"] > 0
        assert row["failure_taxonomy"]


def test_redesign_is_not_a_failed_candidate_retune() -> None:
    mechanisms = read_json("redesigned_mechanisms.json")["mechanisms"]
    classes = read_json("testability_classification.json")
    assert len(mechanisms) <= 4
    assert classes["READY_FOR_FROZEN_TEST"]
    assert all("threshold" not in mechanism["name"] for mechanism in mechanisms)


def test_audit_and_determinism_pass() -> None:
    audit = read_json("independent_audit_report.json")
    determinism = read_json("determinism_report.json")
    assert audit["status"] == "PASS"
    assert audit["checks"]["no_production_modifications"] is True
    assert determinism["status"] == "PASS"
