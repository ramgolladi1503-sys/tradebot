from __future__ import annotations

import pandas as pd


DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_EXPIRY_CUTOFF = "15:30:00"


def parse_ts(value: str, *, timezone: str = DEFAULT_TIMEZONE) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(value)
    except Exception as exc:
        raise ValueError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        return parsed.tz_localize(timezone)
    return parsed.tz_convert(timezone)


def expiry_cutoff_ts(expiry: str, *, timezone: str = DEFAULT_TIMEZONE, cutoff: str = DEFAULT_EXPIRY_CUTOFF) -> pd.Timestamp:
    try:
        expiry_date = pd.Timestamp(expiry).date()
    except Exception as exc:
        raise ValueError("invalid_expiry_date") from exc
    return pd.Timestamp(f"{expiry_date.isoformat()}T{cutoff}").tz_localize(timezone)
