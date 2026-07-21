from __future__ import annotations

import pandas as pd
import pytest

from research.opening_dislocation_reversal.fresh_epoch_reconciliation_v3 import (
    conservation_pass,
    normalize_provider_timestamps,
    ohlc_valid,
)


def test_exact_raw_row_conservation_passes_only_with_zero_unresolved():
    counts = {
        "raw_rows": 92896,
        "accepted_regular_session_rows": 92250,
        "outside_regular_session_rows": 274,
        "duplicate_rows": 0,
        "invalid_ohlc_rows": 0,
        "wrong_instrument_rows": 0,
        "unparsable_timestamp_rows": 0,
        "nonstandard_session_rows": 0,
        "incomplete_session_rows_retained_for_diagnosis": 372,
        "other_explicitly_classified_rows": 0,
        "unresolved_rows": 0,
    }
    assert conservation_pass(counts) is True


def test_unresolved_row_failure():
    counts = {
        "raw_rows": 2,
        "accepted_regular_session_rows": 1,
        "outside_regular_session_rows": 0,
        "duplicate_rows": 0,
        "invalid_ohlc_rows": 0,
        "wrong_instrument_rows": 0,
        "unparsable_timestamp_rows": 0,
        "nonstandard_session_rows": 0,
        "incomplete_session_rows_retained_for_diagnosis": 0,
        "other_explicitly_classified_rows": 0,
        "unresolved_rows": 1,
    }
    assert conservation_pass(counts) is False


def test_timezone_normalization_rejects_naive_timestamps():
    with pytest.raises(ValueError, match="naive_provider_timestamp"):
        normalize_provider_timestamps(pd.Series(["2022-01-03 09:15:00"]))


def test_date_grouping_after_timezone_normalization():
    out = normalize_provider_timestamps(pd.Series(["2022-01-03T03:45:00+00:00"]))
    assert out.dt.strftime("%Y-%m-%d %H:%M:%S%z").iloc[0] == "2022-01-03 09:15:00+0530"


def test_ohlc_validation_catches_bad_high_low_relationship():
    frame = pd.DataFrame([{"open": 10, "high": 9, "low": 8, "close": 10}])
    assert bool(ohlc_valid(frame).iloc[0]) is False
