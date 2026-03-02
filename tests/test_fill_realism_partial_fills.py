from __future__ import annotations

from types import SimpleNamespace
import time

from core.fill_realism import FillRealismEngine, FillRequest


def _cfg(*, allow_partials: bool, fill_remainder_at_worse: bool) -> SimpleNamespace:
    return SimpleNamespace(
        FILL_REALISM_SEED=7,
        MAX_SPREAD_PCT_FOR_MARKET=0.10,
        MAX_QUOTE_AGE_MS=5_000,
        LATENCY_MS=80,
        ALLOW_PARTIAL_FILLS=allow_partials,
        DEPTH_IMPACT_K=0.10,
        VOL_IMPACT_K=0.08,
        SPREAD_MULTIPLIER_RANGE=(0.5, 0.5),
        LIMIT_ORDER_REJECT_ON_SLIP=True,
        FILL_REALISM_FILL_REMAINDER_AT_WORSE=fill_remainder_at_worse,
        FILL_REALISM_METRICS_MAX_POINTS=1000,
    )


def _req() -> FillRequest:
    return FillRequest(
        symbol="BANKNIFTY",
        side="BUY",
        qty=100,
        order_type="MARKET",
        limit_price=None,
        ts=time.time(),
        ltp=250.0,
        bid=249.0,
        ask=250.0,
        spread=1.0,
        depth={"sell": [{"quantity": 20}], "buy": [{"quantity": 20}]},
        volatility=0.4,
        latency_ms=80,
    )


def test_partial_fill_when_qty_exceeds_depth():
    engine = FillRealismEngine(_cfg(allow_partials=True, fill_remainder_at_worse=False), rng_seed=7)
    result = engine.simulate_fill(_req())
    assert result.status == "PARTIAL"
    assert float(result.filled_qty or 0.0) == 20.0
    assert len(result.partial_fills) == 1
    assert result.reject_reason == "INSUFFICIENT_LIQUIDITY"


def test_fill_remainder_when_config_enabled():
    engine = FillRealismEngine(_cfg(allow_partials=True, fill_remainder_at_worse=True), rng_seed=7)
    result = engine.simulate_fill(_req())
    assert result.status == "FILLED"
    assert float(result.filled_qty or 0.0) == 100.0
    assert len(result.partial_fills) >= 2


def test_reject_when_partials_disabled():
    engine = FillRealismEngine(_cfg(allow_partials=False, fill_remainder_at_worse=False), rng_seed=7)
    result = engine.simulate_fill(_req())
    assert result.status == "REJECTED"
    assert result.reject_reason == "INSUFFICIENT_LIQUIDITY"
