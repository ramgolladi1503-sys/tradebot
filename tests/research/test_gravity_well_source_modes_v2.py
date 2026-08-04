from pathlib import Path
import importlib.util
import sys

import numpy as np
import pandas as pd
import pytest

MODULE = Path(__file__).parents[2] / "scripts" / "run_gravity_well_source_modes_v2.py"
spec = importlib.util.spec_from_file_location("gws", MODULE)
gws = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gws
assert spec.loader is not None
spec.loader.exec_module(gws)


def frame(close, centre, sessions=None, atr=1.0):
    count = len(close)
    timestamps = pd.date_range(
        "2026-07-09 09:15", periods=count, freq="5min", tz="Asia/Kolkata"
    )
    data = pd.DataFrame(
        {
            "timestamp": timestamps,
            "session": sessions or ["2026-07-09"] * count,
            "open": close,
            "high": np.array(close) + 0.2,
            "low": np.array(close) - 0.2,
            "close": close,
            "centre": centre,
            "atr": atr,
        }
    )
    data["centre_slope"] = data.centre.diff().fillna(0.1)
    data["centre_accel"] = data.centre_slope.diff().fillna(0.0)
    data["escape_upper"] = data.centre + 1.5 * data.atr
    data["escape_lower"] = data.centre - 1.5 * data.atr
    data["outer_upper"] = data.centre + 1.5 * data.atr
    data["outer_lower"] = data.centre - 1.5 * data.atr
    data["inner_upper"] = data.centre + 0.75 * data.atr
    data["inner_lower"] = data.centre - 0.75 * data.atr
    data["displacement_atr"] = (data.close - data.centre) / data.atr
    return data


def test_midline_emits_only_on_state_flip():
    data = frame([10, 11, 12, 9, 8, 11], [10] * 6)
    assert gws.signals_for_frame(data, "SOURCE_MIDLINE") == [
        (3, "SHORT"),
        (5, "LONG"),
    ]


def test_bands_mode_is_reclaim_hysteresis():
    data = frame([8.0, 8.4, 8.8, 10.0, 12.0, 11.0], [10] * 6)
    assert gws.signals_for_frame(data, "SOURCE_BANDS_RECLAIM") == [
        (2, "LONG"),
        (5, "SHORT"),
    ]


def test_trend_requires_escape_distance_and_directional_centre():
    data = frame([10, 10.5, 12.0, 12.2, 8.0], [10, 10.1, 10.2, 10.3, 10.2])
    assert gws.signals_for_frame(data, "SOURCE_TREND_SLOPE") == [
        (2, "LONG"),
        (4, "SHORT"),
    ]


def test_state_is_not_reset_at_session_boundary():
    sessions = ["2026-07-09"] * 3 + ["2026-07-10"] * 3
    data = frame(
        [10, 10.2, 12.0, 12.4, 12.5, 8.0],
        [10, 10.0, 10.1, 10.2, 10.3, 10.2],
        sessions=sessions,
    )
    assert gws.signals_for_frame(data, "SOURCE_TREND_SLOPE") == [
        (2, "LONG"),
        (5, "SHORT"),
    ]


def test_entry_is_next_bar_and_outcome_does_not_cross_session():
    sessions = ["2026-07-09"] * 8 + ["2026-07-10"] * 2
    data = frame(
        [8.0, 8.4, 8.8, 10, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7],
        [10] * 10,
        sessions=sessions,
    )
    events = gws.generate_source_mode_events(
        data,
        gws.SourceModeSpec(max_hold_bars=6, centre_mode="UNIFORM_VOLUME_SMA"),
    )
    row = events[events.family == "SOURCE_BANDS_RECLAIM"].iloc[0]
    assert pd.Timestamp(row.entry_timestamp) > pd.Timestamp(row.signal_timestamp)
    assert pd.Timestamp(row.exit_timestamp).date() == pd.Timestamp(row.entry_timestamp).date()
    assert row.hold_bars <= 6
    assert bool(row.exact_source_code_replication) is False


def test_uniform_volume_proxy_is_sma_and_true_vwma_is_weighted():
    raw = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-09 09:15", periods=6, freq="5min", tz="Asia/Kolkata"
            ),
            "session": "2026-07-09",
            "open": np.arange(6.0) + 100,
            "high": np.arange(6.0) + 101,
            "low": np.arange(6.0) + 99,
            "close": np.arange(6.0) + 100,
            "volume": [1, 1, 10, 1, 1, 1],
        }
    )
    sma = gws.add_source_indicators(
        raw,
        gws.SourceModeSpec(
            centre_length=3,
            atr_length=2,
            centre_mode="UNIFORM_VOLUME_SMA",
        ),
    )
    vwma = gws.add_source_indicators(
        raw,
        gws.SourceModeSpec(
            centre_length=3,
            atr_length=2,
            centre_mode="TRUE_VWMA",
        ),
    )
    assert sma.centre.iloc[2] == np.mean([100.0, 101.0, 102.0])
    assert vwma.centre.iloc[2] == pytest.approx((100.0 + 101.0 + 1020.0) / 12.0)
    assert vwma.centre.iloc[2] != sma.centre.iloc[2]


def test_true_vwma_fails_closed_without_positive_volume():
    raw = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-09 09:15", periods=4, freq="5min", tz="Asia/Kolkata"
            ),
            "session": "2026-07-09",
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100, 101, 102, 103],
            "volume": [0, 0, 0, 0],
        }
    )
    with pytest.raises(ValueError, match="positive_volume"):
        gws.add_source_indicators(
            raw,
            gws.SourceModeSpec(
                centre_length=2,
                atr_length=2,
                centre_mode="TRUE_VWMA",
            ),
        )
