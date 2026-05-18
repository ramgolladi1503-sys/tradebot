from __future__ import annotations

import pytest

from core.paper_order_state_machine import (
    CANCEL_REQUESTED,
    CANCELLED,
    CREATED,
    FILLED,
    PARTIALLY_FILLED,
    REJECTED,
    SUBMITTED,
    PaperOrderStateError,
    create_paper_order_record,
    transition_paper_order,
)


def _decision(**overrides):
    payload = {
        "schema_version": 1,
        "state": "PAPER_DECISION_APPROVED",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "allowed_for_paper_order": True,
        "allowed_for_live_execution": False,
        "paper_intent_id": "intent-clean",
        "selected_strategy_id": "call_high",
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


def test_create_paper_order_record_from_approved_decision():
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")

    assert order.schema_version == 1
    assert order.paper_order_id == "paper-1"
    assert order.paper_intent_id == "intent-clean"
    assert order.state == CREATED
    assert order.quantity == 5
    assert order.filled_quantity == 0
    assert order.remaining_quantity == 5
    assert order.broker_order_action is False
    assert order.live_order_action is False
    assert len(order.transitions) == 1
    assert order.transitions[0].from_state == "NONE"
    assert order.transitions[0].to_state == CREATED
    assert order.blockers == ()


def test_create_paper_order_record_rejects_blocked_decision():
    with pytest.raises(PaperOrderStateError) as exc_info:
        create_paper_order_record(
            _decision(
                state="PAPER_DECISION_BLOCKED",
                allowed_for_paper_order=False,
                blockers=["RISK_SIZE_ZERO"],
            )
        )

    message = str(exc_info.value)
    assert "paper_order_record_preconditions_failed" in message
    assert "PAPER_DECISION_NOT_APPROVED" in message
    assert "PAPER_ORDER_NOT_ALLOWED" in message
    assert "RISK_SIZE_ZERO" in message


def test_create_paper_order_record_rejects_live_or_order_action_flags():
    with pytest.raises(PaperOrderStateError) as exc_info:
        create_paper_order_record(
            _decision(
                is_order_action=True,
                append=True,
                allowed_for_live_execution=True,
            )
        )

    message = str(exc_info.value)
    assert "DECISION_CONTAINS_ORDER_ACTION" in message
    assert "DECISION_APPEND_TRUE" in message
    assert "LIVE_EXECUTION_PERMISSION_UNEXPECTED" in message


def test_submit_then_full_fill_valid_transition_path():
    created = create_paper_order_record(_decision())
    submitted = transition_paper_order(created, SUBMITTED, reason="paper_submit", event_id="submit-1")
    filled = transition_paper_order(
        submitted,
        FILLED,
        reason="paper_fill_complete",
        event_id="fill-1",
        filled_quantity_delta=5,
    )

    assert submitted.state == SUBMITTED
    assert submitted.filled_quantity == 0
    assert submitted.remaining_quantity == 5
    assert filled.state == FILLED
    assert filled.filled_quantity == 5
    assert filled.remaining_quantity == 0
    assert [t.to_state for t in filled.transitions] == [CREATED, SUBMITTED, FILLED]


def test_partial_fill_then_full_fill_valid_transition_path():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")
    order = transition_paper_order(
        order,
        PARTIALLY_FILLED,
        reason="paper_partial_fill",
        event_id="fill-1",
        filled_quantity_delta=2,
    )
    order = transition_paper_order(
        order,
        FILLED,
        reason="paper_final_fill",
        event_id="fill-2",
        filled_quantity_delta=3,
    )

    assert order.state == FILLED
    assert order.filled_quantity == 5
    assert order.remaining_quantity == 0


def test_submit_then_cancel_valid_transition_path():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")
    order = transition_paper_order(order, CANCEL_REQUESTED, reason="user_cancel", event_id="cancel-req-1")
    order = transition_paper_order(order, CANCELLED, reason="cancel_confirmed", event_id="cancel-1")

    assert order.state == CANCELLED
    assert order.filled_quantity == 0
    assert order.remaining_quantity == 5


def test_created_can_reject_without_submit():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, REJECTED, reason="pre_submit_validation_failed", event_id="reject-1")

    assert order.state == REJECTED
    assert order.remaining_quantity == 5


def test_invalid_transition_jump_rejected():
    order = create_paper_order_record(_decision())

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, FILLED, reason="bad_jump", event_id="fill-1", filled_quantity_delta=5)

    assert "invalid_state_transition:CREATED->FILLED" in str(exc_info.value)


def test_terminal_state_transition_rejected():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")
    order = transition_paper_order(order, REJECTED, reason="paper_reject", event_id="reject-1")

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, CANCELLED, reason="bad_after_terminal", event_id="cancel-1")

    assert "terminal_state_transition_rejected:REJECTED->CANCELLED" in str(exc_info.value)


def test_duplicate_state_transition_rejected():
    order = create_paper_order_record(_decision())

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, CREATED, reason="duplicate", event_id="dup-1")

    assert "duplicate_state_transition_rejected:CREATED->CREATED" in str(exc_info.value)


def test_duplicate_transition_event_rejected_when_same_transition_and_event_repeated():
    order = create_paper_order_record(_decision())
    submitted = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="same-event")
    cancelled_path = transition_paper_order(submitted, CANCEL_REQUESTED, reason="cancel", event_id="cancel-1")

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(cancelled_path, SUBMITTED, reason="invalid_return", event_id="same-event")

    assert "invalid_state_transition:CANCEL_REQUESTED->SUBMITTED" in str(exc_info.value)


def test_fill_transition_requires_positive_delta():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, PARTIALLY_FILLED, reason="bad_partial", event_id="fill-1", filled_quantity_delta=0)

    assert "fill_transition_requires_positive_delta" in str(exc_info.value)


def test_non_fill_transition_rejects_fill_delta():
    order = create_paper_order_record(_decision())

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, SUBMITTED, reason="bad_submit", event_id="submit-1", filled_quantity_delta=1)

    assert "non_fill_transition_rejects_fill_delta" in str(exc_info.value)


def test_partial_fill_cannot_complete_order():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, PARTIALLY_FILLED, reason="bad_partial", event_id="fill-1", filled_quantity_delta=5)

    assert "partial_fill_cannot_complete_order" in str(exc_info.value)


def test_filled_state_requires_full_quantity():
    order = create_paper_order_record(_decision())
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")

    with pytest.raises(PaperOrderStateError) as exc_info:
        transition_paper_order(order, FILLED, reason="bad_full", event_id="fill-1", filled_quantity_delta=4)

    assert "filled_state_requires_full_quantity" in str(exc_info.value)


def test_to_dict_is_json_friendly_and_stable():
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")
    payload = order.to_dict()

    assert payload["schema_version"] == 1
    assert payload["paper_order_id"] == "paper-1"
    assert payload["state"] == CREATED
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["transitions"][0]["to_state"] == CREATED
    assert payload["metadata"]["state_machine"] == "paper_order_state_machine_v1"
    assert payload["metadata"]["scope"] == "in_memory_no_broker_calls_no_fill_model_no_ledger_mutation"
