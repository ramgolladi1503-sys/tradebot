from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
)


def _normalize_timestamp(series: pd.Series, timezone: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        return ts.dt.tz_localize(timezone)
    return ts.dt.tz_convert(timezone)


def load_option_symbol_csv(
    *,
    data_path: str | Path,
    symbol: str,
    date_from: str | None,
    date_to: str | None,
    timezone: str,
) -> pd.DataFrame:
    path = Path(data_path)
    df = pd.read_csv(path)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"missing_required_columns:{','.join(missing)}")

    df = df.copy()
    if "symbol" not in df.columns:
        df["symbol"] = symbol
    df["timestamp"] = _normalize_timestamp(df["timestamp"], timezone)
    if df["timestamp"].isna().any():
        raise ValueError("invalid_timestamp_rows")

    if date_from:
        start_ts = pd.Timestamp(date_from)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize(timezone)
        else:
            start_ts = start_ts.tz_convert(timezone)
        df = df.loc[df["timestamp"] >= start_ts]
    if date_to:
        end_ts = pd.Timestamp(date_to)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize(timezone)
        else:
            end_ts = end_ts.tz_convert(timezone)
        end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        df = df.loc[df["timestamp"] <= end_ts]

    df = df.loc[df["symbol"].astype(str) == str(symbol)].copy()
    if df.empty:
        raise ValueError("no_rows_after_filters")

    for column in ("open", "high", "low", "close", "volume", "oi", "bid", "ask"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["has_bid_ask"] = False
    if "bid" in df.columns and "ask" in df.columns:
        df["has_bid_ask"] = df["bid"].notna() & df["ask"].notna() & (df["bid"] > 0) & (df["ask"] > 0)

    return df.sort_values("timestamp").reset_index(drop=True)
