from __future__ import annotations

from core.paper_intent_contract import (
    PAPER_INTENT_BLOCKED,
    PAPER_INTENT_READY,
    build_paper_intent_contract,
)


def _selection(**overrides):
    payload = {
        "schema_version": 1,
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "state": "SELECTED_FOR_PAPER",
        "selected_count": 1,
        "selected_strategy_ids": ["call_high"],
        "selections": [
            {
                "rank": 1,
                "strategy_id": "call_high",
                "symbol": "NIFTY",
                "direction": "BUY_CALL",
                "final_score": 0.82,
                "bucket": "EXECUTABLE_CANDIDATE",
                "score_eligibility": "SCORE_ELIGIBLE",
                "decision": "SELECTED_FOR_PAPER",
                "selected": True,
                "reasons": ["ranked_candidate_selected_for_paper"],
                "blockers": [],
                "warnings": [],
            }
        ],
        "blockers": [],
        "warnings": [],
        "reasons": [],
    }
    payload.update(overrides)
    return payload


def _contract(**overrides):
    payload = {
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "exchange": "NFO",
        "segment": "NFO-OPT",
        "resolution_path": "exact_contract_match",
        "fallback_candidate": False,
        "execution_grade": True,
        "advisory_only": False,
    }
    payload.update(overrides)
    return payload


def _quote(**overrides):
    payload = {
        "bid": 101.0,
        "ask": 102.0,
        "ltp": 101.5,
        "quote_source": "live_option_tick",
    }
    payload.update(overrides)
    return payload


def _feed(**overrides):
    payload = {
        "schema_version": 1,
        "gate_state": "FRESH",
        "allowed_for_execution": True,
        "allowed_for_paper_execution": True,
        "allowed_for_live_execution": True,
        "advisory_only": False,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _evidence(**overrides):
    payload = {
        "evidence_hash": "a" * 64,
        "latest_path": "/tmp/ranked_pipeline_runtime_latest.json",
        "daily_path": "/tmp/ranked_pipeline_runtime_2026-05-18.jsonl",
    }
    payload.update(overrides)
    return payload


def test_selected_candidate_builds_ready_paper_intent_contract():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_READY
    assert intent.ready_for_risk_review is True
    assert intent.allowed_for_paper_order is False
    assert intent.allowed_for_live_execution is False
    assert intent.is_order_action is False
    assert intent.append is False
    assert intent.paper_intent_id is not None
    assert len(intent.paper_intent_id) == 24
    assert intent.selected_strategy_id == "call_high"
    assert intent.instrument_token == 12345
    assert intent.tradingsymbol == "NIFTY26MAY22500CE"
    assert intent.bid == 101.0
    assert intent.ask == 102.0
    assert intent.ranked_pipeline_evidence_hash == "a" * 64
    assert intent.blockers == ()


def test_paper_intent_id_is_deterministic_for_same_basis():
    first = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )
    second = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(ltp=103.0),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert first.paper_intent_id == second.paper_intent_id


def test_non_selected_selection_report_blocks():
    intent = build_paper_intent_contract(
        _selection(state="WAIT", selected_count=0, selected_strategy_ids=[], selections=[]),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert intent.ready_for_risk_review is False
    assert intent.paper_intent_id is None
    assert "SELECTION_NOT_SELECTED_FOR_PAPER" in intent.blockers
    assert "SELECTED_RECORD_COUNT_NOT_ONE" in intent.blockers


def test_fallback_contract_blocks_paper_intent():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(
            resolution_path="safe_nearest_contract_fallback",
            fallback_candidate=True,
            execution_grade=False,
            advisory_only=True,
        ),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert "CONTRACT_NOT_EXACT_MATCH" in intent.blockers
    assert "CONTRACT_FALLBACK_CANDIDATE" in intent.blockers
    assert "CONTRACT_ADVISORY_ONLY" in intent.blockers
    assert "CONTRACT_NOT_EXECUTION_GRADE" in intent.blockers


def test_stale_or_advisory_feed_blocks_paper_intent():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(
            gate_state="ADVISORY_ONLY",
            allowed_for_paper_execution=False,
            advisory_only=True,
            blockers=["STALE_OPTION_LTP"],
        ),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert "STALE_OPTION_LTP" in intent.blockers
    assert "FEED_NOT_ALLOWED_FOR_PAPER_EXECUTION" in intent.blockers
    assert "FEED_GATE_ADVISORY_ONLY" in intent.blockers
    assert "FEED_GATE_NOT_FRESH" in intent.blockers


def test_missing_quote_blocks_paper_intent():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=None,
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert "QUOTE_SNAPSHOT_MISSING" in intent.blockers
    assert intent.ready_for_risk_review is False


def test_invalid_quote_blocks_paper_intent():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(bid=103.0, ask=102.0, ltp=None),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert "QUOTE_ASK_BELOW_BID" in intent.blockers
    assert "QUOTE_LTP_MISSING" in intent.blockers


def test_missing_evidence_blocks_paper_intent():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=None,
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert "RANKED_PIPELINE_EVIDENCE_MISSING" in intent.blockers
    assert intent.paper_intent_id is None


def test_selection_report_order_action_blocks():
    intent = build_paper_intent_contract(
        _selection(is_order_action=True),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )

    assert intent.state == PAPER_INTENT_BLOCKED
    assert "SELECTION_REPORT_CONTAINS_ORDER_ACTION" in intent.blockers


def test_to_dict_is_json_friendly_and_stable():
    intent = build_paper_intent_contract(
        _selection(),
        contract_resolution=_contract(),
        quote_snapshot=_quote(),
        feed_gate_decision=_feed(),
        ranked_pipeline_evidence=_evidence(),
    )
    payload = intent.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == PAPER_INTENT_READY
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["allowed_for_paper_order"] is False
    assert payload["allowed_for_live_execution"] is False
    assert payload["blockers"] == []
    assert payload["metadata"]["contract"] == "paper_intent_contract_v1"
