from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/prospective_structural_edge_v2")


def test_failure_knowledge_ingests_all_prior_hypotheses():
    data = json.loads((BASE / "cumulative_failure_knowledge.json").read_text())

    assert data["prior_hypotheses_analyzed"] == 18
    assert len(data["records"]) == 18
    assert all("forbidden_cosmetic_descendants" in row for row in data["records"])


def test_family_status_tracks_open_and_weak_families():
    data = json.loads((BASE / "mechanism_family_status.json").read_text())

    assert data["family_status"]["compression_breakout"] == "WEAK_OR_UNSTABLE"
    assert data["family_status"]["opening_repair_state"] == "OPEN_FOR_MATERIALLY_DISTINCT_MECHANISM"


def test_cycle5_started_hypotheses_are_not_evaluated_when_cosmetic():
    audit = json.loads((BASE / "cycle5_hypothesis_ancestry_audit.json").read_text())

    assert audit["results"]["AC19_INTRADAY_RANGE_COMPRESSION_RELEASE"]["verdict"] == "REJECTED_COSMETIC_VARIANT"
    assert audit["results"]["AC20_PRIOR_DAY_INSIDE_VALUE_BREAK_ACCEPTANCE"]["verdict"] == "REJECTED_COSMETIC_VARIANT"
    assert audit["results"]["AC21_CROSS_INDEX_PULLBACK_NONCONFIRMATION_REVERSAL"]["verdict"] == "REJECTED_COSMETIC_VARIANT"
    assert audit["replacements"] == [
        "AC22_OPENING_REPAIR_SECOND_SIDE_ACCEPTANCE",
        "AC23_TWO_INDEX_EXTENSION_NONCONFIRMATION_REVERSAL",
        "AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION",
    ]


def test_cycle5_replacement_contracts_are_outcome_blind_and_counterfactual_frozen():
    for hypothesis_id in [
        "AC22_OPENING_REPAIR_SECOND_SIDE_ACCEPTANCE",
        "AC23_TWO_INDEX_EXTENSION_NONCONFIRMATION_REVERSAL",
        "AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION",
    ]:
        hdir = BASE / "hypotheses" / hypothesis_id
        contract = json.loads((hdir / "specification_contract.json").read_text())
        counterfactual = json.loads((hdir / "matched_counterfactual_contract.json").read_text())

        assert contract["outcomes_read_before_contract_freeze"] is False
        assert contract["parameters_optimized"] is False
        assert contract["same_bar_rules"] == "confirmation and entry on same bar prohibited"
        assert counterfactual["frozen_before_outcomes"] is True


def test_cycle5_mechanism_quality_oracle_passes_before_outcomes():
    oracle = json.loads((BASE / "cycle5_mechanism_quality_oracle.json").read_text())

    assert oracle["verdict"] == "CYCLE5_MECHANISM_QUALITY_PASS"
    assert oracle["outcomes_read_before_contract_freeze"] is False
    assert oracle["candidate_counts_calculated_before_contract_freeze"] is False
