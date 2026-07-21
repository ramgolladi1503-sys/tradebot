from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/independent_underlying_confirmation_v3")


def test_no_interim_candidate_counts_or_epoch_opening():
    final = json.loads((BASE / "final_verdict.json").read_text())

    assert final["FINAL_VERDICT"] == "WAITING_FOR_INDEPENDENT_UNSEEN_DATA"
    assert final["interim_candidate_counts_inspected"] is False
    assert final["independent_epoch_opened"] is False
    assert final["AC24_independent_result"] == "NOT_OPENED"
    assert final["AC16_independent_result"] == "NOT_OPENED"


def test_option_and_execution_claims_are_prohibited():
    final = json.loads((BASE / "final_verdict.json").read_text())

    assert final["bid_ask_required"] is False
    assert final["option_data_used"] is False
    assert final["option_economic_certification"] == "OUT_OF_SCOPE"
    assert final["production_strategy_created"] is False
    assert final["execution_eligibility"] is False
    assert final["broker_api_called"] is False
    assert final["order_action"] is False


def test_pre_open_audit_passes_waiting_state():
    audit = json.loads((BASE / "pre_open_audit.json").read_text())

    assert audit["verdict"] == "PASS_WAITING_NOT_OPENED"
    assert audit["same_corpus_epoch_closed"] is True
    assert audit["no_strategy_specific_readiness_leakage"] is True
