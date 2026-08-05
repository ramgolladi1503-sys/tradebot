from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "upstox_capture"
    / "generate_offline_datasets_v3.py"
)
spec = importlib.util.spec_from_file_location("generate_offline_datasets_v3", MODULE_PATH)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)


def utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def test_0730_utc_is_1300_ist_and_live():
    boundary = utc("2026-08-05 07:30:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "13:00:00"
    # This boundary is intentionally in the known stale-gap set.
    assert generator.classify_interval(boundary, 0.0) == "STALE_CARRY_FORWARD"


def test_0732_utc_is_continuous_market_not_startup():
    boundary = utc("2026-08-05 07:32:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "13:02:00"
    assert generator.classify_interval(boundary, 0.0) == "LIVE_FRESH"
    assert generator.get_market_phase(boundary) == "CONTINUOUS_MARKET"


def test_0915_utc_is_not_indian_market_open():
    boundary = utc("2026-08-05 09:15:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "14:45:00"
    assert generator.classify_interval(boundary, 0.0) == "LIVE_FRESH"


def test_after_1530_ist_is_excluded():
    boundary = utc("2026-08-05 10:01:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "15:31:00"
    assert generator.classify_interval(boundary, 0.0) == "OUTSIDE_CONTINUOUS_MARKET"
    assert (
        generator.get_market_phase(boundary)
        == "POST_CLOSE_OR_DERIVATIVE_CONVERGENCE"
    )


def test_latest_complete_rows_preserves_single_source_row():
    frame = pd.DataFrame(
        [
            {
                "instrument_key": "A",
                "source_exchange_ts": 1000,
                "local_sequence": 1,
                "receive_monotonic_ns": 1,
                "ltp": 100.0,
                "volume": 10,
            },
            {
                "instrument_key": "A",
                "source_exchange_ts": 2000,
                "local_sequence": 2,
                "receive_monotonic_ns": 2,
                "ltp": 101.0,
                "volume": None,
            },
        ]
    )
    latest = generator._latest_complete_rows(frame, 2000).iloc[0]
    assert latest["ltp"] == 101.0
    assert pd.isna(latest["volume"])
