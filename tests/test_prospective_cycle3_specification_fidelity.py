from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/prospective_structural_edge_v2")
HYPOTHESES = [
    "AC11_ASYNC_OPENING_DISPLACEMENT_PROPAGATION",
    "AC12_PRIOR_CLOSE_LOCATION_NEUTRAL_GAP_CONTINUATION",
    "AC13_OPENING_DISPERSION_CONVERGENCE",
    "AC14_FIRST_HOUR_VOL_OF_VOL_TRANSITION",
    "AC15_MORNING_TREND_INTERRUPTION_SECOND_IMPULSE",
]


def _contract(hypothesis_id: str) -> dict:
    return json.loads((BASE / "hypotheses" / hypothesis_id / "specification_contract_v2.json").read_text())


def test_v1_defects_are_audited_and_v2_oracle_passes():
    audit = json.loads((BASE / "cycle3_specification_fidelity_audit.json").read_text())

    assert audit["oracle_verdict"] == "CYCLE3_SPECIFICATION_FIDELITY_PASS"
    assert audit["outcome_files_read"] is False
    assert audit["candidate_counts_calculated"] is False
    assert audit["parameter_optimization"] is False
    assert all(result["generic_placeholders_detected"] for result in audit["results"])


def test_v2_contracts_have_unique_parameter_hashes_and_no_placeholders():
    hashes = []
    forbidden = "mechanism-specific"
    for hypothesis_id in HYPOTHESES:
        contract = _contract(hypothesis_id)
        payload = json.dumps(contract).lower()
        assert forbidden not in payload
        assert contract["first_legal_timestamp"].startswith("next completed")
        assert "same-bar" in contract["same_bar_behavior"].lower()
        assert "canonical sha256" in contract["candidate_identity"]
        assert contract["parameter_hash"]
        hashes.append(contract["parameter_hash"])

    assert len(set(hashes)) == len(HYPOTHESES)


def test_ac11_leader_laggard_and_scale_normalization_are_executable():
    contract = _contract("AC11_ASYNC_OPENING_DISPLACEMENT_PROPAGATION")

    assert "largest absolute normalized displacement" in contract["leader_symbol_or_basket_owner"]
    assert "displacement_bps" in contract["normalization_formula"]
    assert "max_laggard_displacement_bps" in contract["threshold_formula"]
    assert contract["target_symbol"] == "confirming_laggard_symbol"


def test_ac12_prior_session_and_neutral_gap_boundaries_are_executable():
    contract = _contract("AC12_PRIOR_CLOSE_LOCATION_NEUTRAL_GAP_CONTINUATION")

    assert "immediately preceding complete authoritative session" in " ".join(contract["state_machine"])
    assert "prior_close_location" in contract["normalization_formula"]
    assert "neutral gap <= 10 bps" in contract["threshold_formula"]


def test_ac13_chooses_convergence_not_divergence():
    contract = _contract("AC13_OPENING_DISPERSION_CONVERGENCE")

    assert "choose premise CONVERGENCE_TO_BASKET" in contract["state_machine"]
    assert "DIVERGENCE" not in json.dumps(contract)
    assert "median" in contract["leader_symbol_or_basket_owner"]


def test_ac14_uses_training_only_vol_of_vol_threshold():
    contract = _contract("AC14_FIRST_HOUR_VOL_OF_VOL_TRANSITION")

    percentile = contract["parameters"]["vol_of_vol_training_percentile"]
    assert percentile["owner"] == "training_only_empirical_quantile"
    assert "validation never refits" in percentile["boundary_behavior"]
    assert "directional acceptance" in contract["confirmation_formula"]


def test_ac15_vwap_pause_and_second_impulse_are_distinct():
    contract = _contract("AC15_MORNING_TREND_INTERRUPTION_SECOND_IMPULSE")

    assert "VWAP_UNIT_WEIGHT_PROXY" in " ".join(contract["state_machine"])
    assert "same bar pause completion cannot be breakout" in " ".join(contract["state_machine"])
    assert "generic trend pullback" not in contract["mechanism_family"].lower()
