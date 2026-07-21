from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/prospective_structural_edge_v2")
HYPOTHESES = [
    "AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION",
    "AC17_CORRELATION_BREAKDOWN_LEADER_RESPONSE",
    "AC18_LATE_MULTI_INDEX_CONFIRMATION_CONTINUATION",
]


def test_cycle4_v2_placeholder_detection_and_outcome_blindness():
    audit = json.loads((BASE / "cycle4_specification_fidelity_audit.json").read_text())

    assert audit["oracle_verdict"] == "CYCLE4_SPECIFICATION_FIDELITY_PASS"
    assert audit["outcomes_read_before_v3_freeze"] is False
    assert audit["candidate_counts_calculated_before_v3_freeze"] is False
    assert audit["development_returns_calculated_before_v3_freeze"] is False
    assert audit["prospective_sessions_evaluated"] is False
    assert any(
        "GENERIC_PLACEHOLDER" in result["candidate_affecting_field_classifications"].values()
        for result in audit["results"]
    )


def test_cycle4_v3_contracts_are_executable_and_underlying_only():
    for hypothesis_id in HYPOTHESES:
        contract = json.loads((BASE / "hypotheses" / hypothesis_id / "specification_contract_v3.json").read_text())
        payload = json.dumps(contract).lower()

        assert "specified by causal completed-bar state machine" not in payload
        assert contract["contract_status"] == "FROZEN_EXECUTABLE_PRE_OUTCOME_V3"
        assert contract["underlying_only"] is True
        assert contract["option_data_used"] is False
        assert contract["parameters_optimized"] is False
        assert contract["same_bar_behavior"] == "same-bar confirmation and entry prohibited"
        assert contract["parameter_hash"]
        assert contract["specification_hash"]


def test_cycle4_parameter_contracts_are_owned_and_non_inert():
    for hypothesis_id in HYPOTHESES:
        matrix = json.loads((BASE / "hypotheses" / hypothesis_id / "parameter_ownership_matrix_v3.json").read_text())
        for parameter in matrix["parameters"]:
            assert parameter["owner"] == "pre_outcome_structural_contract_v3"
            assert parameter["candidate_gate_role"] in {
                "candidate presence",
                "candidate timing",
                "candidate identity",
                "direction",
                "raw score",
                "evidence only",
            }
            assert parameter["sensitivity_neighbors"]


def test_ac16_acceptance_fraction_denominator_is_prior_day_range():
    contract = json.loads((BASE / "hypotheses" / HYPOTHESES[0] / "specification_contract_v3.json").read_text())

    assert contract["acceptance_fraction_denominator"] == "prior-day range = prior_day_high - prior_day_low"
    assert "prior_day_high + 0.26 * prior_day_range" == contract["long_acceptance_level"]
    assert "prior_day_low - 0.26 * prior_day_range" == contract["short_acceptance_level"]


def test_ac17_correlation_and_tie_rules_are_frozen():
    contract = json.loads((BASE / "hypotheses" / HYPOTHESES[1] / "specification_contract_v3.json").read_text())

    assert "Pearson" in contract["correlation_estimator"]
    assert contract["parameters"]["breakdown_correlation_threshold"]["value"] == 0.18
    assert "symbol-order tie-break" in contract["leader_selection_rule"]
    assert "symbol-order tie-break" in contract["laggard_selection_rule"]


def test_ac18_confirmation_count_is_not_overloaded():
    contract = json.loads((BASE / "hypotheses" / HYPOTHESES[2] / "specification_contract_v3.json").read_text())

    assert contract["required_confirming_indices"] == 2
    assert contract["required_confirmation_bars"] == 1
    assert contract["acceptance_fraction_denominator"] == "each index own completed-bar morning range"
