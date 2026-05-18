from __future__ import annotations

from core.paper_decision_orchestrator import (
    PAPER_DECISION_APPROVED,
    PAPER_DECISION_BLOCKED,
    build_paper_decision_report,
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
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _intent(**overrides):
    payload = {
        "schema_version": 1,
        "state": "PAPER_INTENT_READY",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "paper_intent_id": "intent123",
        "ready_for_risk_review": True,
        "allowed_for_paper_order": False,
        "allowed_for_live_execution": False,
        "selected_strategy_id": "call_high",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _risk(**overrides):
    payload = {
        "schema_version": 1,
        "state": "RISK_APPROVED",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "allowed_for_paper_order": True,
        "allowed_for_live_execution": False,
        "paper_intent_id": "intent123",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "quantity": 5,
        "entry_price": 100.0,
        "estimated_notional": 500.0,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_clean_selection_intent_and_risk_approve_paper_decision():
    decision = build_paper_decision_report(_selection(), _intent(), _risk())

    assert decision.state == PAPER_DECISION_APPROVED
    assert decision.allowed_for_paper_order is True
    assert decision.allowed_for_live_execution is False
    assert decision.read_only is True
    assert decision.is_order_action is False
    assert decision.append is False
    assert decision.paper_intent_id == "intent123"
    assert decision.selected_strategy_id == "call_high"
    assert decision.symbol == "NIFTY"
    assert decision.direction == "BUY_CALL"
    assert decision.instrument_token == 12345
    assert decision.tradingsymbol == "NIFTY26MAY22500CE"
    assert decision.quantity == 5
    assert decision.entry_price == 100.0
    assert decision.estimated_notional == 500.0
    assert decision.blockers == ()


def test_missing_selection_blocks_decision():
    decision = build_paper_decision_report(None, _intent(), _risk())

    assert decision.state == PAPER_DECISION_BLOCKED
    assert decision.allowed_for_paper_order is False
    assert "SELECTION_REPORT_MISSING" in decision.blockers


def test_non_selected_selection_blocks_decision():
    decision = build_paper_decision_report(
        _selection(state="WAIT", selected_count=0),
        _intent(),
        _risk(),
    )

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "SELECTION_NOT_SELECTED_FOR_PAPER" in decision.blockers
    assert "SELECTION_SELECTED_COUNT_NOT_ONE" in decision.blockers


def test_order_action_selection_blocks_decision():
    decision = build_paper_decision_report(_selection(is_order_action=True), _intent(), _risk())

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "SELECTION_REPORT_CONTAINS_ORDER_ACTION" in decision.blockers


def test_missing_paper_intent_blocks_decision():
    decision = build_paper_decision_report(_selection(), None, _risk())

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "PAPER_INTENT_MISSING" in decision.blockers


def test_blocked_paper_intent_blocks_decision():
    decision = build_paper_decision_report(
        _selection(),
        _intent(state="PAPER_INTENT_BLOCKED", ready_for_risk_review=False, blockers=["CONTRACT_FALLBACK_CANDIDATE"]),
        _risk(),
    )

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "CONTRACT_FALLBACK_CANDIDATE" in decision.blockers
    assert "PAPER_INTENT_NOT_READY" in decision.blockers
    assert "PAPER_INTENT_NOT_READY_FOR_RISK_REVIEW" in decision.blockers


def test_paper_intent_order_permission_is_rejected_before_orchestrator():
    decision = build_paper_decision_report(
        _selection(),
        _intent(allowed_for_paper_order=True),
        _risk(),
    )

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "PAPER_INTENT_ORDER_PERMISSION_UNEXPECTED" in decision.blockers


def test_missing_risk_decision_blocks_decision():
    decision = build_paper_decision_report(_selection(), _intent(), None)

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "RISK_DECISION_MISSING" in decision.blockers


def test_blocked_risk_decision_blocks_decision():
    decision = build_paper_decision_report(
        _selection(),
        _intent(),
        _risk(state="RISK_BLOCKED", allowed_for_paper_order=False, quantity=0, blockers=["RISK_SIZE_ZERO"]),
    )

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "RISK_SIZE_ZERO" in decision.blockers
    assert "RISK_DECISION_NOT_APPROVED" in decision.blockers
    assert "RISK_NOT_ALLOWED_FOR_PAPER_ORDER" in decision.blockers
    assert "RISK_QUANTITY_ZERO" in decision.blockers


def test_risk_live_execution_permission_blocks_decision():
    decision = build_paper_decision_report(_selection(), _intent(), _risk(allowed_for_live_execution=True))

    assert decision.state == PAPER_DECISION_BLOCKED
    assert "RISK_LIVE_EXECUTION_UNEXPECTED" in decision.blockers


def test_warnings_are_propagated_without_blocking():
    decision = build_paper_decision_report(
        _selection(warnings=["directional_balance_warning"]),
        _intent(warnings=["intent_warning"]),
        _risk(warnings=["risk_warning"]),
    )

    assert decision.state == PAPER_DECISION_APPROVED
    assert "DIRECTIONAL_BALANCE_WARNING" in decision.warnings
    assert "INTENT_WARNING" in decision.warnings
    assert "RISK_WARNING" in decision.warnings


def test_to_dict_is_json_friendly_and_stable():
    decision = build_paper_decision_report(_selection(), _intent(), _risk())
    payload = decision.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == PAPER_DECISION_APPROVED
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["allowed_for_paper_order"] is True
    assert payload["allowed_for_live_execution"] is False
    assert payload["blockers"] == []
    assert payload["metadata"]["orchestrator"] == "paper_decision_orchestrator_v1"
    assert payload["metadata"]["scope"] == "read_only_no_order_creation_no_broker_calls_no_ledger_mutation"
