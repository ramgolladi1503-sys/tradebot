#!/usr/bin/env python3
import datetime
from typing import Tuple

def parse_iso_timestamp(ts_str: str) -> datetime.datetime | None:
    if not ts_str:
        return None
    cleaned = ts_str.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    cleaned = cleaned.replace(" ", "T")

    # Try parsing ISO standard formats
    try:
        return datetime.datetime.fromisoformat(cleaned)
    except Exception:
        pass

    # Try manual fallback formats
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(cleaned, fmt)
        except Exception:
            continue
    return None

def classify_session_position_window_v3(timestamp_str: str) -> Tuple[str | None, str | None]:
    dt = parse_iso_timestamp(timestamp_str)
    if dt is None:
        return None, "TIMESTAMP_PARSE_FAILED"

    # Market open: 09:15 IST (which corresponds to 03:45 UTC if UTC-naive)
    # The timestamps in canonical NIFTY.csv are ISO UTC formatted e.g. 2024-07-09T03:45:00
    minutes_since_midnight = dt.hour * 60 + dt.minute

    # Check UTC market open (03:45 UTC) vs IST market open (09:15 IST = 555 mins)
    if 3 * 60 + 45 <= minutes_since_midnight <= 10 * 60:
        minutes_since_open = minutes_since_midnight - (3 * 60 + 45)
    elif 9 * 60 + 15 <= minutes_since_midnight <= 15 * 60 + 30:
        minutes_since_open = minutes_since_midnight - (9 * 60 + 15)
    else:
        return None, "UNCLASSIFIABLE_WINDOW"

    if 0 <= minutes_since_open <= 30:
        return "OPENING_0_30", None
    if 30 < minutes_since_open <= 60:
        return "OPENING_30_60", None
    if 60 < minutes_since_open < 375 - 60:
        return "MID_SESSION", None
    if 375 - 60 <= minutes_since_open < 375 - 30:
        return "PRE_CLOSE_60", None
    if 375 - 30 <= minutes_since_open <= 375:
        return "PRE_CLOSE_30", None

    return None, "UNCLASSIFIABLE_WINDOW"
