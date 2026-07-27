from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from core.movement_contract import StrategyContext
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1 import canonical_adapter


def _context() -> StrategyContext:
    return StrategyContext(
        symbol="NIFTY",
        spot_ltp=25000.0,
        open_price=24950.0,
        vwap=24980.0,
        vwap_slope=2.0,
        day_high=25020.0,
        day_low=24920.0,
        orb_high=25000.0,
        orb_low=24940.0,
        atr=30.0,
        atr_short=25.0,
        atr_long=35.0,
        range_width_pct=0.004,
        volume_z=0.0,
        quote_source="kite_historical_underlying_5m",
    )


def test_resolve_callable_returns_canonical_owner() -> None:
    fn, module_name, callable_name = canonical_adapter.resolve_callable("OPENING_RANGE_RETEST")
    assert module_name == "strategies.movement.opening_range_breakout"
    assert callable_name == "generate_opening_range_retest_candidates"
    assert fn.__module__ == module_name
    assert fn.__name__ == callable_name


def test_invoke_canonical_calls_exact_resolved_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake(ctx, regime):
        calls.append((ctx, regime))
        return ()

    monkeypatch.setattr(canonical_adapter, "resolve_callable", lambda key: (fake, "test.module", "fake"))
    candidates, record = canonical_adapter.invoke_canonical("OPENING_DRIVE", _context())
    assert candidates == ()
    assert len(calls) == 1
    assert calls[0][0].symbol == "NIFTY"
    assert record.invocation_count == 1
    assert record.candidate_count == 0
    assert record.exception_count == 0


def test_proxy_formula_guard_rejects_old_runner_logic() -> None:
    with pytest.raises(AssertionError, match="proxy_strategy_logic_detected"):
        canonical_adapter.assert_no_proxy_strategy_logic("elif strategy == 'VWAP_RECLAIM': closes[i] > ma")


def test_completed_history_contains_no_future_rows() -> None:
    start = pd.Timestamp("2026-01-02 09:15:00", tz="Asia/Kolkata")
    rows = []
    for i in range(4):
        rows.append(
            {
                "timestamp": start + timedelta(minutes=5 * i),
                "bar_duration": timedelta(minutes=5),
                "open": 100 + i,
                "high": 101 + i,
                "low": 99 + i,
                "close": 100.5 + i,
                "volume": 1000,
            }
        )
    history = canonical_adapter.build_completed_history(
        rows[:3], symbol="NIFTY", session_date="2026-01-02", timeframe="5m"
    )
    assert len(history) == 3
    assert history[-1]["bar_start_timestamp"] == rows[2]["timestamp"]
    assert isinstance(history[-1]["bar_start_timestamp"], pd.Timestamp)
    assert rows[3]["timestamp"] not in {row["bar_start_timestamp"] for row in history}


def test_unknown_strategy_fails_closed() -> None:
    with pytest.raises(KeyError, match="unknown_canonical_strategy"):
        canonical_adapter.resolve_callable("NOT_A_STRATEGY")
