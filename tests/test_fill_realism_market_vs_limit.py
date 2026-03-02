from __future__ import annotations

from types import SimpleNamespace
import time

from core.fill_realism import FillRealismEngine, FillRequest


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        FILL_REALISM_SEED=99,
        MAX_SPREAD_PCT_FOR_MARKET=0.10,
        MAX_QUOTE_AGE_MS=5_000,
        LATENCY_MS=80,
        ALLOW_PARTIAL_FILLS=True,
        DEPTH_IMPACT_K=0.10,
        VOL_IMPACT_K=0.08,
        SPREAD_MULTIPLIER_RANGE=(0.5, 0.5),
        LIMIT_ORDER_REJECT_ON_SLIP=True,
        FILL_REALISM_FILL_REMAINDER_AT_WORSE=False,
        FILL_REALISM_METRICS_MAX_POINTS=1000,
    )


def test_market_buy_and_sell_use_touch_or_worse():
    engine = FillRealismEngine(_cfg(), rng_seed=99)
    now = time.time()
    buy_req = FillRequest(
        symbol="NIFTY",
        side="BUY",
        qty=5,
        order_type="MARKET",
        limit_price=None,
        ts=now,
        ltp=101.0,
        bid=100.0,
        ask=101.0,
        spread=1.0,
        depth={"sell": [{"quantity": 50}], "buy": [{"quantity": 50}]},
        volatility=0.6,
        latency_ms=100,
    )
    sell_req = FillRequest(
        symbol="NIFTY",
        side="SELL",
        qty=5,
        order_type="MARKET",
        limit_price=None,
        ts=now,
        ltp=101.0,
        bid=100.0,
        ask=101.0,
        spread=1.0,
        depth={"sell": [{"quantity": 50}], "buy": [{"quantity": 50}]},
        volatility=0.6,
        latency_ms=100,
    )

    buy = engine.simulate_fill(buy_req)
    sell = engine.simulate_fill(sell_req)
    assert buy.status == "FILLED"
    assert sell.status == "FILLED"
    assert float(buy.avg_price or 0.0) >= 101.0
    assert float(sell.avg_price or 999999.0) <= 100.0


def test_limit_buy_fill_rules():
    engine = FillRealismEngine(_cfg(), rng_seed=99)
    now = time.time()
    not_cross = FillRequest(
        symbol="NIFTY",
        side="BUY",
        qty=2,
        order_type="LIMIT",
        limit_price=99.5,
        ts=now,
        ltp=100.0,
        bid=99.0,
        ask=100.0,
        spread=1.0,
        depth={"sell": [{"quantity": 20}], "buy": [{"quantity": 20}]},
        volatility=0.0,
        latency_ms=0,
    )
    cross = FillRequest(
        symbol="NIFTY",
        side="BUY",
        qty=2,
        order_type="LIMIT",
        limit_price=100.5,
        ts=now,
        ltp=100.0,
        bid=99.0,
        ask=100.0,
        spread=1.0,
        depth={"sell": [{"quantity": 20}], "buy": [{"quantity": 20}]},
        volatility=0.0,
        latency_ms=0,
    )

    r1 = engine.simulate_fill(not_cross)
    r2 = engine.simulate_fill(cross)
    assert r1.status in {"OPEN", "REJECTED"}
    assert float(r1.filled_qty or 0.0) == 0.0
    assert r2.status == "FILLED"
    assert float(r2.filled_qty or 0.0) == 2.0
