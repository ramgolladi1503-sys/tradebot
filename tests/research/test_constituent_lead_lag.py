from __future__ import annotations

import pandas as pd
import pytest

from research.constituent_lead_lag.model import (
    DataContractError,
    SignalState,
    StrategyThresholds,
    classify_state,
    evaluate_first_signal_per_session,
    select_weight_snapshot,
    validate_bars,
    validate_weights,
)


def test_weight_snapshot_is_point_in_time():
    weights = validate_weights(pd.DataFrame([
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2026-01-01", "effective_to": "2026-06-30", "weight": 0.5},
        {"index_symbol": "NIFTY", "constituent_symbol": "B", "effective_from": "2026-01-01", "effective_to": "2026-06-30", "weight": 0.5},
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2026-07-01", "effective_to": None, "weight": 0.4},
        {"index_symbol": "NIFTY", "constituent_symbol": "C", "effective_from": "2026-07-01", "effective_to": None, "weight": 0.6},
    ]))
    june = select_weight_snapshot(weights, "NIFTY", "2026-06-15")
    july = select_weight_snapshot(weights, "NIFTY", "2026-07-15")
    assert set(june.constituent_symbol) == {"A", "B"}
    assert set(july.constituent_symbol) == {"A", "C"}


def test_long_and_short_entry_contract_is_symmetric():
    t = StrategyThresholds()
    long_side, _ = classify_state(
        basket_return_5m_bps=12,
        basket_return_10m_bps=20,
        lead_gap_z=2.2,
        participation=0.8,
        weighted_breadth=0.5,
        dispersion_percentile=0.5,
        catch_up_ratio=0.4,
        range_consumed=0.4,
        weight_coverage=0.9,
        thresholds=t,
    )
    short_side, _ = classify_state(
        basket_return_5m_bps=-12,
        basket_return_10m_bps=-20,
        lead_gap_z=-2.2,
        participation=0.8,
        weighted_breadth=-0.5,
        dispersion_percentile=0.5,
        catch_up_ratio=0.4,
        range_consumed=0.4,
        weight_coverage=0.9,
        thresholds=t,
    )
    assert long_side == "LONG"
    assert short_side == "SHORT"


def test_low_weight_coverage_fails_closed():
    side, reason = classify_state(
        basket_return_5m_bps=20,
        basket_return_10m_bps=30,
        lead_gap_z=3,
        participation=0.9,
        weighted_breadth=0.8,
        dispersion_percentile=0.2,
        catch_up_ratio=0.2,
        range_consumed=0.2,
        weight_coverage=0.5,
        thresholds=StrategyThresholds(),
    )
    assert side == "NONE"
    assert reason == "insufficient_weight_coverage"


def test_duplicate_bars_rejected():
    rows = [
        {"timestamp": "2026-07-01T04:30:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 101, "low": 99, "close": 100.5},
        {"timestamp": "2026-07-01T04:30:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 101, "low": 99, "close": 100.5},
    ]
    with pytest.raises(DataContractError):
        validate_bars(pd.DataFrame(rows))


def test_next_bar_entry_and_same_bar_ambiguity():
    bars = pd.DataFrame([
        {"timestamp": "2026-07-01T04:25:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 100, "low": 100, "close": 100},
        {"timestamp": "2026-07-01T04:30:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 102, "low": 98, "close": 100},
        {"timestamp": "2026-07-01T04:35:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 100.2, "low": 99.8, "close": 100},
        {"timestamp": "2026-07-01T04:40:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 100.2, "low": 99.8, "close": 100},
        {"timestamp": "2026-07-01T04:45:00Z", "session": "2026-07-01", "symbol": "NIFTY", "open": 100, "high": 100.2, "low": 99.8, "close": 100},
    ])
    state = SignalState(
        index_symbol="NIFTY",
        session="2026-07-01",
        decision_time="10:00",
        decision_timestamp="2026-07-01T04:25:00+00:00",
        side="LONG",
        reason="fixture",
        basket_return_5m_bps=10,
        basket_return_10m_bps=20,
        index_return_5m_bps=1,
        index_return_10m_bps=2,
        lead_gap_bps=9,
        lead_gap_z=2.5,
        participation=0.8,
        weighted_breadth=0.5,
        dispersion_bps=2,
        dispersion_percentile=0.2,
        catch_up_ratio=0.1,
        range_consumed=0.2,
        weight_coverage=1.0,
        rolling_median_30m_move_bps=100,
    )
    outcome = evaluate_first_signal_per_session([state], bars)[0]
    assert outcome.entry_timestamp == "2026-07-01T04:30:00+00:00"
    assert outcome.exit_reason == "AMBIGUOUS_SAME_BAR"
