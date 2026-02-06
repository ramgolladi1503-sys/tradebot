from core.execution_engine import ExecutionEngine
from core.trade_schema import Trade
from datetime import datetime


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


def _snapshot_seq(quotes):
    idx = {"i": 0}
    def _fn():
        i = idx["i"]
        if i >= len(quotes):
            return quotes[-1]
        idx["i"] += 1
        return quotes[i]
    return _fn


def test_buy_fills_only_after_ask_below_limit():
    eng = ExecutionEngine()
    trade = _trade("BUY")
    quotes = [
        {"bid": 98, "ask": 101},
        {"bid": 99, "ask": 100},
        {"bid": 100, "ask": 99},
    ]
    filled, price, report = eng.simulate_limit_fill(
        trade,
        limit_price=99.5,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0,
        max_chase_pct=0,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=1.0,
    )
    assert filled is True
    assert price == 99
    assert report["reason_if_aborted"] is None


def test_sell_fills_only_after_bid_above_limit():
    eng = ExecutionEngine()
    trade = _trade("SELL")
    quotes = [
        {"bid": 99, "ask": 101},
        {"bid": 100, "ask": 102},
        {"bid": 101, "ask": 103},
    ]
    filled, price, report = eng.simulate_limit_fill(
        trade,
        limit_price=100.5,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0,
        max_chase_pct=0,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=1.0,
    )
    assert filled is True
    assert price == 101
    assert report["reason_if_aborted"] is None


def test_timeout_abort_when_never_crosses():
    eng = ExecutionEngine()
    trade = _trade("BUY")
    quotes = [
        {"bid": 98, "ask": 105},
        {"bid": 98, "ask": 104},
        {"bid": 98, "ask": 103},
    ]
    filled, price, report = eng.simulate_limit_fill(
        trade,
        limit_price=99,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.01,
        poll_sec=0,
        max_chase_pct=0,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=1.0,
    )
    assert filled is False
    assert report["reason_if_aborted"] in ("timeout", "no_quote")


def test_spread_widen_abort():
    eng = ExecutionEngine()
    trade = _trade("BUY")
    quotes = [
        {"bid": 100, "ask": 100.5},
        {"bid": 95, "ask": 110},
    ]
    filled, price, report = eng.simulate_limit_fill(
        trade,
        limit_price=101,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0,
        max_chase_pct=0,
        spread_widen_pct=0.5,
        max_spread_pct=1.0,
        fill_prob=1.0,
    )
    assert filled is False
    assert report["reason_if_aborted"] == "spread_widened"


def test_max_chase_abort():
    eng = ExecutionEngine()
    trade = _trade("BUY")
    quotes = [
        {"bid": 100, "ask": 101},
        {"bid": 100, "ask": 105},
    ]
    filled, price, report = eng.simulate_limit_fill(
        trade,
        limit_price=101,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0,
        max_chase_pct=0.01,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=1.0,
    )
    assert filled is False
    assert report["reason_if_aborted"] == "max_chase_exceeded"


def test_fill_probability_gate_blocks_fill():
    eng = ExecutionEngine()
    trade = _trade("BUY")
    quotes = [
        {"bid": 99, "ask": 100},
        {"bid": 100, "ask": 99},
    ]
    filled, price, report = eng.simulate_limit_fill(
        trade,
        limit_price=100,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0,
        max_chase_pct=0,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=0.0,
    )
    assert filled is False
    assert report["reason_if_aborted"] in ("timeout", "no_quote")
