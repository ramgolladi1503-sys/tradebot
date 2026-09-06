from __future__ import annotations

import numpy as np
import pandas as pd

from research.reversal_probability_profile_v1.campaign import (
    CampaignConfig,
    CandidateSpec,
    _pivot_confirmations,
    attach_shifted_time_control,
    build_candidate_events,
    build_causal_profile_features,
    load_index_ohlc,
)


def _frame(days: int = 8) -> pd.DataFrame:
    rows = []
    for d in range(days):
        date = pd.Timestamp("2026-01-02") + pd.Timedelta(days=d)
        if date.weekday() >= 5:
            continue
        ts = pd.date_range(date.strftime("%Y-%m-%d") + " 09:15", periods=180, freq="1min", tz="Asia/Kolkata")
        x = np.arange(len(ts))
        base = 24000 + 12*np.sin(x/4.0) + 0.02*x + d
        for t, c in zip(ts, base):
            rows.append({"timestamp": t, "open": c-0.2, "high": c+1.0, "low": c-1.0, "close": c})
    df = pd.DataFrame(rows)
    df["session"] = df["timestamp"].dt.date
    return df.reset_index(drop=True)


def test_pivots_are_only_available_after_right_bars():
    cfg = CampaignConfig(pivot_left=2, pivot_right=2)
    ts = pd.date_range("2026-01-02 09:15", periods=7, freq="1min", tz="Asia/Kolkata")
    high = [1, 2, 5, 2, 1, 2, 1]
    low = [0, 0, 0, 0, 0, 0, 0]
    df = pd.DataFrame({"timestamp": ts, "open": high, "high": high, "low": low, "close": high})
    df["session"] = df["timestamp"].dt.date
    conf = _pivot_confirmations(df, cfg)
    # Pivot centered at index 2 can only be confirmed at index 4.
    assert any(kind == "HIGH" and pivot_idx == 2 for kind, _, pivot_idx in conf[4])
    assert 2 not in conf
    assert 3 not in conf


def test_causal_features_do_not_exist_before_minimum_confirmed_pivots():
    df = _frame()
    cfg = CampaignConfig(
        pivot_left=2, pivot_right=2, min_profile_pivots=10,
        pivot_memory=40, profile_bins=24, atr_window=10,
        calculation_lookback_bars=500,
    )
    feat = build_causal_profile_features(df, cfg)
    assert not feat.empty
    assert feat["confirmed_pivot_count"].min() >= 10
    assert feat["support_density"].dropna().between(0, 1).all()
    assert feat["resistance_density"].dropna().between(0, 1).all()


def test_candidate_signal_uses_only_current_and_past_columns():
    cfg = CampaignConfig()
    f = pd.DataFrame([{
        "timestamp": pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata"),
        "session": pd.Timestamp("2026-01-02").date(),
        "open": 100, "high": 101, "low": 99.9, "close": 100.8, "prev_close": 100.0,
        "atr": 2.0, "momentum_atr": 0.5,
        "support": 98.0, "support_density": 0.7,
        "resistance": 100.4, "resistance_density": 0.9,
        "support_distance_atr": 1.4, "resistance_distance_atr": -0.2,
        "max_reversal_zone": 100.4, "max_zone_distance_atr": 0.2,
        "confirmed_pivot_count": 30,
    }])
    ev = build_candidate_events(f, CandidateSpec("X", "BREAKOUT", 0.8), cfg)
    assert len(ev) == 1
    assert int(ev.iloc[0]["signal"]) == 1


def test_loader_accepts_spot_prefixed_columns(tmp_path):
    p = tmp_path / "x.csv"
    ts = pd.date_range("2026-01-02 09:15", periods=3, freq="1min", tz="Asia/Kolkata")
    pd.DataFrame({
        "timestamp": ts,
        "spot_open": [1,2,3], "spot_high": [2,3,4], "spot_low": [0,1,2], "spot_close": [1.5,2.5,3.5],
    }).to_csv(p, index=False)
    out = load_index_ohlc(p)
    assert list(out.columns[:5]) == ["timestamp", "open", "high", "low", "close"]
    assert len(out) == 3


def test_shifted_negative_control_moves_clock_and_preserves_signal():
    cfg = CampaignConfig(negative_control_shift_minutes=30, primary_horizon_minutes=15, round_trip_cost_bps=5.0)
    ts = pd.date_range("2026-01-02 09:15", periods=120, freq="1min", tz="Asia/Kolkata")
    px = 100.0 + np.arange(len(ts)) * 0.01
    prices = pd.DataFrame({
        "timestamp": ts,
        "open": px,
        "high": px + 0.1,
        "low": px - 0.1,
        "close": px,
    })
    prices["session"] = prices["timestamp"].dt.date
    decision = pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata")
    events = pd.DataFrame([{
        "timestamp": decision,
        "session": decision.date(),
        "signal": 1,
    }])
    out = attach_shifted_time_control(events, prices, cfg)
    assert len(out) == 1
    assert out.iloc[0]["shifted_control_decision_timestamp"] == pd.Timestamp("2026-01-02 10:30", tz="Asia/Kolkata")
    assert out.iloc[0]["shifted_control_entry_timestamp"] == pd.Timestamp("2026-01-02 10:31", tz="Asia/Kolkata")
    assert np.isfinite(out.iloc[0]["shifted_control_net_bps"])
