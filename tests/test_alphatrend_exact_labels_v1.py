import pandas as pd

from research.alphatrend_mechanism_v1 import add_forward_labels


def _bars(rows=40):
    timestamp = pd.date_range("2026-08-03 09:15", periods=rows, freq="min")
    values = [25000.0 + i for i in range(rows)]
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "session_date": "2026-08-03",
            "open": values,
            "high": [value + 1.0 for value in values],
            "low": [value - 1.0 for value in values],
            "close": values,
        }
    )


def test_exact_15_minute_endpoint_is_used():
    frame = _bars()
    out = add_forward_labels(frame, horizons=(15,))
    expected = (25015.0 / 25000.0 - 1.0) * 10000.0
    assert abs(out.loc[0, "fwd_ret_15_bps"] - expected) < 1e-12


def test_missing_intermediate_minute_invalidates_entire_horizon():
    frame = _bars()
    frame = frame.loc[frame["timestamp"] != pd.Timestamp("2026-08-03 09:25")].reset_index(drop=True)
    out = add_forward_labels(frame, horizons=(15,))
    first = out.loc[out["timestamp"] == pd.Timestamp("2026-08-03 09:15")].iloc[0]
    assert pd.isna(first["fwd_ret_15_bps"])
    assert pd.isna(first["fwd_high_15_bps"])
    assert pd.isna(first["fwd_low_15_bps"])


def test_horizon_does_not_bind_across_sessions_even_if_clock_gap_matches():
    day_one = _bars(rows=10)
    day_two = _bars(rows=10).copy()
    day_two["timestamp"] = pd.date_range("2026-08-04 09:15", periods=10, freq="min")
    day_two["session_date"] = "2026-08-04"
    out = add_forward_labels(pd.concat([day_one, day_two], ignore_index=True), horizons=(15,))
    assert out["fwd_ret_15_bps"].isna().all()
