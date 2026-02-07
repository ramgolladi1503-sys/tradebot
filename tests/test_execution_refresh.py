import time

from core.execution_engine import ExecutionEngine


class DummyTrade:
    def __init__(self, side="BUY"):
        self.side = side


def test_fill_only_on_later_quote():
    engine = ExecutionEngine()
    trade = DummyTrade(side="BUY")

    quotes = [
        {"bid": 100, "ask": 102, "ts": time.time()},
        {"bid": 100, "ask": 99, "ts": time.time()},
    ]
    idx = {"i": 0}

    def quote_fn():
        i = idx["i"]
        if i >= len(quotes):
            return quotes[-1]
        q = quotes[i]
        idx["i"] += 1
        return q

    filled, price, report = engine.simulate_limit_fill(
        trade=trade,
        limit_price=100,
        quote_fn=quote_fn,
        timeout_sec=1.0,
        poll_sec=0.01,
        max_chase_pct=0.0,
        spread_widen_pct=0.0,
        max_spread_pct=0.5,
        max_quote_age_sec=10.0,
        fill_prob=1.0,
    )
    assert filled is True
    assert price == 99
    assert report.get("attempts") and len(report.get("attempts")) >= 2


def test_abort_on_stale_quote():
    engine = ExecutionEngine()
    trade = DummyTrade(side="BUY")
    stale_ts = time.time() - 10

    def quote_fn():
        return {"bid": 100, "ask": 101, "ts": stale_ts}

    filled, price, report = engine.simulate_limit_fill(
        trade=trade,
        limit_price=101,
        quote_fn=quote_fn,
        timeout_sec=0.2,
        poll_sec=0.01,
        max_chase_pct=0.0,
        spread_widen_pct=0.0,
        max_spread_pct=0.5,
        max_quote_age_sec=1.0,
        fill_prob=1.0,
    )
    assert filled is False
    assert report.get("reason_if_aborted") == "stale_quote"
