from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from research.reversal_probability_profile_v2.state_machine import (
    RPPV2Config,
    _build_profile,
    _pivot_confirmations,
    attach_forward_outcomes,
    build_confirmed_events,
    infer_cadence_minutes,
    label_zone_interactions,
    load_nifty_ohlc,
)


def _row(ts: str, **overrides) -> dict:
    base = {
        "timestamp": pd.Timestamp(ts, tz="Asia/Kolkata"),
        "session": pd.Timestamp(ts).date(),
        "open": 100.0,
        "high": 100.5,
        "low": 99.5,
        "close": 100.0,
        "prev_close": 100.0,
        "atr": 2.0,
        "cadence_minutes": 5,
        "approach_momentum_atr": 0.0,
        "approach_direction": "FLAT",
        "confirmed_pivot_count": 30,
        "support": 98.0,
        "support_density": 0.75,
        "support_distance_atr": 1.0,
        "resistance": 102.0,
        "resistance_density": 0.75,
        "resistance_distance_atr": 1.0,
        "nearest_zone_type": "SUPPORT",
        "max_reversal_zone": 100.0,
        "max_zone_distance_atr": 0.0,
        "max_zone_relative_density": 1.0,
    }
    base.update(overrides)
    return base


def test_pivot_is_unavailable_until_right_bars_close():
    cfg = replace(RPPV2Config(), pivot_left=2, pivot_right=2)
    ts = pd.date_range("2026-01-02 09:15", periods=7, freq="5min", tz="Asia/Kolkata")
    high = [1, 2, 5, 2, 1, 2, 1]
    df = pd.DataFrame({
        "timestamp": ts,
        "open": high,
        "high": high,
        "low": [0] * 7,
        "close": high,
    })
    df["session"] = df["timestamp"].dt.date
    conf = _pivot_confirmations(df, cfg)
    assert any(kind == "HIGH" and pivot_idx == 2 for kind, _, pivot_idx in conf[4])
    assert 2 not in conf
    assert 3 not in conf


def test_profile_score_is_relative_density_not_probability():
    cfg = replace(RPPV2Config(), min_profile_pivots=4, profile_bins=8, smoothing_radius_bins=1)
    pivots = [
        ("LOW", 100.0, 0, 2),
        ("LOW", 100.2, 5, 7),
        ("HIGH", 104.0, 10, 12),
        ("HIGH", 104.1, 15, 17),
        ("HIGH", 104.2, 20, 22),
    ]
    profile = _build_profile(pivots, cfg)
    assert profile is not None
    scores = profile["relative_density"]
    assert np.isclose(scores.max(), 1.0)
    assert (scores >= 0).all() and (scores <= 1).all()


def test_support_rejection_is_bullish_close_confirmed():
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=100.6, support=100.0, support_density=0.82, resistance=104.0),
        _row(
            "2026-01-02 10:05",
            open=100.5,
            high=100.6,
            low=100.1,
            close=100.3,
            approach_momentum_atr=-0.3,
            approach_direction="DOWN",
            support=99.0,
            resistance=105.0,
        ),
    ])
    out = label_zone_interactions(loc)
    e = out.iloc[1]
    assert e["interaction_state"] == "REJECTED"
    assert e["interaction_direction"] == "BULLISH"
    assert e["interaction_zone_type"] == "SUPPORT"
    assert e["interaction_zone"] == 100.0
    assert e["interaction_density"] == 0.82


def test_resistance_rejection_is_bearish_close_confirmed():
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=101.4, support=98.0, resistance=102.0, resistance_density=0.91),
        _row(
            "2026-01-02 10:05",
            open=101.5,
            high=101.9,
            low=101.3,
            close=101.7,
            approach_momentum_atr=0.4,
            approach_direction="UP",
            support=97.0,
            resistance=104.0,
        ),
    ])
    out = label_zone_interactions(loc)
    e = out.iloc[1]
    assert e["interaction_state"] == "REJECTED"
    assert e["interaction_direction"] == "BEARISH"
    assert e["interaction_zone"] == 102.0
    assert e["interaction_density"] == 0.91


def test_break_uses_previous_known_zone_not_current_reselected_zone():
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=101.8, resistance=102.0, resistance_density=0.88),
        _row(
            "2026-01-02 10:05",
            open=101.9,
            high=103.0,
            low=101.8,
            close=102.4,
            approach_momentum_atr=0.5,
            approach_direction="UP",
            resistance=105.0,
            resistance_density=0.99,
        ),
    ])
    out = label_zone_interactions(loc)
    e = out.iloc[1]
    assert e["interaction_state"] == "BROKEN"
    assert e["interaction_direction"] == "BULLISH"
    assert e["interaction_zone"] == 102.0
    assert e["interaction_density"] == 0.88
    assert e["zone_source_timestamp"] == loc.iloc[0]["timestamp"]


