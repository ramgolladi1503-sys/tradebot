# Migration note:
# Added tests for deterministic activation rules used by suggested trades.

from core.trade_activation import should_activate, activate_trade


def test_should_activate_buy_breakout():
    assert should_activate("BUY", "BREAKOUT", entry=100, ltp=100)
    assert should_activate("BUY", "BREAKOUT", entry=100, ltp=101)
    assert not should_activate("BUY", "BREAKOUT", entry=100, ltp=99)


def test_activation_sets_fill_and_status():
    row = {"status": "PLANNING", "entry": 100.0}
    updated = activate_trade(row, ltp=101.0, ts="2026-02-25T09:30:00+05:30")
    assert updated["status"] == "ACTIVE"
    assert updated["activated_ts"] == "2026-02-25T09:30:00+05:30"
    assert updated["fill_price"] == 101.0
    assert updated["ltp_at_activation"] == 101.0


def test_should_activate_sell_breakout():
    assert should_activate("SELL", "BREAKOUT", entry=100, ltp=100)
    assert not should_activate("SELL", "BREAKOUT", entry=100, ltp=101)
    assert should_activate("SELL", "BREAKOUT", entry=100, ltp=99)
