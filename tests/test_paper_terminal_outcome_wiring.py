from __future__ import annotations

import pytest

from core.offline_family_learning import load_family_learning_state, load_family_outcome_records
from core.paper_order_state_machine import FILLED, REJECTED, SUBMITTED, create_paper_order_record, transition_paper_order
from core.paper_terminal_outcome_wiring import (
    PaperTerminalOutcomeWiringError,
    build_terminal_paper_outcome,
    record_terminal_paper_outcome,
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


def _filled_order():
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")
    order = transition_paper_order(order, SUBMITTED, reason="paper_submit", event_id="submit-1")
    return transition_paper_order(
        order,
        FILLED,
        reason="paper_fill_complete",
        event_id="fill-1",
        filled_quantity_delta=5,
    )


def test_build_terminal_paper_outcome_maps_filled_order_to_executed():
    draft = build_terminal_paper_outcome(
        _filled_order(),
        defaults={
            "strategy_family": "orb",
            "regime": "trend",
            "final_score": 0.82,
            "simulated_pnl": 100.0,
            "slippage_cost": 7.5,
            "realized_r_multiple": 1.25,
        },
    )

    assert draft.candidate_id == "intent-clean"
    assert draft.paper_order_id == "paper-1"
    assert draft.strategy_family == "orb"
    assert draft.regime == "trend"
    assert draft.direction_family == "BUY_CALL"
    assert draft.terminal_status == "executed"
    assert draft.terminal_order_state == FILLED
    assert draft.terminal_reason == "paper_fill_complete"
    assert draft.final_score == 0.82
    assert draft.slippage_adjusted_pnl == 92.5
    assert draft.realized_r_multiple == 1.25
    assert draft.is_order_action is False
    assert draft.broker_api_called is False


def test_non_terminal_paper_order_is_rejected():
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")

    with pytest.raises(PaperTerminalOutcomeWiringError, match="paper_order_not_terminal:CREATED"):
        build_terminal_paper_outcome(order, defaults={"strategy_family": "orb"})


def test_terminal_paper_outcome_requires_strategy_family_and_direction():
    order = _filled_order()

    with pytest.raises(PaperTerminalOutcomeWiringError, match="strategy_family"):
        build_terminal_paper_outcome(order, defaults={})

    with pytest.raises(PaperTerminalOutcomeWiringError, match="direction_family"):
        build_terminal_paper_outcome(order, defaults={"strategy_family": "orb", "direction": ""})


def test_rejected_order_maps_to_saved_loss_by_default():
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")
    order = transition_paper_order(order, REJECTED, reason="paper_reject", event_id="reject-1")

    draft = build_terminal_paper_outcome(order, defaults={"strategy_family": "orb"})

    assert draft.terminal_status == "rejected-saved-loss"
    assert draft.terminal_order_state == REJECTED


def test_record_terminal_paper_outcome_appends_to_family_outcome_journal(tmp_path):
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"

    normalized = record_terminal_paper_outcome(
        _filled_order(),
        defaults={
            "strategy_family": "orb",
            "regime": "trend",
            "final_score": 0.82,
            "simulated_pnl": 100.0,
            "slippage_cost": 7.5,
            "realized_r_multiple": 1.25,
        },
        records_path=records_path,
        state_path=state_path,
    )

    records = load_family_outcome_records(path=records_path)
    state = load_family_learning_state(path=state_path)

    assert records == [normalized]
    assert normalized["terminal_status"] == "executed"
    assert normalized["strategy_family"] == "orb"
    assert normalized["direction_family"] == "bullish"
    assert normalized["final_score"] == 0.82
    assert normalized["slippage_adjusted_pnl"] == 92.5
    assert state["families"]["orb|bullish"]["sample_count"] == 1
