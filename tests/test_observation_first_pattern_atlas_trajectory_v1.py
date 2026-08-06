from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_observation_first_pattern_atlas_trajectory_v1.py"
SPEC = importlib.util.spec_from_file_location("atlas_trajectory", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_session(session_date: date, periods: int = 80) -> pd.DataFrame:
    start = pd.Timestamp.combine(session_date, MODULE.window(MODULE.regime(session_date))[0])
    timestamps = pd.date_range(start=start, periods=periods, freq="1min", tz=MODULE.TZ)
    price = 100.0 + np.cumsum(np.sin(np.arange(periods) / 7.0) * 0.08 + 0.03)
    return pd.DataFrame({
        "timestamp": timestamps,
        "instrument": "NIFTY",
        "session_date": session_date,
        "regime": MODULE.regime(session_date),
        "price": price,
        "volume": np.arange(periods, dtype=float) + 1.0,
        "source_vwap": np.nan,
        "observed_this_minute": True,
        "minutes_since_observation": 0.0,
        "session_start": timestamps[0],
        "session_end": pd.Timestamp.combine(
            session_date,
            MODULE.window(MODULE.regime(session_date))[1],
        ).tz_localize(MODULE.TZ),
    })


def test_explicit_allowlist_excludes_outcome_columns() -> None:
    available = ["timestamp", "open", "high", "low", "close", "volume", "future_return_15", "net_pnl"]
    selected = MODULE.allowed_columns("underlying", available)
    assert selected == ["timestamp", "open", "high", "low", "close", "volume"]


def test_cas_windows_are_not_silently_pooled() -> None:
    assert MODULE.window("PRE_CAS")[1].isoformat() == "15:30:00"
    assert MODULE.window("POST_CAS")[1].isoformat() == "15:40:00"
    assert MODULE.regime(date(2026, 8, 2)) == "PRE_CAS"
    assert MODULE.regime(date(2026, 8, 3)) == "POST_CAS"


def test_timestamp_normalization_preserves_aware_instants_and_localizes_naive() -> None:
    values = pd.Series(["2026-08-04 09:15:00", "2026-08-04T03:45:00+00:00"])
    normalized = MODULE.normalize_timestamps(values)
    assert normalized.iloc[0].isoformat() == "2026-08-04T09:15:00+05:30"
    assert normalized.iloc[1].isoformat() == "2026-08-04T09:15:00+05:30"


def test_causal_feature_prefix_invariance() -> None:
    first = make_session(date(2026, 7, 1), periods=80)
    second = make_session(date(2026, 7, 2), periods=80)
    full = pd.concat([first, second], ignore_index=True)
    assert MODULE.prefix_invariant(full, 120)


def test_completed_session_vector_does_not_extrapolate_missing_close() -> None:
    frame = MODULE.add_causal_features(make_session(date(2026, 8, 4), periods=80))
    session_vector = MODULE.vector(frame, 10)
    assert session_vector["regime"] == "POST_CAS"
    assert session_vector["features"]["return_from_open"][-1] is None


def test_quality_gate_rejects_incomplete_session() -> None:
    frame = MODULE.add_causal_features(make_session(date(2026, 8, 4), periods=80))
    accepted, rejected = MODULE.build_vectors(frame, 10, 0.90, 5.0)
    assert accepted == []
    assert rejected[0]["reasons"]
