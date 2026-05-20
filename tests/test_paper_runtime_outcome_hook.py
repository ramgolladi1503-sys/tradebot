from __future__ import annotations

from core.offline_family_learning import load_family_learning_state, load_family_outcome_records
from core.paper_order_state_machine import FILLED, SUBMITTED, create_paper_order_record
from core.paper_runtime_outcome_hook import transition_paper_order_and_record_outcome


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


def test_non_terminal_transition_does_not_write_journal(tmp_path):
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")

    updated, result = transition_paper_order_and_record_outcome(
        order,
        SUBMITTED,
        reason="paper_submit",
        event_id="submit-1",
        outcome_defaults={"strategy_family": "orb"},
        records_path=records_path,
        state_path=state_path,
    )

    assert updated.state == SUBMITTED
    assert result.terminal is False
    assert result.outcome_recorded is False
    assert result.journal_record is None
    assert result.warnings == ("paper_order_not_terminal_no_journal_record",)
    assert not records_path.exists()


def test_terminal_transition_records_journal_outcome(tmp_path):
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")
    order, _ = transition_paper_order_and_record_outcome(
        order,
        SUBMITTED,
        reason="paper_submit",
        event_id="submit-1",
        outcome_defaults={"strategy_family": "orb"},
        records_path=records_path,
        state_path=state_path,
    )

    updated, result = transition_paper_order_and_record_outcome(
        order,
        FILLED,
        reason="paper_fill_complete",
        event_id="fill-1",
        filled_quantity_delta=5,
        outcome_defaults={
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

    assert updated.state == FILLED
    assert result.terminal is True
    assert result.outcome_recorded is True
    assert result.journal_record == records[0]
    assert result.journal_record["terminal_status"] == "executed"
    assert result.journal_record["strategy_family"] == "orb"
    assert result.journal_record["direction_family"] == "bullish"
    assert result.journal_record["slippage_adjusted_pnl"] == 92.5
    assert state["families"]["orb|bullish"]["sample_count"] == 1
    assert result.is_order_action is False
    assert result.broker_api_called is False


def test_hook_result_is_json_friendly_for_runtime_evidence(tmp_path):
    records_path = tmp_path / "family_outcomes.jsonl"
    state_path = tmp_path / "family_learning_state.json"
    order = create_paper_order_record(_decision(), paper_order_id="paper-1")

    _, result = transition_paper_order_and_record_outcome(
        order,
        SUBMITTED,
        reason="paper_submit",
        event_id="submit-1",
        outcome_defaults={"strategy_family": "orb"},
        records_path=records_path,
        state_path=state_path,
    )
    payload = result.to_dict()

    assert payload["schema_version"] == 1
    assert payload["paper_order_id"] == "paper-1"
    assert payload["from_state"] == "CREATED"
    assert payload["to_state"] == SUBMITTED
    assert payload["outcome_recorded"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["state_machine_preserved_pure"] is True
