from __future__ import annotations

from types import SimpleNamespace
import time

from core.fill_realism import FillRealismEngine, FillRequest


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        FILL_REALISM_SEED=21,
        MAX_SPREAD_PCT_FOR_MARKET=0.005,
        MAX_QUOTE_AGE_MS=1_000,
        LATENCY_MS=200,
        ALLOW_PARTIAL_FILLS=True,
        DEPTH_IMPACT_K=0.20,
        VOL_IMPACT_K=0.20,
        SPREAD_MULTIPLIER_RANGE=(0.5, 0.5),
        LIMIT_ORDER_REJECT_ON_SLIP=True,
        FILL_REALISM_FILL_REMAINDER_AT_WORSE=False,
        FILL_REALISM_METRICS_MAX_POINTS=1000,
    )


def test_stale_quote_reject():
    engine = FillRealismEngine(_cfg(), rng_seed=21)
    req = FillRequest(
        symbol="NIFTY",
        side="BUY",
        qty=1,
        order_type="MARKET",
        limit_price=None,
        ts=time.time() - 20,
        ltp=100.0,
        bid=99.5,
        ask=100.5,
        spread=1.0,
        depth={"sell": [{"quantity": 10}]},
        volatility=0.2,
        latency_ms=120,
    )
    out = engine.simulate_fill(req)
    assert out.status == "REJECTED"
    assert out.reject_reason == "STALE_QUOTE"


def test_wide_spread_market_reject():
    engine = FillRealismEngine(_cfg(), rng_seed=21)
    req = FillRequest(
        symbol="NIFTY",
        side="BUY",
        qty=1,
        order_type="MARKET",
        limit_price=None,
        ts=time.time(),
        ltp=105.0,
        bid=100.0,
        ask=110.0,
        spread=10.0,
        depth={"sell": [{"quantity": 10}]},
        volatility=0.2,
        latency_ms=120,
    )
    out = engine.simulate_fill(req)
    assert out.status == "REJECTED"
    assert out.reject_reason == "SPREAD_TOO_WIDE"


def test_limit_slip_reject():
    engine = FillRealismEngine(_cfg(), rng_seed=21)
    req = FillRequest(
        symbol="BANKNIFTY",
        side="BUY",
        qty=500,
        order_type="LIMIT",
        limit_price=100.2,
        ts=time.time(),
        ltp=100.1,
        bid=100.0,
        ask=100.2,
        spread=0.2,
        depth={"sell": [{"quantity": 5}], "buy": [{"quantity": 5}]},
        volatility=8.0,
        latency_ms=1500,
    )
    out = engine.simulate_fill(req)
    assert out.status == "REJECTED"
    assert out.reject_reason == "LIMIT_SLIPPED"
