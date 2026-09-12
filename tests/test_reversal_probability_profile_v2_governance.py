from __future__ import annotations

import pandas as pd

from research.reversal_probability_profile_v2 import RPPV2Config
from research.reversal_probability_profile_v2.experiment import (
    apply_governed_regular_session_policy,
    build_terminal_confirmed_events,
)


def test_governed_special_sessions_are_excluded_before_research():
    rows = []
    for d in ["2024-01-19", "2024-01-20", "2024-03-02", "2024-03-04"]:
        ts = pd.Timestamp(f"{d} 10:00", tz="Asia/Kolkata")
        rows.append({
            "timestamp": ts,
            "session": ts.date(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
        })
    kept, excluded = apply_governed_regular_session_policy(pd.DataFrame(rows))
    assert excluded == ["2024-01-20", "2024-03-02"]
    assert {str(x) for x in kept["session"].unique()} == {"2024-01-19", "2024-03-04"}


def test_same_break_cannot_emit_both_acceptance_and_reclaim_forecasts():
    cfg = RPPV2Config(deoverlap_minutes=0)
    session = pd.Timestamp("2026-01-02").date()
    source = pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata")
    base = {
        "session": session,
        "event_density_eligible": True,
        "interaction_direction": "BULLISH",
        "interaction_density": 0.9,
        "zone_source_timestamp": source,
        "approach_momentum_atr": 0.4,
    }
    states = pd.DataFrame([
        {
            **base,
            "timestamp": pd.Timestamp("2026-01-02 10:10", tz="Asia/Kolkata"),
            "interaction_state": "ACCEPTED",
        },
        {
            **base,
            "timestamp": pd.Timestamp("2026-01-02 10:20", tz="Asia/Kolkata"),
            "interaction_state": "RECLAIMED",
        },
    ])
    events = build_terminal_confirmed_events(states, cfg)
    assert len(events) == 1
    assert events.iloc[0]["interaction_state"] == "ACCEPTED"