def test_break_becomes_accepted_only_after_required_closes_beyond_zone():
    cfg = replace(RPPV2Config(), acceptance_bars=2)
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=101.8, resistance=102.0, resistance_density=0.90),
        _row(
            "2026-01-02 10:05",
            open=101.9,
            high=102.7,
            low=101.8,
            close=102.4,
            approach_momentum_atr=0.5,
            resistance=105.0,
        ),
        _row(
            "2026-01-02 10:10",
            open=102.4,
            high=103.0,
            low=102.35,
            close=102.7,
            approach_momentum_atr=0.4,
            resistance=105.0,
        ),
    ])
    out = label_zone_interactions(loc, cfg)
    assert out.iloc[1]["interaction_state"] == "BROKEN"
    assert out.iloc[2]["interaction_state"] == "ACCEPTED"
    assert out.iloc[2]["interaction_direction"] == "BULLISH"


def test_post_break_retest_can_confirm_reclaim():
    cfg = replace(RPPV2Config(), acceptance_bars=3)
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=101.8, resistance=102.0, resistance_density=0.93),
        _row(
            "2026-01-02 10:05",
            high=102.8,
            low=101.9,
            close=102.5,
            approach_momentum_atr=0.5,
            resistance=105.0,
        ),
        _row(
            "2026-01-02 10:10",
            high=102.6,
            low=102.1,
            close=102.35,
            approach_momentum_atr=0.2,
            resistance=105.0,
        ),
    ])
    out = label_zone_interactions(loc, cfg)
    assert out.iloc[1]["interaction_state"] == "BROKEN"
    assert out.iloc[2]["interaction_state"] == "RECLAIMED"
    assert out.iloc[2]["interaction_direction"] == "BULLISH"
    assert out.iloc[2]["interaction_zone_type"] == "RESISTANCE_TO_SUPPORT"


def test_first_break_is_not_a_forecast_event():
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=101.8, resistance=102.0, resistance_density=0.90),
        _row(
            "2026-01-02 10:05",
            high=102.8,
            low=101.9,
            close=102.5,
            approach_momentum_atr=0.5,
            resistance=105.0,
        ),
    ])
    states = label_zone_interactions(loc)
    events = build_confirmed_events(states)
    assert states.iloc[1]["interaction_state"] == "BROKEN"
    assert events.empty


def test_low_density_confirmation_is_observed_but_not_traded():
    loc = pd.DataFrame([
        _row("2026-01-02 10:00", close=100.6, support=100.0, support_density=0.40, resistance=104.0),
        _row(
            "2026-01-02 10:05",
            low=100.1,
            close=100.3,
            approach_momentum_atr=-0.3,
            support=99.0,
            resistance=105.0,
        ),
    ])
    states = label_zone_interactions(loc)
    assert states.iloc[1]["interaction_state"] == "REJECTED"
    assert not bool(states.iloc[1]["event_density_eligible"])
    assert build_confirmed_events(states).empty


def test_long_panel_loader_filters_nifty_before_duplicate_check(tmp_path):
    p = tmp_path / "panel.csv"
    ts = pd.date_range("2026-01-02 09:15", periods=3, freq="5min", tz="Asia/Kolkata")
    rows = []
    for symbol, offset in [("NIFTY", 0.0), ("RELIANCE", 100.0)]:
        for i, t in enumerate(ts):
            c = 100 + offset + i
            rows.append({
                "timestamp": t,
                "symbol": symbol,
                "open": c,
                "high": c + 1,
                "low": c - 1,
                "close": c + 0.2,
            })
    pd.DataFrame(rows).to_csv(p, index=False)
    out = load_nifty_ohlc(p)
    assert len(out) == 3
    assert out["close"].max() < 200
    assert infer_cadence_minutes(out) == 5


def test_forward_outcome_enters_next_actual_five_minute_open():
    ts = pd.date_range("2026-01-02 09:15", periods=12, freq="5min", tz="Asia/Kolkata")
    px = 100 + np.arange(len(ts)) * 0.1
    prices = pd.DataFrame({
        "timestamp": ts,
        "open": px,
        "high": px + 0.2,
        "low": px - 0.2,
        "close": px + 0.05,
    })
    prices["session"] = prices["timestamp"].dt.date
    decision = ts[3]
    events = pd.DataFrame([{
        "timestamp": decision,
        "session": decision.date(),
        "signal": 1,
        "approach_momentum_atr": 0.2,
        "interaction_density": 0.9,
        "event_type": "BULLISH_ACCEPTED",
    }])
    out = attach_forward_outcomes(events, prices)
    assert len(out) == 1
    assert out.iloc[0]["entry_timestamp"] == ts[4]
    assert out.iloc[0]["entry_open"] == prices.iloc[4]["open"]
