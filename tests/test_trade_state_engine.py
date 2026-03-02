import time

import pytest

from config import config as cfg
import core.trade_state_engine as engine


@pytest.fixture(autouse=True)
def _force_non_live_mode(monkeypatch):
    # Keep state-engine tests independent of shared LIVE feed monitor state.
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)


def test_buy_activates_when_ltp_crosses_entry(monkeypatch):
    trade = {
        "symbol": "NIFTY",
        "expiry_date": "2026-03-02",
        "strike": 25350.0,
        "option_type": "PE",
        "side": "BUY",
        "entry": 104.55,
        "status": "PLANNING",
        "instrument_token": 123,
    }

    def _fake_get_last_tick(_token):
        return {"ltp": 113.8, "ts_epoch": time.time()}

    monkeypatch.setattr(engine, "get_last_tick", _fake_get_last_tick)
    updated, update = engine.process_trade_state([trade], now_ts=time.time())
    row = updated[0]
    assert row["status"] == "ACTIVE"
    assert row.get("activation_price") == 113.8
    assert update.activated == 1


def test_no_pnl_before_activation(monkeypatch):
    trade = {
        "symbol": "NIFTY",
        "expiry_date": "2026-03-02",
        "strike": 25350.0,
        "option_type": "PE",
        "side": "BUY",
        "entry": 104.55,
        "status": "PLANNING",
        "instrument_token": 123,
    }

    def _fake_get_last_tick(_token):
        return None

    monkeypatch.setattr(engine, "get_last_tick", _fake_get_last_tick)
    updated, _update = engine.process_trade_state([trade], now_ts=time.time())
    row = updated[0]
    assert row["status"] == "PLANNING"
    assert row.get("pnl_points") is None
    assert row.get("pnl_cash") is None


def test_pnl_after_activation_updates(monkeypatch):
    trade = {
        "symbol": "NIFTY",
        "expiry_date": "2026-03-02",
        "strike": 25350.0,
        "option_type": "PE",
        "side": "BUY",
        "status": "ACTIVE",
        "activation_price": 110.0,
        "instrument_token": 123,
    }

    def _fake_get_last_tick(_token):
        return {"ltp": 113.0, "ts_epoch": time.time()}

    monkeypatch.setattr(engine, "get_last_tick", _fake_get_last_tick)
    updated, _update = engine.process_trade_state([trade], now_ts=time.time())
    row = updated[0]
    assert row.get("pnl_points") == 3.0


def test_sell_activation_rule_correct(monkeypatch):
    trade = {
        "symbol": "NIFTY",
        "expiry_date": "2026-03-02",
        "strike": 25350.0,
        "option_type": "PE",
        "side": "SELL",
        "entry": 100.0,
        "status": "PLANNING",
        "instrument_token": 123,
    }

    def _fake_get_last_tick(_token):
        return {"ltp": 99.0, "ts_epoch": time.time()}

    monkeypatch.setattr(engine, "get_last_tick", _fake_get_last_tick)
    updated, _update = engine.process_trade_state([trade], now_ts=time.time())
    row = updated[0]
    assert row["status"] == "ACTIVE"


def test_dedup_trade_key_updates_last_seen_not_insert():
    base = {
        "symbol": "NIFTY",
        "expiry_date": "2026-03-02",
        "strike": 25350.0,
        "option_type": "PE",
        "side": "BUY",
        "strategy_id": "TEST",
        "timestamp": "2026-02-26T10:00:00Z",
        "last_seen": "2026-02-26T10:00:00Z",
    }
    newer = dict(base)
    newer["timestamp"] = "2026-02-26T10:05:00Z"
    newer["last_seen"] = "2026-02-26T10:05:00Z"
    rows = engine.dedupe_rows([base, newer])
    assert len(rows) == 1
    assert rows[0].get("last_seen") == "2026-02-26T10:05:00Z"
