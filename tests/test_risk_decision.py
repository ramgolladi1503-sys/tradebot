from __future__ import annotations

from core.risk_decision import RISK_APPROVED, RISK_BLOCKED, build_risk_decision


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
        "rank": 1,
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


def _ledger(**overrides):
    payload = {
        "risk_halt_active": False,
        "daily_realized_pnl": 0.0,
        "daily_trade_count": 0,
        "open_position_count": 0,
        "current_exposure": 0.0,
        "open_instrument_tokens": [],
        "open_tradingsymbols": [],
    }
    payload.update(overrides)
    return payload


def test_ready_intent_with_clean_limits_is_risk_approved():
    decision = build_risk_decision(_intent(), risk_limits=_limits(), ledger_snapshot=_ledger())

    assert decision.state == RISK_APPROVED
    assert decision.allowed_for_paper_order is True
    assert decision.allowed_for_live_execution is False
    assert decision.is_order_action is False
    assert decision.append is False
    assert decision.paper_intent_id == "intent123"
    assert decision.quantity == 5
    assert decision.entry_price == 100.0
    assert decision.estimated_notional == 500.0
    assert decision.risk_per_unit == 10.0
    assert decision.max_loss_amount == 50.0
    assert decision.blockers == ()


def test_blocked_intent_fails_closed():
    decision = build_risk_decision(
        _intent(state="PAPER_INTENT_BLOCKED", ready_for_risk_review=False, blockers=["CONTRACT_FALLBACK_CANDIDATE"]),
        risk_limits=_limits(),
        ledger_snapshot=_ledger(),
    )

    assert decision.state == RISK_BLOCKED
    assert decision.allowed_for_paper_order is False
    assert "CONTRACT_FALLBACK_CANDIDATE" in decision.blockers
    assert "PAPER_INTENT_NOT_READY" in decision.blockers
    assert "PAPER_INTENT_NOT_READY_FOR_RISK_REVIEW" in decision.blockers


def test_missing_risk_limits_fail_closed():
    decision = build_risk_decision(_intent(), risk_limits={}, ledger_snapshot=_ledger())

    assert decision.state == RISK_BLOCKED
    assert decision.quantity == 0
    assert "MAX_TRADE_NOTIONAL_MISSING" in decision.blockers
    assert "MAX_TOTAL_EXPOSURE_MISSING" in decision.blockers
    assert "MAX_DAILY_LOSS_MISSING" in decision.blockers
    assert "MAX_DAILY_TRADES_MISSING" in decision.blockers
    assert "MAX_OPEN_POSITIONS_MISSING" in decision.blockers
    assert "MAX_CONTRACTS_PER_TRADE_MISSING" in decision.blockers
    assert "AVAILABLE_CASH_MISSING" in decision.blockers
    assert "RISK_SIZE_ZERO" in decision.blockers


def test_zero_size_blocks_when_notional_too_small():
    decision = build_risk_decision(
        _intent(ask=100.0),
        risk_limits=_limits(max_trade_notional=50.0),
        ledger_snapshot=_ledger(),
    )

    assert decision.state == RISK_BLOCKED
    assert decision.quantity == 0
    assert "RISK_SIZE_BELOW_MIN_CONTRACTS" in decision.blockers
    assert "RISK_SIZE_ZERO" in decision.blockers


def test_risk_halt_blocks():
    decision = build_risk_decision(_intent(), risk_limits=_limits(), ledger_snapshot=_ledger(risk_halt_active=True))

    assert decision.state == RISK_BLOCKED
    assert "RISK_HALT_ACTIVE" in decision.blockers


def test_daily_loss_limit_blocks():
    decision = build_risk_decision(
        _intent(),
        risk_limits=_limits(max_daily_loss=1000.0),
        ledger_snapshot=_ledger(daily_realized_pnl=-1000.0),
    )

    assert decision.state == RISK_BLOCKED
    assert "DAILY_LOSS_LIMIT_REACHED" in decision.blockers


def test_daily_trade_limit_blocks():
    decision = build_risk_decision(
        _intent(),
        risk_limits=_limits(max_daily_trades=2),
        ledger_snapshot=_ledger(daily_trade_count=2),
    )

    assert decision.state == RISK_BLOCKED
    assert "DAILY_TRADE_LIMIT_REACHED" in decision.blockers


def test_max_open_positions_blocks():
    decision = build_risk_decision(
        _intent(),
        risk_limits=_limits(max_open_positions=1),
        ledger_snapshot=_ledger(open_position_count=1),
    )

    assert decision.state == RISK_BLOCKED
    assert "MAX_OPEN_POSITIONS_REACHED" in decision.blockers


def test_duplicate_contract_blocks():
    decision = build_risk_decision(
        _intent(instrument_token=12345, tradingsymbol="NIFTY26MAY22500CE"),
        risk_limits=_limits(),
        ledger_snapshot=_ledger(open_instrument_tokens=[12345]),
    )

    assert decision.state == RISK_BLOCKED
    assert "DUPLICATE_OPEN_CONTRACT" in decision.blockers


def test_total_exposure_exceeded_blocks():
    decision = build_risk_decision(
        _intent(ask=100.0),
        risk_limits=_limits(max_total_exposure=1000.0, max_trade_notional=500.0),
        ledger_snapshot=_ledger(current_exposure=700.0),
    )

    assert decision.state == RISK_BLOCKED
    assert "MAX_TOTAL_EXPOSURE_EXCEEDED" in decision.blockers


def test_insufficient_cash_blocks():
    decision = build_risk_decision(
        _intent(ask=100.0),
        risk_limits=_limits(max_trade_notional=500.0, available_cash=400.0),
        ledger_snapshot=_ledger(),
    )

    assert decision.state == RISK_BLOCKED
    assert "INSUFFICIENT_AVAILABLE_CASH" in decision.blockers


def test_missing_entry_price_blocks():
    decision = build_risk_decision(_intent(ask=None), risk_limits=_limits(), ledger_snapshot=_ledger())

    assert decision.state == RISK_BLOCKED
    assert decision.quantity == 0
    assert "ENTRY_PRICE_MISSING" in decision.blockers
    assert "RISK_SIZE_UNAVAILABLE" in decision.blockers
    assert "RISK_SIZE_ZERO" in decision.blockers


def test_to_dict_is_json_friendly_and_stable():
    decision = build_risk_decision(_intent(), risk_limits=_limits(), ledger_snapshot=_ledger())
    payload = decision.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == RISK_APPROVED
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["allowed_for_paper_order"] is True
    assert payload["allowed_for_live_execution"] is False
    assert payload["quantity"] == 5
    assert payload["blockers"] == []
    assert payload["metadata"]["risk_decision"] == "risk_decision_v1"
