from __future__ import annotations

from pathlib import Path

from core.cost_slippage_model import (
    BLOCKED,
    DEGRADED,
    INVALID_RISK_PER_UNIT,
    MISSING_BID_ASK,
    READY,
    build_cost_slippage_model,
)


def _model(**overrides: object) -> dict[str, object]:
    payload = {
        "entry_price": 100.0,
        "exit_price": 110.0,
        "bid": 99.5,
        "ask": 100.5,
        "best_bid": 99.4,
        "best_ask": 100.6,
        "spread": 1.0,
        "spread_pct": 1.0,
        "lot_size": 50.0,
        "quantity": 2.0,
        "risk_per_unit": 10.0,
        "brokerage": 1.0,
        "taxes": 0.5,
        "slippage_ticks": 2.0,
        "tick_size": 0.05,
        "side": "BUY",
    }
    payload.update(overrides)
    return payload


def test_normal_tight_spread_produces_small_cost() -> None:
    result = build_cost_slippage_model(_model(spread=0.25, spread_pct=0.25, slippage_ticks=0.5))

    assert result.cost_model_status == READY
    assert result.estimated_cost_abs > 0
    assert result.estimated_cost_r is not None
    assert result.estimated_cost_r < 20
    assert result.spread_cost_abs < result.estimated_cost_abs


def test_wide_spread_produces_larger_cost() -> None:
    tight = build_cost_slippage_model(_model(spread=0.25, spread_pct=0.25, slippage_ticks=0.5))
    wide = build_cost_slippage_model(_model(spread=2.5, spread_pct=2.5, slippage_ticks=0.5))

    assert wide.cost_model_status == READY
    assert wide.spread_cost_abs > tight.spread_cost_abs
    assert wide.estimated_cost_abs > tight.estimated_cost_abs
    assert wide.estimated_cost_r is not None
    assert wide.estimated_cost_r > tight.estimated_cost_r


def test_missing_bid_ask_produces_degraded_status_without_crash() -> None:
    result = build_cost_slippage_model(_model(bid=None, ask=None))

    assert result.cost_model_status == DEGRADED
    assert MISSING_BID_ASK in result.cost_model_blockers
    assert result.cost_model_warnings
    assert result.estimated_cost_abs >= 0
    assert result.estimated_cost_r is not None


def test_zero_or_invalid_risk_returns_safe_blocker() -> None:
    result = build_cost_slippage_model(_model(risk_per_unit=0.0))

    assert result.cost_model_status == BLOCKED
    assert INVALID_RISK_PER_UNIT in result.cost_model_blockers
    assert result.estimated_cost_r is None


def test_high_slippage_and_spread_can_make_cost_material() -> None:
    result = build_cost_slippage_model(_model(spread=3.0, spread_pct=3.0, slippage_ticks=8.0, tick_size=0.25))

    assert result.cost_model_status == READY
    assert result.estimated_cost_abs > 0
    assert result.estimated_cost_r is not None
    assert result.estimated_cost_r > 0
    assert result.effective_entry is not None
    assert result.effective_exit is not None


def test_no_broker_or_order_imports() -> None:
    source = Path(build_cost_slippage_model.__code__.co_filename).read_text(encoding="utf-8")
    forbidden = ("broker", "order_router", "live_trade", "kite", "upstox")
    assert not any(f"from core.{name}" in source or f"import {name}" in source for name in forbidden)
