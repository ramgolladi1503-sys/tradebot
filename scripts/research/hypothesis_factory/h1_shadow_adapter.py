#!/usr/bin/env python3
"""H1 Trapped Push Snapback no-order shadow adapter utilities.

This module intentionally does not change the frozen H1 predicate.  It only
normalises completed NIFTY 5-minute index bars into the V19 forward-intake
schema and enforces zero-order shadow authority before the existing validator
and observer are called.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

CANDIDATE_ID = "H1_TRAPPED_PUSH_SNAPBACK"
FROZEN_PREDICATE_VERSION = "H1_V14_FROZEN"
FROZEN_PREDICATE = "(range_bps[t-1] > 12.0) & (upper_wick_bps[t-1] > 4.0) & (body_bps[t] < -2.0)"
SUPPORT_SCOPE = "OPENING_WINDOW_5MIN_OHLC_INDEX_BPS"

H1_COMPLETED_BAR_COLUMNS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume_optional",
    "source",
    "completed_bar",
    "timezone",
]

REQUIRED_KITE_OHLC_COLUMNS = ["open", "high", "low", "close"]


@dataclass(frozen=True)
class NoOrderShadowAuthority:
    """Authority flags that must remain disabled for H1 shadow observation."""

    paper_authorized: bool = False
    live_authorized: bool = False
    order_authority: bool = False
    broker_write_authority: bool = False

    def assert_safe(self) -> None:
        unsafe = {
            key: value
            for key, value in asdict(self).items()
            if bool(value)
        }
        if unsafe:
            raise ValueError(
                "UNSAFE_H1_SHADOW_AUTHORITY: H1 adapter is no-order only; "
                f"refusing enabled flags={sorted(unsafe)}"
            )


@dataclass(frozen=True)
class H1ShadowAdapterConfig:
    observation_date: str
    market_timezone: str = "Asia/Kolkata"
    keep_start: str = "09:15"
    opening_start: str = "09:15"
    opening_end: str = "11:30"
    keep_end: str = "12:00"
    source_label: str = "KITE_HISTORICAL_READ_ONLY"
    candidate_id: str = CANDIDATE_ID
    frozen_predicate_version: str = FROZEN_PREDICATE_VERSION

    def validate(self) -> None:
        datetime.strptime(self.observation_date, "%Y-%m-%d")
        if not (self.keep_start <= self.opening_start <= self.opening_end <= self.keep_end):
            raise ValueError(
                "INVALID_H1_SHADOW_WINDOW: expected keep_start <= opening_start "
                "<= opening_end <= keep_end"
            )


def _timestamp_column(frame: pd.DataFrame) -> str:
    for column in ("timestamp", "date", "datetime"):
        if column in frame.columns:
            return column
    raise ValueError("Input CSV must contain one timestamp column: timestamp, date, or datetime")


def _parse_to_market_time(series: pd.Series, market_timezone: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        bad_count = int(parsed.isna().sum())
        raise ValueError(f"INVALID_TIMESTAMP_VALUES: {bad_count} timestamp values could not be parsed")

    # Series.dt.tz is None for timezone-naive datetimes and a tzinfo otherwise.
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize(market_timezone)
    return parsed.dt.tz_convert(market_timezone)


def _validate_ohlc(frame: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_KITE_OHLC_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Input CSV missing OHLC columns: {missing}")

    for column in REQUIRED_KITE_OHLC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    invalid_numeric = int(frame[REQUIRED_KITE_OHLC_COLUMNS].isna().any(axis=1).sum())
    if invalid_numeric:
        raise ValueError(f"INVALID_OHLC_NUMERIC_VALUES: {invalid_numeric} rows have non-numeric OHLC")

    invalid_ohlc = frame[
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    ]
    if not invalid_ohlc.empty:
        raise ValueError(f"INVALID_OHLC_RELATIONSHIPS: {len(invalid_ohlc)} rows failed OHLC sanity")


def normalise_kite_intraday_csv(
    raw_csv_path: str | Path,
    output_csv_path: str | Path,
    config: H1ShadowAdapterConfig,
    *,
    authority: NoOrderShadowAuthority | None = None,
) -> dict[str, Any]:
    """Convert Kite intraday CSV output into the H1 completed-bar intake schema."""

    config.validate()
    (authority or NoOrderShadowAuthority()).assert_safe()

    raw_path = Path(raw_csv_path)
    out_path = Path(output_csv_path)
    frame = pd.read_csv(raw_path)

    ts_column = _timestamp_column(frame)
    _validate_ohlc(frame)

    dt_ist = _parse_to_market_time(frame[ts_column], config.market_timezone)
    frame = frame.copy()
    frame["_datetime_ist"] = dt_ist
    frame["_time_hhmm"] = dt_ist.dt.strftime("%H:%M")
    frame["_date"] = dt_ist.dt.strftime("%Y-%m-%d")

    in_scope = (
        (frame["_date"] == config.observation_date)
        & (frame["_time_hhmm"] >= config.keep_start)
        & (frame["_time_hhmm"] <= config.keep_end)
    )
    scoped = frame.loc[in_scope].copy()

    if scoped.empty:
        raise ValueError(
            "NO_H1_BARS_IN_SCOPE: no rows survived observation_date/keep window filtering"
        )

    output = pd.DataFrame(
        {
            "datetime": scoped["_datetime_ist"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "open": scoped["open"].astype(float),
            "high": scoped["high"].astype(float),
            "low": scoped["low"].astype(float),
            "close": scoped["close"].astype(float),
            "volume_optional": pd.to_numeric(scoped.get("volume", 0), errors="coerce").fillna(0.0),
            "source": config.source_label,
            "completed_bar": "true",
            "timezone": config.market_timezone,
        }
    )

    output["_sort_datetime"] = pd.to_datetime(output["datetime"])
    output = (
        output.sort_values("_sort_datetime")
        .drop_duplicates(subset=["datetime"], keep="last")
        .drop(columns=["_sort_datetime"])
        .reset_index(drop=True)
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    output[H1_COMPLETED_BAR_COLUMNS].to_csv(out_path, index=False)

    return {
        "schema_version": "H1_SHADOW_ADAPTER_NORMALIZATION_V1",
        "candidate_id": config.candidate_id,
        "frozen_predicate_version": config.frozen_predicate_version,
        "support_scope": SUPPORT_SCOPE,
        "source_raw_csv": str(raw_path),
        "output_csv": str(out_path),
        "observation_date": config.observation_date,
        "market_timezone": config.market_timezone,
        "keep_window_ist": f"{config.keep_start}-{config.keep_end}",
        "opening_scan_window_ist": f"{config.opening_start}-{config.opening_end}",
        "rows_in": int(len(frame)),
        "rows_out": int(len(output)),
        "first_timestamp_ist": str(output["datetime"].iloc[0]),
        "last_timestamp_ist": str(output["datetime"].iloc[-1]),
        "orders_created": 0,
        "broker_writes_created": 0,
        "authority_flags_all_false": True,
        "predicate_changed": False,
    }


def merge_h1_completed_bar_csvs(
    input_csv_paths: list[str | Path],
    output_csv_path: str | Path,
    config: H1ShadowAdapterConfig,
    *,
    authority: NoOrderShadowAuthority | None = None,
) -> dict[str, Any]:
    """Merge already-normalised H1 completed-bar CSVs, preserving the same schema."""

    config.validate()
    (authority or NoOrderShadowAuthority()).assert_safe()

    if not input_csv_paths:
        raise ValueError("At least one completed-bar CSV is required")

    frames = []
    for csv_path in input_csv_paths:
        path = Path(csv_path)
        frame = pd.read_csv(path)
        missing = [column for column in H1_COMPLETED_BAR_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"{path} missing H1 completed-bar columns: {missing}")
        frames.append(frame[H1_COMPLETED_BAR_COLUMNS].copy())

    combined = pd.concat(frames, ignore_index=True)
    combined["datetime"] = pd.to_datetime(combined["datetime"], errors="coerce")
    if combined["datetime"].isna().any():
        raise ValueError("INVALID_H1_COMPLETED_BAR_DATETIME: could not parse merged datetime")

    combined["_date"] = combined["datetime"].dt.strftime("%Y-%m-%d")
    combined["_time_hhmm"] = combined["datetime"].dt.strftime("%H:%M")
    in_scope = (
        (combined["_date"] == config.observation_date)
        & (combined["_time_hhmm"] >= config.keep_start)
        & (combined["_time_hhmm"] <= config.keep_end)
    )
    combined = combined.loc[in_scope].copy()
    if combined.empty:
        raise ValueError("NO_H1_COMPLETED_BARS_IN_MERGED_SCOPE")

    for column in REQUIRED_KITE_OHLC_COLUMNS:
        combined[column] = pd.to_numeric(combined[column], errors="coerce")
    _validate_ohlc(combined)

    combined = (
        combined.sort_values("datetime")
        .drop_duplicates(subset=["datetime"], keep="last")
        .reset_index(drop=True)
    )
    combined["datetime"] = combined["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    combined["completed_bar"] = "true"
    combined["timezone"] = config.market_timezone

    out_path = Path(output_csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined[H1_COMPLETED_BAR_COLUMNS].to_csv(out_path, index=False)

    return {
        "schema_version": "H1_SHADOW_ADAPTER_MERGE_V1",
        "candidate_id": config.candidate_id,
        "input_csvs": [str(Path(path)) for path in input_csv_paths],
        "output_csv": str(out_path),
        "observation_date": config.observation_date,
        "rows_out": int(len(combined)),
        "first_timestamp_ist": str(combined["datetime"].iloc[0]),
        "last_timestamp_ist": str(combined["datetime"].iloc[-1]),
        "orders_created": 0,
        "broker_writes_created": 0,
        "authority_flags_all_false": True,
        "predicate_changed": False,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_shadow_run_id(observation_date: str, prefix: str = "H1_SHADOW") -> str:
    datetime.strptime(observation_date, "%Y-%m-%d")
    return f"{prefix}_{observation_date.replace('-', '')}"
