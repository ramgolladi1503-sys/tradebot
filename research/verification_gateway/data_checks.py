"""Optional Pandera input checks for isolated research fixtures.

These checks concern shape, types and ordering, not data authority or market
truth. Do not pass them as evidence of point-in-time accuracy or fillability.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from typing import Literal


@dataclass(frozen=True)
class FixtureValidationReport:
    """Shape outcome kept separate from source and execution authority."""

    data_shape: Literal["DATA_SHAPE_PASS", "DATA_SHAPE_BLOCK"]
    source_authenticated: Literal["NOT_VERIFIED"]
    execution_quotes_available: Literal["NOT_VERIFIED"]
    issues: tuple[str, ...] = ()


def validate_ohlcv_fixture(df):
    import pandas as pd
    import pandera.pandas as pa

    schema = pa.DataFrameSchema(
        {
            "instrument_id": pa.Column(str, nullable=False),
            "contract_id": pa.Column(str, nullable=False),
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
    for column in ("event_time", "available_time"):
        if column not in df.columns or not pd.api.types.is_datetime64_any_dtype(df[column]):
            raise ValueError(f"INVALID_{column.upper()}_TYPE")
        if df[column].dt.tz is None:
            raise ValueError(f"NAIVE_{column.upper()}")
    required_numeric = ("open", "high", "low", "close", "volume")
    if not set(required_numeric).issubset(df.columns):
        raise ValueError("MISSING_OHLCV_COLUMNS")
    try:
        raw_numeric = df[list(required_numeric)].to_numpy(dtype=float)
    except (TypeError, ValueError):
        raise ValueError("INVALID_OHLCV_NUMERIC") from None
    if not np.isfinite(raw_numeric).all():
        raise ValueError("NONFINITE_OHLCV")
    valid = schema.validate(df, lazy=True)
    if valid.empty:
        raise ValueError("EMPTY_DATA")
    for column in ("instrument_id", "contract_id"):
        identities = valid[column]
        if identities.str.strip().eq("").any() or identities.ne(identities.str.strip()).any():
            raise ValueError(f"INVALID_{column.upper()}")
    price_columns = ("open", "high", "low", "close", "volume")
    try:
        numeric_values = valid[list(price_columns)].to_numpy(dtype=float)
    except (TypeError, ValueError):
        raise ValueError("INVALID_OHLCV_NUMERIC") from None
    if not np.isfinite(numeric_values).all():
        raise ValueError("NONFINITE_OHLCV")
    if (valid["available_time"] < valid["event_time"]).any():
        raise ValueError("AVAILABILITY_BEFORE_EVENT")
    identity = ["instrument_id", "contract_id"]
    if valid.duplicated([*identity, "event_time"]).any():
        raise ValueError("DUPLICATE_EVENT_TIMES_WITHIN_CONTRACT")
    for _, group in valid.groupby(identity, sort=False, dropna=False):
        if not group["event_time"].is_monotonic_increasing:
            raise ValueError("NONMONOTONIC_EVENT_TIMES_WITHIN_CONTRACT")
    if (valid["low"] > valid["high"]).any():
        raise ValueError("INVALID_HIGH_LOW")
    if ((valid["open"] < valid["low"]) | (valid["open"] > valid["high"]) |
        (valid["close"] < valid["low"]) | (valid["close"] > valid["high"])).any():
        raise ValueError("OHLC_OUTSIDE_RANGE")
    return valid


def inspect_ohlcv_fixture(df) -> FixtureValidationReport:
    """Report shape separately; input alone cannot authenticate provenance.

    This function deliberately does not infer source authenticity or option /
    execution quote availability from a valid OHLCV schema.
    """
    try:
        validate_ohlcv_fixture(df)
    except Exception as exc:
        return FixtureValidationReport(
            data_shape="DATA_SHAPE_BLOCK",
            source_authenticated="NOT_VERIFIED",
            execution_quotes_available="NOT_VERIFIED",
            issues=(type(exc).__name__, str(exc)),
        )
    return FixtureValidationReport(
        data_shape="DATA_SHAPE_PASS",
        source_authenticated="NOT_VERIFIED",
        execution_quotes_available="NOT_VERIFIED",
    )
