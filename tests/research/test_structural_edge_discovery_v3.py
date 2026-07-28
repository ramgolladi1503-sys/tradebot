from __future__ import annotations

import pandas as pd

from research.structural_edge_discovery_v3.engine import (
    add_causal_features,
    build_events,
    event_feature_frame,
    label_outcomes,
    stable_hash,
)


def _sample_session() -> pd.DataFrame:
    ts = pd.date_range("2026-07-01 09:15", periods=80, freq="min", tz="Asia/Kolkata")
    rows = []
    price = 100.0
    for i, item in enumerate(ts):
        price += 0.2 if i > 20 else (-0.1 if i < 10 else 0.05)
        rows.append(
            {
                "session_id": "NIFTY:2026-07-01",
                "instrument": "NIFTY",
                "session_date": "2026-07-01",
                "ts": item,
                "bar_completed_ts": item + pd.Timedelta(minutes=1),
                "open": price - 0.1,
                "high": price + 0.3,
                "low": price - 0.3,
                "close": price,
                "volume": 0.0,
                "source_path": "fixture",
                "source_hash": "fixture",
            }
        )
    return pd.DataFrame(rows)


def test_stable_hash_is_deterministic() -> None:
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})


def test_features_use_completed_bar_timestamps() -> None:
    features = add_causal_features(_sample_session())
    assert (features["bar_completed_ts"] > features["ts"]).all()
    assert "vwap_distance" in features.columns


def test_event_and_outcome_pipeline_is_causal_next_bar() -> None:
    features = add_causal_features(_sample_session())
    events = build_events(features)
    assert not events.empty
    event_features = event_feature_frame(events, features)
    labelled = label_outcomes(event_features, features)
    assert not labelled.empty
    entry_ts = pd.to_datetime(labelled.iloc[0]["entry_timestamp"])
    trigger_ts = pd.to_datetime(labelled.iloc[0]["causal_trigger_timestamp"])
    assert entry_ts >= trigger_ts

