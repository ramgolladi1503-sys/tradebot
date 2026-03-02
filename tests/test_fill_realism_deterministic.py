from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace
import time

from core.fill_realism import FillRealismEngine, FillRequest


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
        FILL_REALISM_SEED=123,
        MAX_SPREAD_PCT_FOR_MARKET=0.10,
        MAX_QUOTE_AGE_MS=5_000,
        LATENCY_MS=120,
        ALLOW_PARTIAL_FILLS=True,
        DEPTH_IMPACT_K=0.10,
        VOL_IMPACT_K=0.10,
        SPREAD_MULTIPLIER_RANGE=(0.5, 0.5),
        LIMIT_ORDER_REJECT_ON_SLIP=True,
        FILL_REALISM_FILL_REMAINDER_AT_WORSE=False,
        FILL_REALISM_METRICS_MAX_POINTS=1000,
    )


def test_fill_realism_is_deterministic_for_same_request():
    engine = FillRealismEngine(_cfg(), rng_seed=123)
    req = FillRequest(
        symbol="NIFTY",
        side="BUY",
        qty=10,
        order_type="MARKET",
        limit_price=None,
        ts=time.time(),
        ltp=100.5,
        bid=100.0,
        ask=101.0,
        spread=1.0,
        depth={"sell": [{"quantity": 200}], "buy": [{"quantity": 200}]},
        volatility=0.5,
        latency_ms=100,
    )
    r1 = engine.simulate_fill(req)
    r2 = engine.simulate_fill(req)
    d1 = asdict(r1)
    d2 = asdict(r2)
    d1.pop("ts_filled", None)
    d2.pop("ts_filled", None)
    d1_debug = dict(d1.get("debug") or {})
    d2_debug = dict(d2.get("debug") or {})
    d1_debug.pop("quote_age_ms", None)
    d2_debug.pop("quote_age_ms", None)
    d1["debug"] = d1_debug
    d2["debug"] = d2_debug
    assert d1 == d2
    assert r1.status == "FILLED"
    components = dict((r1.debug or {}).get("slippage_components") or {})
    assert components
    assert round(sum(float(v) for v in components.values()), 6) == round(float(r1.slippage or 0.0), 6)
