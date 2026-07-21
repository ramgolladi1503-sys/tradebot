import json

from research.rsi2_mean_reversion.independent_publication_oracle_v2 import (
    REQUIRED_CONTROLS,
    V2,
    control_truth,
    decide,
    decision_contract,
    independent_random_replicates,
    parameter_neighborhood_truth,
    random_summary,
    tradable_inventory,
    trend_filter_audit,
)


def test_construction_status_separate_from_economic_result():
    summary = random_summary(independent_random_replicates().head(5))

    assert summary["construction_status"] == "PASS"
    assert summary["economic_control_status"] == "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM"
    assert summary["supports_structural_edge"] is False


def test_random_superiority_failure_maps_to_no_structural_edge():
    random = random_summary(independent_random_replicates())
    controls = control_truth(random)
    verdict = decide(random, controls, trend_filter_audit(), tradable_inventory())

    assert verdict["index_signal_verdict"] == "NO_STRUCTURAL_EDGE"
    assert verdict["overall_research_verdict"] == "NO_STRUCTURAL_EDGE"


def test_concentration_and_parameter_neighbors_do_not_override_adverse_controls():
    contract = decision_contract()
    neighborhood = parameter_neighborhood_truth()

    assert "NO_STRUCTURAL_EDGE" in contract["precedence"]
    assert neighborhood["cannot_override_adverse_controls"] is True


def test_trend_and_tradable_availability_are_evidence_derived_not_generic_flags():
    trend = trend_filter_audit()
    tradable = tradable_inventory()

    assert trend["verdict"] == "TREND_FILTER_IMPROVES_POINT_ESTIMATE_BUT_UNCERTAIN"
    assert trend["audit"]["trade_count_comparable"] is False
    assert tradable["derived_from_inventory"] is True
    assert tradable["verdict"] == "INSUFFICIENT_TRADABLE_DATA"


def test_control_presence_differs_from_outcome_and_exposes_adverse_controls():
    rows = control_truth(random_summary(independent_random_replicates().head(5)))
    by_id = {row["control_id"]: row for row in rows}

    assert set(by_id) == set(REQUIRED_CONTROLS)
    assert by_id["matched_random"]["present"] is True
    assert by_id["matched_random"]["economic_result"] == "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM"
    assert by_id["matched_random"]["rejects_edge"] is True
    assert by_id["inverted_rsi_condition"]["economic_result"] == "ADVERSE_INVERTED_RSI_BETTER_THAN_BASE_PF"
    assert by_id["one_session_signal_shift_forward"]["economic_result"] == "ADVERSE_POSITIVE_SHIFT_CONTROL"


def test_publication_pass_does_not_imply_edge_pass_after_generation():
    report = json.loads((V2 / "final_publication_report_v2.json").read_text())

    assert report["publication_integrity_verdict"] == "PASS_PUBLICATION_GATE"
    assert report["strategy_scientific_verdict"] == "NO_STRUCTURAL_EDGE"
    assert report["structural_edge_supported"] is False

