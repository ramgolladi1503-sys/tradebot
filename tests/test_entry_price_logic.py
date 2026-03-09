from __future__ import annotations

from core.entry_semantics import enforce_entry_contract, resolve_entry_price
from core.trade_state_machine import TradeStateV1, transition_trade_state


def test_approved_state_derives_expected_entry_from_snapshot_ltp() -> None:
    trade = {
        "trade_id": "t-approved-ltp",
        "trade_state_v1": "CANDIDATE",
        "snapshot_id": "snap-ltp-1",
        "snapshot": {"option_quote": {"ltp": 123.45, "bid": 123.2, "ask": 123.8}},
    }

    out = transition_trade_state(trade, TradeStateV1.APPROVED)

    assert out["trade_state_v1"] == "APPROVED"
    assert float(out["expected_entry"]) == 123.45
    assert float(out["entry_price"]) == 123.45


def test_approved_state_derives_expected_entry_from_snapshot_mid_price() -> None:
    trade = {
        "trade_id": "t-approved-mid",
        "trade_state_v1": "CANDIDATE",
        "snapshot_id": "snap-mid-1",
        "snapshot": {"option_quote": {"ltp": None, "bid": 99.0, "ask": 101.0}},
    }

    out = transition_trade_state(trade, TradeStateV1.APPROVED)

    assert out["trade_state_v1"] == "APPROVED"
    assert float(out["expected_entry"]) == 100.0
    assert float(out["entry_price"]) == 100.0


def test_entry_price_live_uses_fill_entry_if_available() -> None:
    row = {"expected_entry": 200.0, "fill_entry": 205.5}
    assert float(resolve_entry_price(row, mode="LIVE")) == 205.5


def test_entry_price_paper_uses_expected_entry() -> None:
    row = {"expected_entry": 200.0, "fill_entry": 205.5}
    assert float(resolve_entry_price(row, mode="PAPER")) == 200.0


def test_enforce_entry_contract_sets_entry_price_for_filled_live() -> None:
    row = {
        "trade_id": "t-filled",
        "status": "FILLED",
        "snapshot_id": "snap-fill-1",
        "expected_entry": 150.0,
        "fill_price": 151.2,
        "execution_mode": "LIVE",
    }

    out = enforce_entry_contract(row, stage="unit_test", mode="LIVE")

    assert float(out["expected_entry"]) == 150.0
    assert float(out["fill_entry"]) == 151.2
    assert float(out["entry_price"]) == 151.2


def test_enforce_entry_contract_sets_entry_price_for_approved_paper() -> None:
    row = {
        "trade_id": "t-approved-paper",
        "status": "APPROVED",
        "snapshot_id": "snap-paper-1",
        "snapshot": {"option_quote": {"ltp": 88.4, "bid": 88.1, "ask": 88.7}},
        "execution_mode": "PAPER",
    }

    out = enforce_entry_contract(row, stage="unit_test", mode="PAPER")

    assert float(out["expected_entry"]) == 88.4
    assert float(out["entry_price"]) == 88.4
    assert out.get("fill_entry") is None
