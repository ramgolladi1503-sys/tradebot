# Migration note:
# Added unit tests for trailing stop behavior (buy/sell + exit triggers).

from core.trailing import update_trailing, check_exit


def test_trailing_buy_moves_stop_up():
    trade = {
        "side": "BUY",
        "fill_price": 100.0,
        "original_stop": 90.0,
        "stop": 90.0,
        "trail_offset": 5.0,
        "mfe_price": 100.0,
        "trail_enabled": True,
    }
    updated = update_trailing(trade, ltp=110.0)
    assert updated["mfe_price"] == 110.0
    assert updated["trail_stop"] == 105.0
    assert updated["stop"] == 105.0


def test_trailing_sell_moves_stop_down():
    trade = {
        "side": "SELL",
        "fill_price": 100.0,
        "original_stop": 110.0,
        "stop": 110.0,
        "trail_offset": 5.0,
        "mfe_price": 100.0,
        "trail_enabled": True,
    }
    updated = update_trailing(trade, ltp=90.0)
    assert updated["mfe_price"] == 90.0
    assert updated["trail_stop"] == 95.0
    assert updated["stop"] == 95.0


def test_exit_trigger_buy():
    trade = {
        "side": "BUY",
        "stop": 105.0,
    }
    should_exit, reason = check_exit(trade, ltp=104.0)
    assert should_exit is True
    assert reason == "TRAIL_STOP"


def test_exit_trigger_sell():
    trade = {
        "side": "SELL",
        "stop": 95.0,
    }
    should_exit, reason = check_exit(trade, ltp=96.0)
    assert should_exit is True
    assert reason == "TRAIL_STOP"
