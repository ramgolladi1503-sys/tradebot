from core.risk_engine import RiskEngine
from types import SimpleNamespace

def test_size_trade_minimum_one():
    re = RiskEngine()
    trade = SimpleNamespace(entry_price=100, stop_loss=95)
    lots = re.size_trade(trade, capital=1000, lot_size=1)
    assert lots >= 1
