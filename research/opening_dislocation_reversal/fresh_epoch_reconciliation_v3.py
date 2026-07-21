from __future__ import annotations

import hashlib
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


REGULAR_START = time(9, 15)
REGULAR_END = time(15, 29)
STANDARD_MINUTE_COUNT = 375

NSE_2022_WEEKDAY_HOLIDAYS = {
    "2022-01-26": "Republic Day",
    "2022-03-01": "Mahashivratri",
    "2022-03-18": "Holi",
    "2022-04-14": "Mahavir Jayanti / Dr.Baba Saheb Ambedkar Jayanti",
    "2022-04-15": "Good Friday",
    "2022-05-03": "Id-Ul-Fitr",
    "2022-08-09": "Muharram",
    "2022-08-15": "Independence Day",
    "2022-08-31": "Ganesh Chaturthi",
    "2022-10-05": "Dussehra",
    "2022-10-26": "Diwali-Balipratipada",
    "2022-11-08": "Gurunanak Jayanti",
}

NSE_2022_NONSTANDARD_SPECIAL_SESSIONS = {
    "2022-10-24": "Diwali Muhurat Trading",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_minute_grid(session_date: str) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{session_date} 09:15:00", tz="Asia/Kolkata")
    return pd.date_range(start=start, periods=STANDARD_MINUTE_COUNT, freq="min")


def normalize_provider_timestamps(series: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(series)
    if timestamps.dt.tz is None:
        raise ValueError("naive_provider_timestamp")
    return timestamps.dt.tz_convert("Asia/Kolkata")


def classify_calendar_date(day: date) -> str:
    iso = day.isoformat()
    if day.weekday() >= 5:
        return "WEEKEND"
    if iso in NSE_2022_NONSTANDARD_SPECIAL_SESSIONS:
        return "NONSTANDARD_SPECIAL_SESSION"
    if iso in NSE_2022_WEEKDAY_HOLIDAYS:
        return "OFFICIAL_HOLIDAY"
    return "EXPECTED_REGULAR_SESSION"


def expected_calendar_2022() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cursor = date(2022, 1, 1)
    end = date(2022, 12, 30)
    while cursor <= end:
        rows.append({"date": cursor.isoformat(), "classification": classify_calendar_date(cursor)})
        cursor += timedelta(days=1)
    return rows


def ohlc_valid(frame: pd.DataFrame) -> pd.Series:
    numeric = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    finite_positive = numeric.notna().all(axis=1) & (numeric > 0).all(axis=1)
    high_valid = numeric["high"] >= numeric[["open", "low", "close"]].max(axis=1)
    low_valid = numeric["low"] <= numeric[["open", "high", "close"]].min(axis=1)
    return finite_positive & high_valid & low_valid


def classify_session(row_count: int, duplicate_count: int, invalid_ohlc_count: int) -> str:
    if invalid_ohlc_count:
        return "INVALID_OHLC"
    if duplicate_count:
        return "DUPLICATE_TIMESTAMPS"
    if row_count == STANDARD_MINUTE_COUNT:
        return "COMPLETE_STANDARD_SESSION"
    if row_count < STANDARD_MINUTE_COUNT:
        return "INCOMPLETE_MISSING_MINUTES"
    return "EXTRA_REGULAR_SESSION_MINUTES"


def conservation_pass(counts: dict[str, int]) -> bool:
    classified = (
        counts["accepted_regular_session_rows"]
        + counts["outside_regular_session_rows"]
        + counts["duplicate_rows"]
        + counts["invalid_ohlc_rows"]
        + counts["wrong_instrument_rows"]
        + counts["unparsable_timestamp_rows"]
        + counts["nonstandard_session_rows"]
        + counts["incomplete_session_rows_retained_for_diagnosis"]
        + counts["other_explicitly_classified_rows"]
    )
    return counts["raw_rows"] == classified and counts["unresolved_rows"] == 0


def semantic_session_hash(frame: pd.DataFrame) -> str:
    cols = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]
    normalized = frame.loc[:, cols].copy()
    normalized["timestamp"] = normalize_provider_timestamps(normalized["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    data = normalized.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def reject_local_source(path: str, metadata: dict[str, Any]) -> str:
    haystack = " ".join([path, *(str(v) for v in metadata.values())]).lower()
    if "option" in haystack:
        return "REJECT_OPTION_DATA"
    if "future" in haystack or "fut" in haystack:
        return "REJECT_FUTURES_DATA"
    if "etf" in haystack:
        return "REJECT_ETF_DATA"
    if "nifty" not in haystack:
        return "REJECT_NOT_NIFTY_CASH_INDEX"
    return "REQUIRES_MANUAL_PROVENANCE_REVIEW"


def compatibility_contract() -> dict[str, Any]:
    return {
        "minimum_overlap_sessions": 60,
        "preferred_overlap_sessions": 120,
        "session_date_agreement": "100%",
        "timestamp_grid_agreement": "100%",
        "median_absolute_close_difference_max_points": 1,
        "p99_absolute_close_difference_max_points": 5,
        "daily_close_difference_max_points": 2,
        "daily_close_difference_required_session_pct": 99,
        "gate_immutability": "FROZEN_BEFORE_PROVIDER_COMPARISON",
        "provider_mixing_allowed_before_pass": False,
    }
