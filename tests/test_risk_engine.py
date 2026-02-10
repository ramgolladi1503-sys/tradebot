from core.risk_engine import RiskEngine
from types import SimpleNamespace

def test_size_trade_minimum_one():
    re = RiskEngine()
    trade = SimpleNamespace(entry_price=100, stop_loss=95)
    lots = re.size_trade(trade, capital=100000, lot_size=1)
    assert lots >= 1


def test_missing_daily_pnl_blocks_trading():
    re = RiskEngine()
    ok, reason = re.allow_trade(
        {
            "capital": 100000,
            "equity_high": 100000,
            "trades_today": 0,
            "open_risk_pct": 0.001,
        }
    )
    assert ok is False
    assert reason == "RISK_DATA_UNAVAILABLE:daily_pnl_pct"


def test_malformed_open_risk_pct_blocks_trading():
    re = RiskEngine()
    ok, reason = re.allow_trade(
        {
            "capital": 100000,
            "equity_high": 100000,
            "daily_pnl_pct": 0.0,
            "trades_today": 0,
            "open_risk_pct": "bad-number",
        }
    )
    assert ok is False
    assert reason == "RISK_DATA_UNAVAILABLE:open_risk_pct"


def test_invalid_stop_distance_blocks_sizing():
    re = RiskEngine()
    trade = SimpleNamespace(entry_price=100, stop_loss=100)
    lots = re.size_trade(trade, capital=100000, lot_size=1)
    assert lots == 0
    assert re.last_size_reason == "SIZING_BLOCK:INVALID_STOP_DISTANCE"
