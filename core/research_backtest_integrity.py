from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_CANDLE = "CANDLE"
RESEARCH_NON_CANDLE_QUOTE = "NON_CANDLE_QUOTE"
_REQUIRED_CANDLE_COLUMNS = frozenset({"timestamp", "open", "high", "low", "close"})
_OHLC_COLUMNS = frozenset({"open", "high", "low", "close"})
_KNOWN_QUOTE_COLUMNS = frozenset({"ts", "token", "symbol", "ltp", "bid", "ask"})


def classify_research_parquet_columns(columns: Iterable[object]) -> str:
    """Classify replay parquets without treating quote/depth files as candles."""
    names = {str(column) for column in columns}
    if _REQUIRED_CANDLE_COLUMNS.issubset(names):
        return RESEARCH_CANDLE

    present_ohlc = sorted(_OHLC_COLUMNS.intersection(names))
    if present_ohlc:
        missing = sorted(_REQUIRED_CANDLE_COLUMNS.difference(names))
        raise ValueError(
            f"partial candle schema present_ohlc={present_ohlc} missing={missing}"
        )

    if _KNOWN_QUOTE_COLUMNS.issubset(names):
        return RESEARCH_NON_CANDLE_QUOTE

    raise ValueError(f"unrecognized research parquet schema: {sorted(names)}")


def normalize_research_candle_frame(
    frame: pd.DataFrame,
    *,
    source: str | Path | None = None,
) -> pd.DataFrame:
    """Return one deterministic, validated, start-labelled OHLC candle frame."""
    classification = classify_research_parquet_columns(frame.columns)
    if classification != RESEARCH_CANDLE:
        raise ValueError(
            f"non-candle parquet cannot be normalized as candles: {source or '<memory>'}"
        )
    if frame.empty:
        raise ValueError(f"candle parquet is empty: {source or '<memory>'}")

    normalized = frame.copy()
    timestamps = pd.to_datetime(normalized["timestamp"], errors="raise")
    if timestamps.isna().any():
        raise ValueError(f"candle timestamps contain nulls: {source or '<memory>'}")
    if timestamps.duplicated().any():
        raise ValueError(f"candle timestamps contain duplicates: {source or '<memory>'}")
    normalized["timestamp"] = timestamps

    for column in sorted(_OHLC_COLUMNS):
        numeric = pd.to_numeric(normalized[column], errors="raise")
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValueError(
                f"candle column {column} contains non-finite values: {source or '<memory>'}"
            )
        normalized[column] = numeric.astype(float)

    return normalized.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def resolve_research_candle_symbol(
    frame: pd.DataFrame,
    *,
    source: str | Path,
) -> str:
    """Resolve one symbol without truncating symbols that contain underscores."""
    if "symbol" in frame.columns:
        symbols = sorted(
            {
                str(value).strip()
                for value in frame["symbol"].dropna().tolist()
                if str(value).strip()
            }
        )
        if len(symbols) == 1:
            return symbols[0]
        if len(symbols) > 1:
            raise ValueError(f"candle parquet contains multiple symbols: {symbols}")

    stem = Path(source).stem
    if "_" not in stem:
        raise ValueError(f"cannot resolve symbol from candle filename: {source}")
    symbol, date_key = stem.rsplit("_", 1)
    if len(date_key) != 8 or not date_key.isdigit() or not symbol:
        raise ValueError(f"cannot resolve symbol from candle filename: {source}")
    return symbol


def load_research_candle_parquet(
    path: str | Path,
) -> tuple[str, pd.DataFrame | None, str | None]:
    """Load one parquet, returning explicit non-candle classification when safe."""
    source = Path(path)
    frame = pd.read_parquet(source)
    classification = classify_research_parquet_columns(frame.columns)
    if classification == RESEARCH_NON_CANDLE_QUOTE:
        return classification, None, None
    normalized = normalize_research_candle_frame(frame, source=source)
    symbol = resolve_research_candle_symbol(normalized, source=source)
    return classification, normalized, symbol


def causal_completed_htf_sma(
    close: pd.Series,
    *,
    period_minutes: int,
    window: int = 15,
) -> pd.Series:
    """Map an SMA of completed higher-timeframe closes to intraday rows.

    A row inside the currently-forming HTF bucket may only use HTF buckets that
    completed before that bucket began. Grouping by the floored bucket and
    shifting the bucket-level SMA by one enforces that contract for bar-open or
    bar-close labelled lower-timeframe rows without reading a future close from
    the same bucket.
    """
    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("close must use a DatetimeIndex")
    if period_minutes <= 0:
        raise ValueError("period_minutes must be positive")
    if window <= 0:
        raise ValueError("window must be positive")

    frequency = f"{int(period_minutes)}min"
    bucket_keys = close.index.floor(frequency)
    htf_close = close.groupby(bucket_keys).last()
    completed_htf_sma = htf_close.rolling(window, min_periods=window).mean().shift(1)
    return pd.Series(bucket_keys, index=close.index).map(completed_htf_sma).astype(float)


def is_immediate_next_bar(*, signal_bar_index: int, current_bar_index: int) -> bool:
    """Return whether current_bar_index is the only legal next-bar entry."""
    return int(current_bar_index) == int(signal_bar_index) + 1
