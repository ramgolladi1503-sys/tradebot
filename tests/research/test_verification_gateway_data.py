"""Synthetic-only Pandera fixture tests. No historical outcome access."""
import pandas as pd
import pytest
from research.verification_gateway.data_checks import inspect_ohlcv_fixture, validate_ohlcv_fixture


def fixture():
    times = pd.to_datetime(["2026-09-27T09:15:00+05:30", "2026-09-27T09:20:00+05:30"], utc=True)
    return pd.DataFrame({
        "instrument_id": ["NIFTY", "NIFTY"],
        "contract_id": ["NIFTY-INDEX", "NIFTY-INDEX"],
        "event_time": times, "available_time": times + pd.Timedelta(1, unit="s"),
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
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_TIMES_WITHIN_CONTRACT"):
        validate_ohlcv_fixture(f)


def test_negative_availability_lag():
    f = fixture()
    f.loc[0, "available_time"] = f.loc[0, "event_time"] - pd.Timedelta(1, unit="s")
    with pytest.raises(ValueError, match="AVAILABILITY_BEFORE_EVENT"):
        validate_ohlcv_fixture(f)


def test_naive_timestamps_are_rejected():
    f = fixture()
    f["event_time"] = f["event_time"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="NAIVE_EVENT_TIME"):
        validate_ohlcv_fixture(f)


def test_same_timestamp_on_distinct_contracts_is_valid():
    f = fixture()
    second = f.iloc[[0]].copy()
    second["instrument_id"] = "BANKNIFTY"
    second["contract_id"] = "BANKNIFTY-INDEX"
    f = pd.concat([f, second], ignore_index=True).sort_values(
        ["instrument_id", "event_time"], ignore_index=True
    )
    assert len(validate_ohlcv_fixture(f)) == 3


def test_contract_identity_is_required():
    f = fixture().drop(columns=["contract_id"])
    with pytest.raises(Exception):
        validate_ohlcv_fixture(f)


@pytest.mark.parametrize("column,value", [
    ("open", float("inf")), ("high", float("-inf")),
    ("low", float("nan")), ("close", float("inf")),
    ("volume", float("inf")),
])
def test_nonfinite_ohlcv_is_rejected(column, value):
    f = fixture()
    f.loc[0, column] = value
    with pytest.raises(ValueError, match="NONFINITE_OHLCV"):
        validate_ohlcv_fixture(f)


@pytest.mark.parametrize("column,value", [
    ("instrument_id", ""), ("instrument_id", " NIFTY"),
    ("contract_id", "   "), ("contract_id", "NIFTY-INDEX "),
])
def test_blank_or_untrimmed_identity_is_rejected(column, value):
    f = fixture()
    f.loc[0, column] = value
    with pytest.raises(ValueError, match=f"INVALID_{column.upper()}"):
        validate_ohlcv_fixture(f)


def test_shape_pass_does_not_claim_source_or_execution_authority():
    report = inspect_ohlcv_fixture(fixture())
    assert report.data_shape == "DATA_SHAPE_PASS"
    assert report.source_authenticated == "NOT_VERIFIED"
    assert report.execution_quotes_available == "NOT_VERIFIED"


def test_shape_failure_is_reported_without_authority_promotion():
    f = fixture()
    f.loc[0, "low"] = 105.0
    report = inspect_ohlcv_fixture(f)
    assert report.data_shape == "DATA_SHAPE_BLOCK"
    assert report.source_authenticated == "NOT_VERIFIED"
    assert report.execution_quotes_available == "NOT_VERIFIED"
