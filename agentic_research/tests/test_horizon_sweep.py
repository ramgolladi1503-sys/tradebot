from __future__ import annotations

import pandas as pd

from agentic_research.historical.horizon_sweep import (
    _later_outcomes_for_timeouts,
    _select_one_position_at_a_time,
    resolve_trace_at_horizon,
    summarize_horizon,
    trace_signal_path,
)
from agentic_research.historical.models import HistoricalCampaignConfig


def _session(*, stop_bar: int | None = None, target_bar: int | None = None, bars: int = 70) -> pd.DataFrame:
    rows = []
    for index in range(bars):
        open_price = 100.0
        high = 100.2
        low = 99.8
        if stop_bar is not None and index == stop_bar:
            low = 98.9
        if target_bar is not None and index == target_bar:
            high = 101.6
        rows.append({
            "timestamp": pd.Timestamp("2020-01-01 09:15", tz="Asia/Kolkata") + pd.Timedelta(minutes=index),
            "open": open_price,
            "high": high,
            "low": low,
            "close": 100.1,
        })
    return pd.DataFrame(rows)


def _trace(session: pd.DataFrame) -> dict:
    trace = trace_signal_path(
        session,
        0,
        direction="BUY_CALL",
        anchor=99.0,
        atr=0.0,
        config=HistoricalCampaignConfig(target_rr=1.5, stop_atr_buffer=0.0, max_hold_bars=60),
    )
    assert trace is not None
    return {**trace, "session_date": "2020-01-01", "setup_id": "setup"}


def test_stop_inside_15_minutes_is_stop_at_every_later_horizon():
    trace = _trace(_session(stop_bar=5))
    at_15 = resolve_trace_at_horizon(trace, 15, cost_bps=2.0)
    at_60 = resolve_trace_at_horizon(trace, 60, cost_bps=2.0)
    assert at_15["exit_reason"] == "STOP"
    assert at_15["hold_bars"] == 5
    assert at_60["exit_reason"] == "STOP"
    assert at_60["hold_bars"] == 5
    assert at_15["net_return_bps"] == at_60["net_return_bps"]


def test_target_after_15_is_timeout_at_15_and_target_at_20():
    trace = _trace(_session(target_bar=18))
    at_15 = resolve_trace_at_horizon(trace, 15, cost_bps=2.0)
    at_20 = resolve_trace_at_horizon(trace, 20, cost_bps=2.0)
    assert at_15["exit_reason"] == "TIMEOUT"
    assert at_15["hold_bars"] == 15
    assert at_20["exit_reason"] == "TARGET"
    assert at_20["hold_bars"] == 18


def test_same_bar_stop_and_target_is_conservatively_stop_first():
    session = _session(stop_bar=8, target_bar=8)
    trace = _trace(session)
    resolved = resolve_trace_at_horizon(trace, 15, cost_bps=2.0)
    assert resolved["exit_reason"] == "STOP"
    assert resolved["same_bar_ambiguity"] is True


def test_15_minute_timeout_cohort_reports_later_target_stop_and_unresolved():
    target = _trace(_session(target_bar=20))
    target["setup_id"] = "target"
    stop = _trace(_session(stop_bar=25))
    stop["setup_id"] = "stop"
    unresolved = _trace(_session())
    unresolved["setup_id"] = "unresolved"
    result = _later_outcomes_for_timeouts([target, stop, unresolved], 15, 60)
    assert result["timeout_cohort"] == 3
    assert result["later_target_by_maximum"] == 1
    assert result["later_stop_by_maximum"] == 1
    assert result["still_unresolved_at_maximum"] == 1


def test_timeout_losses_are_not_counted_as_stop_losses():
    trace = _trace(_session())
    trade = resolve_trace_at_horizon(trace, 15, cost_bps=20.0)
    assert trade["exit_reason"] == "TIMEOUT"
    summary = summarize_horizon([trade])
    assert summary["timeout_losses"] == 1
    assert summary["stop_losses"] == 0


def test_one_position_policy_suppresses_only_overlapping_entries():
    base = {
        "session_date": "2020-01-01",
        "setup_id": "first",
        "signal_index": 0,
        "entry_index": 1,
        "exit_index": 10,
        "entry_timestamp": "2020-01-01T09:16:00+05:30",
        "exit_timestamp": "2020-01-01T09:25:00+05:30",
        "direction": "BUY_CALL",
        "horizon_bars": 15,
        "exit_reason": "TIMEOUT",
        "same_bar_ambiguity": False,
        "hold_bars": 10,
        "gross_return_bps": 1.0,
        "net_return_bps": -1.0,
    }
    overlap = {**base, "setup_id": "overlap", "entry_index": 5, "exit_index": 12}
    later = {**base, "setup_id": "later", "entry_index": 11, "exit_index": 20}
    selected, skipped = _select_one_position_at_a_time([overlap, later, base])
    assert [trade["setup_id"] for trade in selected] == ["first", "later"]
    assert skipped == 1


def test_signal_without_complete_60_minute_path_is_excluded():
    trace = trace_signal_path(
        _session(bars=50),
        0,
        direction="BUY_CALL",
        anchor=99.0,
        atr=0.0,
        config=HistoricalCampaignConfig(target_rr=1.5, stop_atr_buffer=0.0, max_hold_bars=60),
    )
    assert trace is None
