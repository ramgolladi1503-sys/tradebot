from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/prospective_structural_edge_v2")


def test_cycle6_intake_consumes_cycle5_lessons():
    intake = json.loads((BASE / "cycle6_failure_learning_intake.json").read_text())

    assert intake["cycle5_evidence_ingested"] is True
    assert intake["AC22_lesson"]["sample"] == [88, 88]
    assert intake["AC22_lesson"]["negative_controls"] == "REJECTED_NEGATIVE_CONTROL_FAILURE"
    assert intake["AC23_lesson"]["aggregate_mean_bps"] == 1.0507
    assert intake["AC24_lesson"]["positive_session_fraction"] == 0.513


def test_cycle6_outcome_dependency_rejects_descendants():
    risk = json.loads((BASE / "cycle6_outcome_dependency_risk.json").read_text())

    assert risk["AC25_OPENING_AUCTION_FAILURE_BASKET_MEDIAN_RETURN"]["verdict"] == "REJECTED_OUTCOME_DEPENDENT_DESCENDANT"
    assert risk["AC26_PRIOR_RANGE_MIDPOINT_ACCEPTANCE_ROTATION"]["verdict"] == "REJECTED_OUTCOME_DEPENDENT_DESCENDANT"
    assert risk["AC27_THREE_INDEX_VOLATILITY_CONTRACTION_ASYMMETRY"]["verdict"] == "REJECTED_EXHAUSTED_MECHANISM_FAMILY"


def test_cycle6_mechanism_family_update_blocks_same_corpus_repairs():
    update = json.loads((BASE / "cycle6_mechanism_family_update.json").read_text())

    assert update["opening_repair_state"]["current_definition_status"] == "FALSIFIED_BY_CURRENT_DEFINITION"
    assert update["nonconfirmation_reversal"]["additional_same_corpus_variants_allowed"] is False
    assert update["prior_midpoint_rejection"]["fresh_data_confirmation_priority"] is True
    assert update["compression_breakout"]["family_level_status"] == "EXHAUSTED_BY_CURRENT_OHLCV_CORPUS"
