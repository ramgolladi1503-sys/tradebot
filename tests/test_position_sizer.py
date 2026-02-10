from types import SimpleNamespace

from core.position_sizer import PositionSizer
from core.risk_engine import RiskEngine


def test_position_sizer_formula_qty():
    sizer = PositionSizer()
    sizer.max_slippage_bps_assumed = 0.0
    sizer.min_qty = 1
    sizer.max_qty = 10_000
    risk_budget = 1000.0
    stop_distance_rupees = 50.0
    result = sizer.size_from_budget(risk_budget, stop_distance_rupees)
    assert result.reason == "OK"
    assert result.qty == 20


def test_event_regime_reduces_qty_vs_trend():
    re = RiskEngine()
    trend_trade = SimpleNamespace(
        entry_price=120.0,
        stop_loss=100.0,
        stop_distance=20.0,
        regime="TREND",
        day_type="UNKNOWN",
        size_mult=1.0,
    )
    event_trade = SimpleNamespace(
        entry_price=120.0,
        stop_loss=100.0,
        stop_distance=20.0,
        regime="EVENT",
        day_type="UNKNOWN",
        size_mult=1.0,
    )
    trend_qty = re.size_trade(trend_trade, capital=100000, lot_size=1)
    event_qty = re.size_trade(event_trade, capital=100000, lot_size=1)
    assert trend_qty > 0
    assert event_qty > 0
    assert event_qty < trend_qty
