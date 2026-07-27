from __future__ import annotations

import pandas as pd

from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1 import underlying_corpus


def test_naive_parquet_timestamp_is_utc_authority_then_converted_to_ist() -> None:
    series = pd.Series(["2026-01-02 03:45:00"])
    converted = underlying_corpus._normalize_ts(series)
    assert str(converted.iloc[0]) == "2026-01-02 09:15:00+05:30"


def test_timezone_aware_timestamp_is_converted_without_double_localization() -> None:
    series = pd.Series(["2026-01-02T09:15:00+05:30"])
    converted = underlying_corpus._normalize_ts(series)
    assert str(converted.iloc[0]) == "2026-01-02 09:15:00+05:30"


def test_regular_nse_session_has_75_five_minute_bar_starts() -> None:
    timestamps = pd.date_range(
        "2026-01-02 09:15:00", "2026-01-02 15:25:00", freq="5min", tz="Asia/Kolkata"
    )
    frame = pd.DataFrame({"timestamp": timestamps})
    assert len(timestamps) == 75
    assert underlying_corpus._expected_bar_count(frame) == 75


def test_muhurat_session_is_explicitly_unsupported() -> None:
    assert underlying_corpus.UNSUPPORTED_SPECIAL_SESSIONS["2024-11-01"] == (
        "MUHURAT_SESSION_DIFFERENT_TRADING_HOURS"
    )
