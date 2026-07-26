from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    sha256_file,
)

IST = "Asia/Kolkata"
UNDERLYINGS = ("BANKNIFTY", "NIFTY", "SENSEX")
DATE_RE = re.compile(r"(20\d{2})-?(\d{2})-?(\d{2})")


def _date_from_path(path: Path) -> str:
    for part in path.parts:
        match = DATE_RE.search(part)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    raise ValueError(f"date_not_found:{path}")


def _normalize_ts(series: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(series, errors="coerce")
    if getattr(timestamps.dt, "tz", None) is None:
        return timestamps.dt.tz_localize(IST)
    return timestamps.dt.tz_convert(IST)


def _expected_bar_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    session_date = frame["timestamp"].iloc[0].date()
    start = pd.Timestamp(f"{session_date} 09:15:00", tz=IST)
    end = pd.Timestamp(f"{session_date} 15:30:00", tz=IST)
    return len(pd.date_range(start, end, freq="5min"))


def _load_underlying(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_parquet(path)
    timestamp_column = "date" if "date" in frame.columns else "timestamp"
    frame = frame.copy()
    frame["timestamp"] = _normalize_ts(frame[timestamp_column])
    for column in ("open", "high", "low", "close", "volume"):
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for flag in ("synthetic", "fallback", "mock"):
        if flag not in frame.columns:
            frame[flag] = True
    valid_geometry = (
        frame["timestamp"].notna()
        & (frame["open"] > 0)
        & (frame["high"] > 0)
        & (frame["low"] > 0)
        & (frame["close"] > 0)
        & (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["high"] >= frame["low"])
    )
    clean_flags = ~(
        frame["synthetic"].astype(bool)
        | frame["fallback"].astype(bool)
        | frame["mock"].astype(bool)
    )
    accepted = (
        frame.loc[valid_geometry & clean_flags]
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    interval = str(
        frame.get("interval", pd.Series(["UNKNOWN"]))
        .dropna()
        .astype(str)
        .iloc[0]
        if not frame.empty
        else "UNKNOWN"
    )
    expected = _expected_bar_count(accepted)
    actual = int(accepted.shape[0])
    summary = {
        "relative_path": "",
        "row_count": int(frame.shape[0]),
        "accepted_row_count": actual,
        "positive_ohlc_rows": int(valid_geometry.sum()),
        "invalid_ohlc_rows": int((~valid_geometry).sum()),
        "synthetic_true_rows": int(frame["synthetic"].astype(bool).sum()),
        "fallback_true_rows": int(frame["fallback"].astype(bool).sum()),
        "mock_true_rows": int(frame["mock"].astype(bool).sum()),
        "duplicate_timestamp_rows": int(frame["timestamp"].duplicated().sum()),
        "out_of_session_rows": (
            int(
                (accepted["timestamp"].dt.time < pd.Timestamp("09:15").time()).sum()
                + (accepted["timestamp"].dt.time > pd.Timestamp("15:30").time()).sum()
            )
            if not accepted.empty
            else 0
        ),
        "missing_bar_count": max(0, expected - actual),
        "minimum_timestamp": str(accepted["timestamp"].min()) if not accepted.empty else None,
        "maximum_timestamp": str(accepted["timestamp"].max()) if not accepted.empty else None,
        "bar_interval": interval,
        "timestamp_timezone": IST,
        "timestamp_semantics": "bar_start",
        "session_start": "09:15:00",
        "session_end": "15:30:00",
        "expected_bar_count": expected,
        "actual_bar_count": actual,
    }
    if actual == 0:
        summary["authority_classification"] = (
            "SYNTHETIC_OR_MOCK_ONLY" if int(clean_flags.sum()) == 0 else "MALFORMED"
        )
    elif actual < int(frame.shape[0]):
        summary["authority_classification"] = "PARTIAL_REAL_WITH_REJECTED_ROWS"
    else:
        summary["authority_classification"] = "REAL_KITE_UNDERLYING_CANDLES"
    return accepted, summary


def _normalize_instrument(frame: pd.DataFrame, path: Path) -> str:
    fallback = path.stem.split("_")[0]
    raw = str(
        frame.get("instrument", pd.Series([fallback])).iloc[0]
        if not frame.empty
        else fallback
    ).upper()
    if "BANKNIFTY" in raw:
        return "BANKNIFTY"
    if "SENSEX" in raw:
        return "SENSEX"
    return "NIFTY"


def audit_corpus(
    root: Path,
) -> tuple[
    dict[tuple[str, str], pd.DataFrame],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    files = sorted(Path(root).glob("*/underlying/*.parquet"))
    sessions: dict[tuple[str, str], pd.DataFrame] = {}
    by_file: list[dict[str, Any]] = []
    by_session: dict[tuple[str, str], dict[str, Any]] = {}
    rejected: defaultdict[str, int] = defaultdict(int)
    for path in files:
        try:
            frame, summary = _load_underlying(path)
            session_date = _date_from_path(path)
            instrument = _normalize_instrument(frame, path)
            source_hash = sha256_file(path)
            summary.update(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "date": session_date,
                    "index": instrument,
                    "source_file_id": source_hash[:16],
                }
            )
            by_file.append(summary)
            by_session[(session_date, instrument)] = {
                "date": session_date,
                "index": instrument,
                "bar_interval": summary["bar_interval"],
                "accepted_row_count": summary["accepted_row_count"],
                "missing_bar_count": summary["missing_bar_count"],
                "authority_classification": summary["authority_classification"],
                "source_file_id": summary["source_file_id"],
            }
            if (
                summary["authority_classification"]
                in {"REAL_KITE_UNDERLYING_CANDLES", "PARTIAL_REAL_WITH_REJECTED_ROWS"}
                and summary["bar_interval"] == "5minute"
            ):
                sessions[(session_date, instrument)] = frame
            for key in (
                "invalid_ohlc_rows",
                "synthetic_true_rows",
                "fallback_true_rows",
                "mock_true_rows",
                "duplicate_timestamp_rows",
            ):
                rejected[key] += int(summary[key])
        except Exception as exc:
            by_file.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "authority_classification": "MALFORMED",
                    "source_file_id": sha256_file(path)[:16],
                    "exact_reason": f"{type(exc).__name__}:{exc}",
                }
            )
    rejected_summary = {
        "schema_version": "kite_underlying_rejected_rows_summary_v1",
        **dict(rejected),
    }
    return (
        sessions,
        by_file,
        sorted(by_session.values(), key=lambda row: (row["index"], row["date"])),
        rejected_summary,
    )


def build_partitions(
    sessions: dict[tuple[str, str], pd.DataFrame],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "schema_version": "underlying_directional_partition_manifest_v1",
        "policy": "60/20/20 chronological per index",
        "holdout_outcomes_read": False,
        "indexes": {},
    }
    for index in UNDERLYINGS:
        dates = sorted(
            session_date for session_date, symbol in sessions if symbol == index
        )
        development_end = int(len(dates) * 0.6)
        validation_end = int(len(dates) * 0.8)
        output["indexes"][index] = {
            "ordered_dates": dates,
            "session_count": len(dates),
            "date_range": [dates[0], dates[-1]] if dates else [],
            "development_dates": dates[:development_end],
            "validation_dates": dates[development_end:validation_end],
            "holdout_dates": dates[validation_end:],
        }
    return output
