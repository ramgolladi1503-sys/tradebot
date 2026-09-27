"""Optional Pandera input checks for isolated research fixtures.

These checks concern shape, types and ordering, not data authority or market
truth. Do not pass them as evidence of point-in-time accuracy or fillability.
"""
from __future__ import annotations


def validate_ohlcv_fixture(df):
    import pandas as pd
    import pandera.pandas as pa

    schema = pa.DataFrameSchema(
        {
            "event_time": pa.Column(pa.DateTime, nullable=False),
            "available_time": pa.Column(pa.DateTime, nullable=False),
            "open": pa.Column(float, nullable=False, coerce=True),
            "high": pa.Column(float, nullable=False, coerce=True),
            "low": pa.Column(float, nullable=False, coerce=True),
            "close": pa.Column(float, nullable=False, coerce=True),
            "volume": pa.Column(float, nullable=False, coerce=True,
                                checks=pa.Check.ge(0)),
        },
        strict=False,
        coerce=False,
    )
    valid = schema.validate(df, lazy=True)
    if valid.empty:
        raise ValueError("EMPTY_DATA")
    if valid["event_time"].duplicated().any():
        raise ValueError("DUPLICATE_EVENT_TIMES")
    if not valid["event_time"].is_monotonic_increasing:
        raise ValueError("NONMONOTONIC_EVENT_TIMES")
    if (valid["available_time"] < valid["event_time"]).any():
        raise ValueError("AVAILABILITY_BEFORE_EVENT")
    if (valid["low"] > valid["high"]).any():
        raise ValueError("INVALID_HIGH_LOW")
    if ((valid["open"] < valid["low"]) | (valid["open"] > valid["high"]) |
        (valid["close"] < valid["low"]) | (valid["close"] > valid["high"])).any():
        raise ValueError("OHLC_OUTSIDE_RANGE")
    return valid
