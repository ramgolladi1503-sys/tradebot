from __future__ import annotations

import pytest

from core.paper_risk_ledger import (
    POSITION_CLOSED,
    POSITION_OPENED,
    RISK_HALT_ACTIVATED,
    RISK_HALT_CLEARED,
    PaperRiskLedgerError,
    empty_paper_risk_ledger_snapshot,
    reduce_paper_risk_ledger_events,
)
from core.risk_decision import RISK_BLOCKED, build_risk_decision


def _open_event(**overrides):
    payload = {
        "event_id": "open-1",
        "event_type": POSITION_OPENED,
        "paper_order_id": "paper-1",
        "paper_intent_id": "intent-1",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "quantity": 5,
        "entry_price": 100.0,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
    }
    payload.update(overrides)
    return payload


def _close_event(**overrides):
    payload = {
        "event_id": "close-1",
        "event_type": POSITION_CLOSED,
        "paper_order_id": "paper-1",
        "quantity": 5,
        "exit_price": 112.5,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
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
        "paper_intent_id": "intent-2",
        "ready_for_risk_review": True,
        "allowed_for_paper_order": False,
        "allowed_for_live_execution": False,
        "selected_strategy_id": "call_high",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY22500CE",
        "ask": 100.0,
        "bid": 99.0,
        "ltp": 99.5,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _limits(**overrides):
    payload = {
        "max_trade_notional": 500.0,
        "max_total_exposure": 2000.0,
        "max_daily_loss": 1000.0,
        "max_daily_trades": 5,
        "max_open_positions": 2,
        "max_contracts_per_trade": 5,
        "min_contracts_per_trade": 1,
        "risk_per_trade_pct": 10.0,
        "available_cash": 2000.0,
    }
    payload.update(overrides)
    return payload


def test_empty_snapshot_is_safe_for_risk_decision():
    snapshot = empty_paper_risk_ledger_snapshot()
    payload = snapshot.to_dict()

    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["risk_halt_active"] is False
    assert payload["daily_realized_pnl"] == 0.0
    assert payload["daily_trade_count"] == 0
    assert payload["open_position_count"] == 0
    assert payload["current_exposure"] == 0.0
    assert payload["open_instrument_tokens"] == []
    assert payload["open_tradingsymbols"] == []


def test_open_position_updates_exposure_and_duplicate_keys_for_risk_gate():
    snapshot = reduce_paper_risk_ledger_events([_open_event()])

    assert snapshot.daily_trade_count == 1
    assert snapshot.open_position_count == 1
    assert snapshot.closed_position_count == 0
    assert snapshot.current_exposure == 500.0
    assert snapshot.open_instrument_tokens == (12345,)
    assert snapshot.open_tradingsymbols == ("NIFTY26MAY22500CE",)
    assert snapshot.processed_event_ids == ("open-1",)
    assert snapshot.open_positions[0].paper_order_id == "paper-1"
    assert snapshot.open_positions[0].entry_notional == 500.0


def test_ledger_snapshot_blocks_duplicate_contract_in_existing_risk_decision():
    snapshot = reduce_paper_risk_ledger_events([_open_event()])
    decision = build_risk_decision(_intent(), risk_limits=_limits(), ledger_snapshot=snapshot.to_dict())

    assert decision.state == RISK_BLOCKED
    assert "DUPLICATE_OPEN_CONTRACT" in decision.blockers


def test_ledger_snapshot_blocks_trade_limit_in_existing_risk_decision():
    snapshot = reduce_paper_risk_ledger_events([_open_event()])
    decision = build_risk_decision(
        _intent(instrument_token=54321, tradingsymbol="NIFTY26MAY22600CE"),
        risk_limits=_limits(max_daily_trades=1),
        ledger_snapshot=snapshot.to_dict(),
    )

    assert decision.state == RISK_BLOCKED
    assert "DAILY_TRADE_LIMIT_REACHED" in decision.blockers


def test_close_position_removes_exposure_and_calculates_realized_pnl():
    snapshot = reduce_paper_risk_ledger_events([_open_event(), _close_event()])

    assert snapshot.daily_trade_count == 1
    assert snapshot.open_position_count == 0
    assert snapshot.closed_position_count == 1
    assert snapshot.current_exposure == 0.0
    assert snapshot.daily_realized_pnl == 62.5
    assert snapshot.open_instrument_tokens == ()
    assert snapshot.open_tradingsymbols == ()
    assert snapshot.processed_event_ids == ("open-1", "close-1")


def test_close_position_can_use_explicit_realized_pnl_from_fill_accounting():
    snapshot = reduce_paper_risk_ledger_events(
        [
            _open_event(),
            _close_event(exit_price=None, realized_pnl=-25.75),
        ]
    )

    assert snapshot.daily_realized_pnl == -25.75
    assert snapshot.open_position_count == 0


def test_risk_halt_events_toggle_snapshot_without_order_action():
    snapshot = reduce_paper_risk_ledger_events(
        [
            {"event_id": "halt-1", "event_type": RISK_HALT_ACTIVATED},
            {"event_id": "halt-2", "event_type": RISK_HALT_CLEARED},
            {"event_id": "halt-3", "event_type": RISK_HALT_ACTIVATED},
        ]
    )

    assert snapshot.risk_halt_active is True
    assert snapshot.daily_trade_count == 0
    assert snapshot.open_position_count == 0
    assert snapshot.processed_event_ids == ("halt-1", "halt-2", "halt-3")


def test_duplicate_event_id_rejected_fail_closed():
    with pytest.raises(PaperRiskLedgerError) as exc_info:
        reduce_paper_risk_ledger_events([_open_event(), _close_event(event_id="open-1")])

    assert "duplicate_ledger_event_id:open-1" in str(exc_info.value)


def test_duplicate_open_instrument_rejected_fail_closed():
    with pytest.raises(PaperRiskLedgerError) as exc_info:
        reduce_paper_risk_ledger_events(
            [
                _open_event(),
                _open_event(
                    event_id="open-2",
                    paper_order_id="paper-2",
                    paper_intent_id="intent-2",
                    tradingsymbol="NIFTY26MAY22500CE_DUP",
                ),
            ]
        )

    assert "duplicate_open_instrument_token:12345" in str(exc_info.value)


def test_duplicate_open_tradingsymbol_rejected_fail_closed():
    with pytest.raises(PaperRiskLedgerError) as exc_info:
        reduce_paper_risk_ledger_events(
            [
                _open_event(),
                _open_event(
                    event_id="open-2",
                    paper_order_id="paper-2",
                    paper_intent_id="intent-2",
                    instrument_token=54321,
                ),
            ]
        )

    assert "duplicate_open_tradingsymbol:NIFTY26MAY22500CE" in str(exc_info.value)


def test_close_unknown_position_rejected_fail_closed():
    with pytest.raises(PaperRiskLedgerError) as exc_info:
        reduce_paper_risk_ledger_events([_close_event()])

    assert "position_close_unknown_paper_order:paper-1" in str(exc_info.value)


def test_partial_close_rejected_until_pr_explicitly_scopes_partial_exits():
    with pytest.raises(PaperRiskLedgerError) as exc_info:
        reduce_paper_risk_ledger_events([_open_event(), _close_event(quantity=2)])

    assert "position_close_requires_full_quantity" in str(exc_info.value)


def test_invalid_open_event_rejected_with_specific_blockers():
    with pytest.raises(PaperRiskLedgerError) as exc_info:
        reduce_paper_risk_ledger_events(
            [
                _open_event(
                    paper_order_id="",
                    instrument_token=0,
                    quantity=0,
                    entry_price=0.0,
                )
            ]
        )

    message = str(exc_info.value)
    assert "position_open_event_invalid" in message
    assert "PAPER_ORDER_ID_MISSING" in message
    assert "INSTRUMENT_TOKEN_MISSING" in message
    assert "QUANTITY_MISSING" in message
    assert "ENTRY_PRICE_MISSING" in message


def test_order_action_flags_rejected_before_ledger_mutation():
    for flag in ["broker_order_action", "live_order_action", "is_order_action", "append"]:
        with pytest.raises(PaperRiskLedgerError) as exc_info:
            reduce_paper_risk_ledger_events([_open_event(**{flag: True})])
        assert "rejected" in str(exc_info.value)


def test_to_dict_is_json_friendly_and_stable():
    snapshot = reduce_paper_risk_ledger_events([_open_event()])
    payload = snapshot.to_dict()

    assert payload["schema_version"] == 1
    assert payload["open_positions"][0]["paper_order_id"] == "paper-1"
    assert payload["open_instrument_tokens"] == [12345]
    assert payload["open_tradingsymbols"] == ["NIFTY26MAY22500CE"]
    assert payload["processed_event_ids"] == ["open-1"]
    assert payload["metadata"]["ledger"] == "paper_risk_ledger_v1"
    assert payload["metadata"]["scope"] == "event_reducer_no_broker_calls_no_order_creation_no_persistence_no_runtime_wiring"
