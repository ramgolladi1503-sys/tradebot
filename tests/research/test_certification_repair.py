from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from research.constituent_lead_lag.evidence_controls import (
    build_matched_no_lead_control,
    concentration_summary,
    delayed_entry_summary,
)
from research.constituent_lead_lag.model import (
    DataContractError,
    SignalState,
    StrategyThresholds,
    TradeOutcome,
    generate_signal_states,
)
from research.constituent_lead_lag.unweighted import (
    UnweightedThresholds,
    generate_unweighted_signal_states,
)


def _bar(session: str, time: str, symbol: str, close: float) -> dict[str, object]:
    ts = pd.Timestamp(f"{session} {time}", tz="Asia/Kolkata").tz_convert("UTC")
    return {
        "timestamp": ts,
        "session": session,
        "symbol": symbol,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
    }


def _exact_fixture(missing_symbol_time: tuple[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    session = "2026-01-02"
    symbols = ["NIFTY", "A", "B", "C", "D", "E"]
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        for i, time in enumerate(["09:50", "09:55", "10:00"]):
            if missing_symbol_time == (symbol, time):
                continue
            base = 100.0 if symbol == "NIFTY" else 100.0 + symbols.index(symbol)
            rows.append(_bar(session, time, symbol, base + i))
    weights = pd.DataFrame([
        {
            "index_symbol": "NIFTY",
            "constituent_symbol": symbol,
            "effective_from": session,
            "effective_to": None,
            "weight": 0.2,
        }
        for symbol in ["A", "B", "C", "D", "E"]
    ])
    return pd.DataFrame(rows), weights


def test_weighted_exact_grid_excludes_non_contiguous_constituent():
    bars, weights = _exact_fixture(("E", "09:55"))
    states = generate_signal_states(bars, weights, "NIFTY", decision_times=["10:00"])
    assert len(states) == 1
    assert states[0].constituents_expected == 5
    assert states[0].constituents_available == 4
    assert states[0].count_coverage == pytest.approx(0.8)
    assert states[0].weight_coverage == pytest.approx(0.8)
    assert states[0].missing_constituents == ("E",)


def test_weighted_index_exact_grid_fails_closed():
    bars, weights = _exact_fixture(("NIFTY", "09:55"))
    with pytest.raises(DataContractError, match="index exact return grid missing"):
        generate_signal_states(bars, weights, "NIFTY", decision_times=["10:00"])


def test_unweighted_uses_same_exact_grid_contract():
    bars, weights = _exact_fixture(("D", "09:50"))
    universe = weights.drop(columns=["weight"])
    states = generate_unweighted_signal_states(
        bars,
        universe,
        "NIFTY",
        decision_times=["10:00"],
        thresholds=UnweightedThresholds(minimum_constituent_count=5),
    )
    assert len(states) == 1
    assert states[0].constituents_available == 4
    assert states[0].constituent_coverage == pytest.approx(0.8)
    assert states[0].missing_constituents == ("D",)


def test_real_matched_control_does_not_copy_signal_rows():
    states = pd.DataFrame([
        {"session": "2026-01-01", "decision_time": "10:00", "decision_timestamp": "2026-01-01T04:30:00Z", "side": "LONG", "reason": "signal", "rolling_median_30m_move_bps": 10},
        {"session": "2026-01-02", "decision_time": "10:30", "decision_timestamp": "2026-01-02T05:00:00Z", "side": "SHORT", "reason": "signal", "rolling_median_30m_move_bps": 20},
        {"session": "2026-01-03", "decision_time": "10:00", "decision_timestamp": "2026-01-03T04:30:00Z", "side": "NONE", "reason": "no_lead", "rolling_median_30m_move_bps": 11},
        {"session": "2026-01-04", "decision_time": "10:30", "decision_timestamp": "2026-01-04T05:00:00Z", "side": "NONE", "reason": "no_lead", "rolling_median_30m_move_bps": 21},
        {"session": "2026-01-05", "decision_time": "10:00", "decision_timestamp": "2026-01-05T04:30:00Z", "side": "NONE", "reason": "no_lead", "rolling_median_30m_move_bps": 12},
        {"session": "2026-01-06", "decision_time": "10:30", "decision_timestamp": "2026-01-06T05:00:00Z", "side": "NONE", "reason": "no_lead", "rolling_median_30m_move_bps": 22},
    ])
    control, summary = build_matched_no_lead_control(states)
    assert summary["result"] == "MATCHED_CONTROL_CONSTRUCTED"
    assert len(control) == 2
    assert set(control["control_original_side"]) == {"NONE"}
    assert Counter(control["control_side"]) == Counter({"LONG": 1, "SHORT": 1})
    assert not (control["matched_signal_decision_timestamp"] == control["control_decision_timestamp"]).any()


def _signal_state() -> SignalState:
    return SignalState(
        index_symbol="NIFTY",
        session="2026-01-02",
        decision_time="10:00",
        decision_timestamp=pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata").tz_convert("UTC").isoformat(),
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
        rolling_median_30m_move_bps=20,
    )


def test_delay_is_numeric_and_uses_second_bar_after_decision():
    session = "2026-01-02"
    rows = []
    for time, open_, high, low, close in [
        ("10:00", 100.0, 100.0, 100.0, 100.0),
        ("10:05", 100.0, 100.1, 99.9, 100.0),
        ("10:10", 101.0, 101.05, 100.95, 101.02),
        ("10:15", 101.1, 101.3, 101.0, 101.2),
        ("10:20", 101.2, 101.4, 101.1, 101.3),
        ("10:25", 101.3, 101.5, 101.2, 101.4),
    ]:
        rows.append({
            "timestamp": pd.Timestamp(f"{session} {time}", tz="Asia/Kolkata").tz_convert("UTC"),
            "session": session,
            "symbol": "NIFTY",
            "open": open_, "high": high, "low": low, "close": close,
        })
    outcomes, summary = delayed_entry_summary([_signal_state()], pd.DataFrame(rows), StrategyThresholds())
    assert summary["result"] == "COMPUTED"
    assert len(outcomes) == 1
    assert outcomes[0].entry_timestamp == pd.Timestamp(f"{session} 10:10", tz="Asia/Kolkata").tz_convert("UTC").isoformat()
    assert isinstance(summary["net_mean_bps"], float)


def test_concentration_persists_numeric_shares():
    outcomes = [
        TradeOutcome("NIFTY", "2026-01-02", "10:00", "LONG", "x", "y", 100, 101, 10, 15, 10, 10, "MAX_HOLD"),
        TradeOutcome("NIFTY", "2026-02-02", "10:30", "SHORT", "x", "y", 100, 99, 10, 15, 30, 30, "MAX_HOLD"),
    ]
    summary = concentration_summary(outcomes)
    assert summary["result"] == "COMPUTED"
    assert summary["monthly_absolute_pnl_share_max"] == pytest.approx(0.75)
    assert summary["top_five_session_absolute_pnl_share"] == pytest.approx(1.0)


def test_exact_coverage_reconciles_with_weighted_state():
    from scripts.calculate_proxy_membership_coverage import calculate_frame

    bars, weights = _exact_fixture(("E", "09:55"))
    session = "2026-01-02"
    cutoff = pd.Timestamp(f"{session} 10:00", tz="Asia/Kolkata").tz_convert("UTC").isoformat()
    states = pd.DataFrame([{
        "session": session,
        "decision_time": "10:00",
        "decision_timestamp": cutoff,
        "count_coverage": 0.8,
        "weight_coverage": 0.8,
    }])
    resolution = pd.DataFrame({"proxy_ticker": ["A", "B", "C", "D", "E"]})
    coverage, summary = calculate_frame(states, bars, weights, resolution, session, session)
    assert coverage.iloc[0]["exact_bar_valid_constituents"] == 4
    assert coverage.iloc[0]["stale_or_missing_constituents"] == ["E"]
    assert coverage.iloc[0]["count_coverage"] == pytest.approx(0.8)
    assert coverage.iloc[0]["weight_coverage"] == pytest.approx(0.8)
    assert summary["state_count_coverage_mismatches"] == 0
    assert summary["state_weight_coverage_mismatches"] == 0


def test_explicit_session_policy_separates_special_and_partial_sessions():
    from scripts.audit_proxy_campaign_bars import audit_frame

    rows = []
    for session in ["2026-01-02", "2026-01-03", "2026-01-04"]:
        timestamps = pd.date_range(
            pd.Timestamp(f"{session} 09:15", tz="Asia/Kolkata"),
            pd.Timestamp(f"{session} 15:25", tz="Asia/Kolkata"),
            freq="5min",
        )
        if session == "2026-01-04":
            timestamps = timestamps[:-1]
        for ts in timestamps:
            rows.append({
                "timestamp": ts.tz_convert("UTC"),
                "session": session,
                "symbol": "NIFTY",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            })
    policy = {
        "source": "frozen exchange-calendar fixture",
        "timezone": "Asia/Kolkata",
        "regular_grid": {"start": "09:15", "end": "15:25", "frequency_minutes": 5},
        "sessions": {
            "2026-01-02": "REGULAR",
            "2026-01-03": "SPECIAL",
            "2026-01-04": "REGULAR",
        },
    }
    grid, report = audit_frame(pd.DataFrame(rows), policy, ["10:00"])
    classes = dict(zip(grid["session"], grid["session_classification"]))
    assert classes["2026-01-02"] == "REGULAR_SESSION_COMPLETE"
    assert classes["2026-01-03"] == "SPECIAL_SESSION_OUT_OF_FROZEN_CONTRACT"
    assert classes["2026-01-04"] == "REGULAR_SESSION_PARTIAL"
    assert report["completed_regular_sessions"] == 1
