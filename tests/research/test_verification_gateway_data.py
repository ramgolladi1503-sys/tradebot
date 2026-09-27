"""Synthetic-only Pandera fixture tests. No historical outcome access."""
import pandas as pd
import pytest
from research.verification_gateway.data_checks import validate_ohlcv_fixture


def fixture():
    times = pd.to_datetime(["2026-09-27T09:15:00", "2026-09-27T09:20:00"])
    return pd.DataFrame({
        "event_time": times, "available_time": times + pd.Timedelta(seconds=1),
        "open": [100.0, 101.0], "high": [102.0, 103.0],
        "low": [99.0, 100.0], "close": [101.0, 102.0],
        "volume": [20.0, 30.0],
    })


def test_valid_fixture():
    assert len(validate_ohlcv_fixture(fixture())) == 2


@pytest.mark.parametrize("column,value,error", [
    ("volume", -1.0, None),
    ("high", 90.0, "INVALID_HIGH_LOW"),
])
def test_invalid_numeric(column, value, error):
    f = fixture()
    f.loc[0, column] = value
    with pytest.raises(Exception, match=error) if error else pytest.raises(Exception):
        validate_ohlcv_fixture(f)


def test_duplicate_times():
    f = fixture()
    f.loc[1, "event_time"] = f.loc[0, "event_time"]
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_TIMES"):
        validate_ohlcv_fixture(f)


def test_negative_availability_lag():
    f = fixture()
    f.loc[0, "available_time"] = f.loc[0, "event_time"] - pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="AVAILABILITY_BEFORE_EVENT"):
        validate_ohlcv_fixture(f)
