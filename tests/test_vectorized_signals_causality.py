from types import SimpleNamespace

import numpy as np
import pandas as pd

from core.vectorized_signals import (
    _causal_prior_session_ema,
    _same_session_next_open,
    build_vectorized_signals,
)


def _intraday_close(values_by_day):
    frames = []
    for day, values in values_by_day:
        idx = pd.date_range(
            f"{day} 09:15", periods=len(values), freq="5min", tz="Asia/Kolkata"
        )
        frames.append(pd.Series(values, index=idx, dtype=float))
    return pd.concat(frames)


def test_prior_session_ema_is_unchanged_by_same_day_future_close():
    base = _intraday_close(
        [
            ("2026-01-05", [100, 101, 102]),
            ("2026-01-06", [103, 104, 105]),
            ("2026-01-07", [106, 107, 108]),
        ]
    )
    mutated = base.copy()
    mutation_ts = pd.Timestamp("2026-01-07 09:25", tz="Asia/Kolkata")
    mutated.loc[mutation_ts] = 1000.0

    actual_base = _causal_prior_session_ema(base, span=2)
    actual_mutated = _causal_prior_session_ema(mutated, span=2)

    current_session = actual_base.index.normalize() == pd.Timestamp(
        "2026-01-07", tz="Asia/Kolkata"
    )
    assert base.loc[mutation_ts] != mutated.loc[mutation_ts]
    pd.testing.assert_series_equal(
        actual_base.loc[current_session],
        actual_mutated.loc[current_session],
    )
    assert np.isfinite(actual_base.loc[current_session]).all()


def test_prior_session_ema_matches_independent_daily_oracle():
    close = _intraday_close(
        [
            ("2026-01-05", [99, 100]),
            ("2026-01-06", [109, 110]),
            ("2026-01-07", [119, 120]),
        ]
    )
    actual = _causal_prior_session_ema(close, span=2)

    daily = pd.Series(
        [100.0, 110.0, 120.0],
        index=pd.DatetimeIndex(
            [
                pd.Timestamp("2026-01-05", tz="Asia/Kolkata"),
                pd.Timestamp("2026-01-06", tz="Asia/Kolkata"),
                pd.Timestamp("2026-01-07", tz="Asia/Kolkata"),
            ]
        ),
    )
    expected_daily = daily.ewm(span=2, adjust=False).mean().shift(1)
    expected = (
        pd.Series(close.index.normalize(), index=close.index)
        .map(expected_daily)
        .astype(float)
    )
    pd.testing.assert_series_equal(actual, expected)


def test_same_session_next_open_never_crosses_overnight_or_falls_back_to_close():
    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-01-05 15:25", tz="Asia/Kolkata"),
            pd.Timestamp("2026-01-05 15:30", tz="Asia/Kolkata"),
            pd.Timestamp("2026-01-06 09:15", tz="Asia/Kolkata"),
            pd.Timestamp("2026-01-06 09:20", tz="Asia/Kolkata"),
        ]
    )
    opens = pd.Series([100.0, 101.0, 200.0, 201.0], index=index)

    actual = _same_session_next_open(opens)

    assert actual.loc[index[0]] == 101.0
    assert pd.isna(actual.loc[index[1]])
    assert actual.loc[index[2]] == 201.0
    assert pd.isna(actual.loc[index[3]])


def test_same_session_next_open_rejects_unsorted_input():
    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-01-05 09:20", tz="Asia/Kolkata"),
            pd.Timestamp("2026-01-05 09:15", tz="Asia/Kolkata"),
        ]
    )
    try:
        _same_session_next_open(pd.Series([101.0, 100.0], index=index))
    except ValueError as exc:
        assert str(exc) == "open_prices must be sorted chronologically"
    else:
        raise AssertionError("unsorted next-open input must fail closed")


def test_build_vectorized_signals_does_not_change_earlier_rows_when_late_close_changes():
    sessions = []
    for offset in range(3):
        day = pd.Timestamp("2026-01-05", tz="Asia/Kolkata") + pd.Timedelta(
            days=offset
        )
        sessions.append(
            pd.date_range(
                day + pd.Timedelta(hours=9, minutes=15), periods=76, freq="5min"
            )
        )
    idx = sessions[0].append(sessions[1:])
    prices = np.linspace(100.0, 130.0, len(idx))
    base = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 1.0,
            "low": prices - 1.0,
            "close": prices,
            "volume": 1000.0,
        },
        index=idx,
    )
    mutated = base.copy()
    mutated.iloc[-1, mutated.columns.get_loc("close")] += 500.0

    config = SimpleNamespace(
        allowed_time_start="09:15",
        allowed_time_end="15:30",
        target_atr_mult=1.5,
        stop_atr_mult=1.0,
    )
    signals_base = build_vectorized_signals(base, config)
    signals_mutated = build_vectorized_signals(mutated, config)

    cutoff = idx[-2]
    assert base.iloc[-1]["close"] != mutated.iloc[-1]["close"]
    pd.testing.assert_frame_equal(
        signals_base.loc[signals_base.index <= cutoff],
        signals_mutated.loc[signals_mutated.index <= cutoff],
    )
