from datetime import datetime
from core.paper_fill_simulator import PaperFillSimulator
from core.trade_schema import Trade


def _trade(side="BUY"):
    return Trade(
        trade_id="T1",
        timestamp=datetime.now(),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=None,
        strike=25000,
        expiry="",
        side=side,
        entry_price=100.0,
        stop_loss=90.0,
        target=120.0,
        qty=1,
        capital_at_risk=10.0,
        expected_slippage=0.0,
        confidence=0.8,
        strategy="TEST",
        regime="TREND",
    )


def test_buy_fill_when_limit_crosses():
    sim = PaperFillSimulator(timeout_sec=0.05, poll_sec=0)
    trade = _trade("BUY")
    snapshots = [
        {"bid": 98, "ask": 102, "ts": datetime.now().timestamp()},
        {"bid": 99, "ask": 100, "ts": datetime.now().timestamp()},
    ]
    filled, price, report = sim.simulate(trade, limit_price=100, snapshot_stream=snapshots)
    assert filled is True
    assert price == 100
    assert report["reason_if_aborted"] is None


def test_sell_fill_when_limit_crosses():
    sim = PaperFillSimulator(timeout_sec=0.05, poll_sec=0)
    trade = _trade("SELL")
    snapshots = [
        {"bid": 98, "ask": 101, "ts": datetime.now().timestamp()},
        {"bid": 101, "ask": 103, "ts": datetime.now().timestamp()},
    ]
    filled, price, report = sim.simulate(trade, limit_price=100, snapshot_stream=snapshots)
    assert filled is True
    assert price == 101
    assert report["reason_if_aborted"] is None


def test_timeout_when_never_crosses():
    sim = PaperFillSimulator(timeout_sec=0.01, poll_sec=0)
    trade = _trade("BUY")
    snapshots = [
        {"bid": 98, "ask": 105, "ts": datetime.now().timestamp()},
        {"bid": 98, "ask": 104, "ts": datetime.now().timestamp()},
    ]
    filled, price, report = sim.simulate(trade, limit_price=100, snapshot_stream=snapshots)
    assert filled is False
    assert report["reason_if_aborted"] in ("timeout", "no_quote")
