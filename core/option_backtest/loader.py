from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .models import OptionBacktestConfig

REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
)

STRICT_METADATA_COLUMNS = {
    "underlying": ("underlying", "underlying_symbol"),
    "option_type": ("option_type", "instrument_type", "type"),
    "strike": ("strike", "strike_price"),
    "expiry": ("expiry", "expiry_date"),
    "provider": ("provider", "source_provider"),
    "dataset_hash": ("dataset_hash", "source_dataset_hash", "dataset_version"),
    "bar_interval": ("bar_interval", "interval", "bar_size"),
}

QUOTE_TS_COLUMNS = ("quote_timestamp", "quote_ts", "quote_ts_epoch", "quote_timestamp_epoch")


def _normalize_timestamp(series: pd.Series, timezone: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        return ts.dt.tz_localize(timezone)
    return ts.dt.tz_convert(timezone)


def _has_explicit_time_component(value: str) -> bool:
    text = str(value or "").strip()
    return any(token in text for token in ("T", ":", "+"))


def _first_present_column(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _normalize_interval_minutes(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text.endswith("min"):
        text = text[:-3]
    elif text.endswith("m"):
        text = text[:-1]
    try:
        out = int(float(text))
        return out if out > 0 else None
    except Exception:
        return None


def _reject_invalid_price_geometry(df: pd.DataFrame) -> None:
    for column in ("open", "high", "low", "close"):
        if df[column].isna().any():
            raise ValueError(f"invalid_numeric_rows:{column}")
        if (df[column] <= 0).any():
            raise ValueError(f"nonpositive_price_rows:{column}")
    invalid_geometry = (
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df["low"] > df["high"])
    )
    if invalid_geometry.any():
        raise ValueError("invalid_ohlc_geometry")


def _reject_invalid_size_columns(df: pd.DataFrame) -> None:
    for column in ("volume", "oi"):
        if df[column].isna().any():
            raise ValueError(f"invalid_numeric_rows:{column}")
        if (df[column] < 0).any():
            raise ValueError(f"negative_size_rows:{column}")


def _reject_duplicate_timestamps(df: pd.DataFrame) -> None:
    if df["timestamp"].duplicated().any():
        raise ValueError("duplicate_timestamps")


def _validate_fixed_interval(df: pd.DataFrame, config: OptionBacktestConfig) -> None:
    if len(df) <= 1:
        return
    expected = pd.Timedelta(minutes=int(config.bar_interval_minutes))
    deltas = df["timestamp"].diff().dropna()
    if (deltas <= pd.Timedelta(0)).any():
        raise ValueError("non_monotonic_timestamps")
    if config.allow_missing_bars:
        return
    if (deltas != expected).any():
        raise ValueError("interval_gaps_detected")


def _validate_quote_columns(df: pd.DataFrame, config: OptionBacktestConfig) -> None:
    has_bid = "bid" in df.columns
    has_ask = "ask" in df.columns
    if has_bid != has_ask:
        raise ValueError("incomplete_quote_columns")
    if not has_bid:
        if config.require_bid_ask and config.strict_replay_contract:
            raise ValueError("missing_quote_columns")
        df["has_bid_ask"] = False
        return

    bid = pd.to_numeric(df["bid"], errors="coerce")
    ask = pd.to_numeric(df["ask"], errors="coerce")
    any_quote_present = bid.notna() | ask.notna()
    invalid_quote_rows = any_quote_present & (bid.isna() | ask.isna() | (bid <= 0) | (ask <= 0) | (ask < bid))
    if invalid_quote_rows.any():
        raise ValueError("invalid_bid_ask_rows")
    df["bid"] = bid
    df["ask"] = ask
    df["has_bid_ask"] = any_quote_present & (bid > 0) & (ask > 0) & (ask >= bid)
    if config.require_bid_ask and config.strict_replay_contract and (~df["has_bid_ask"]).any():
        raise ValueError("missing_required_bid_ask_rows")


def _validate_quote_timestamps(df: pd.DataFrame, config: OptionBacktestConfig) -> None:
    if not config.require_quote_timestamps:
        return
    quote_ts_column = _first_present_column(df, QUOTE_TS_COLUMNS)
    if quote_ts_column is None:
        raise ValueError("missing_quote_timestamp_column")
    raw_quote_ts = df[quote_ts_column]
    if quote_ts_column.endswith("_epoch") or quote_ts_column.endswith("ts_epoch"):
        quote_ts = pd.to_datetime(raw_quote_ts, unit="s", errors="coerce", utc=True).dt.tz_convert(config.timezone)
    else:
        quote_ts = _normalize_timestamp(raw_quote_ts, config.timezone)
    if quote_ts.isna().any():
        raise ValueError("invalid_quote_timestamp_rows")
    if (quote_ts > df["timestamp"]).any():
        raise ValueError("quote_after_candle_timestamp")
    if config.max_quote_age_seconds is not None:
        quote_age_seconds = (df["timestamp"] - quote_ts).dt.total_seconds()
        if (quote_age_seconds > float(config.max_quote_age_seconds)).any():
            raise ValueError("stale_quote_rows")
    df["quote_timestamp"] = quote_ts


def _validate_strict_metadata(df: pd.DataFrame, config: OptionBacktestConfig) -> None:
    if not config.require_contract_metadata:
        return
    resolved_columns: dict[str, str] = {}
    for field_name, aliases in STRICT_METADATA_COLUMNS.items():
        column = _first_present_column(df, aliases)
        if column is None:
            raise ValueError(f"missing_contract_metadata:{field_name}")
        resolved_columns[field_name] = column

    underlying_values = df[resolved_columns["underlying"]].astype(str).str.strip()
    if (underlying_values == "").any() or underlying_values.nunique(dropna=True) != 1:
        raise ValueError("invalid_underlying_metadata")

    option_values = df[resolved_columns["option_type"]].astype(str).str.strip().str.upper()
    if option_values.nunique(dropna=True) != 1 or option_values.iloc[0] not in {"CE", "CALL", "PE", "PUT"}:
        raise ValueError("invalid_option_type_metadata")

    strike_series = pd.to_numeric(df[resolved_columns["strike"]], errors="coerce")
    if strike_series.isna().any() or (strike_series <= 0).any() or strike_series.nunique(dropna=True) != 1:
        raise ValueError("invalid_strike_metadata")

    expiry_series = pd.to_datetime(df[resolved_columns["expiry"]], errors="coerce")
    if expiry_series.isna().any() or expiry_series.dt.normalize().nunique(dropna=True) != 1:
        raise ValueError("invalid_expiry_metadata")
    expiry_date = expiry_series.dt.normalize().iloc[0]
    if (df["timestamp"].dt.date > expiry_date.date()).any():
        raise ValueError("post_expiry_rows")

    if config.require_dataset_provenance:
        for field_name in ("provider", "dataset_hash"):
            values = df[resolved_columns[field_name]].astype(str).str.strip()
            if (values == "").any() or values.nunique(dropna=True) != 1:
                raise ValueError(f"invalid_contract_metadata:{field_name}")

    interval_value = df[resolved_columns["bar_interval"]].astype(str).str.strip().iloc[0]
    interval_minutes = _normalize_interval_minutes(interval_value)
    if interval_minutes != int(config.bar_interval_minutes):
        raise ValueError("unexpected_bar_interval")

    df.attrs["replay_contract"] = {
        "underlying": underlying_values.iloc[0],
        "option_type": option_values.iloc[0],
        "strike": float(strike_series.iloc[0]),
        "expiry": expiry_date.date().isoformat(),
        "provider": str(df[resolved_columns["provider"]].iloc[0]).strip(),
        "dataset_hash": str(df[resolved_columns["dataset_hash"]].iloc[0]).strip(),
        "bar_interval": interval_value,
    }


def load_option_symbol_csv(
    *,
    data_path: str | Path,
    symbol: str,
    date_from: str | None,
    date_to: str | None,
    timezone: str,
    config: OptionBacktestConfig | None = None,
) -> pd.DataFrame:
    config = config or OptionBacktestConfig(symbol=symbol, data_path=Path(data_path), timezone=timezone)
    df = pd.read_csv(Path(data_path))
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
        start_ts = start_ts.tz_localize(timezone) if start_ts.tzinfo is None else start_ts.tz_convert(timezone)
        df = df.loc[df["timestamp"] >= start_ts]
    if date_to:
        end_ts = pd.Timestamp(date_to)
        end_ts = end_ts.tz_localize(timezone) if end_ts.tzinfo is None else end_ts.tz_convert(timezone)
        if not _has_explicit_time_component(str(date_to)):
            end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        df = df.loc[df["timestamp"] <= end_ts]

    df = df.loc[df["symbol"].astype(str) == str(symbol)].copy()
    if df.empty:
        raise ValueError("no_rows_after_filters")

    for column in ("open", "high", "low", "close", "volume", "oi", "bid", "ask", "bid_qty", "ask_qty"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)
    _reject_invalid_price_geometry(df)
    _reject_invalid_size_columns(df)
    _reject_duplicate_timestamps(df)
    _validate_fixed_interval(df, config)
    _validate_quote_columns(df, config)
    _validate_quote_timestamps(df, config)
    _validate_strict_metadata(df, config)
    return df
