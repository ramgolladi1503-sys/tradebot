from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from core.session_calendar import get_session
from core.time_utils import parse_ts_ist

IST_TZ = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class CanonicalSessionContext:
    canonical_session_bucket: str
    session_name: str
    segment: str
    ts_utc: str | None
    ts_ist: str | None


def _coerce_ist_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        return dt.astimezone(IST_TZ)
    if isinstance(value, str):
        text = value.strip()
        if text and "+" not in text and "Z" not in text:
            try:
                return datetime.fromisoformat(text).replace(tzinfo=IST_TZ).astimezone(IST_TZ)
            except Exception:
                pass
    dt = parse_ts_ist(value)
    if dt is None:
        try:
            numeric = float(value)
        except Exception:
            return None
        if numeric <= 0:
            return None
        dt = datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(IST_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_TZ)
    return dt.astimezone(IST_TZ)


def resolve_canonical_session_context(
    timestamp: Any,
    *,
    symbol: str | None = None,
    segment: str | None = None,
    is_expiry_day: bool = False,
    is_event_mode: bool = False,
) -> CanonicalSessionContext:
    """
    Resolve the canonical entropy session bucket from a timestamp.

    This is read-only classification logic. It does not mutate runtime state.
    """
    dt_ist = _coerce_ist_dt(timestamp)
    ts_utc = None
    ts_ist = None
    if dt_ist is not None:
        ts_ist = dt_ist.isoformat()
        ts_utc = dt_ist.astimezone(timezone.utc).isoformat()

    if is_event_mode:
        return CanonicalSessionContext(
            canonical_session_bucket="EVENT_MODE",
            session_name="event",
            segment=str(segment or "NSE_FNO"),
            ts_utc=ts_utc,
            ts_ist=ts_ist,
        )
    if is_expiry_day:
        return CanonicalSessionContext(
            canonical_session_bucket="EXPIRY_DAY",
            session_name="expiry",
            segment=str(segment or "NSE_FNO"),
            ts_utc=ts_utc,
            ts_ist=ts_ist,
        )

    sess = get_session(segment or "NSE_FNO")
    if dt_ist is None:
        return CanonicalSessionContext(
            canonical_session_bucket="DEFAULT",
            session_name=sess.name,
            segment=str(segment or sess.segment),
            ts_utc=ts_utc,
            ts_ist=ts_ist,
        )

    if dt_ist.weekday() >= 5:
        bucket = "DEFAULT"
    else:
        open_dt = dt_ist.replace(hour=sess.open_time.hour, minute=sess.open_time.minute, second=0, microsecond=0)
        close_dt = dt_ist.replace(hour=sess.close_time.hour, minute=sess.close_time.minute, second=0, microsecond=0)
        open_discovery_end = open_dt + timedelta(minutes=15)
        closing_vol_start = close_dt - timedelta(minutes=30)
        if dt_ist < open_dt:
            bucket = "DEFAULT"
        elif dt_ist < open_discovery_end:
            bucket = "OPEN_DISCOVERY"
        elif dt_ist >= closing_vol_start:
            bucket = "CLOSING_VOL"
        else:
            bucket = "MID_SESSION"

    return CanonicalSessionContext(
        canonical_session_bucket=bucket,
        session_name=sess.name,
        segment=str(segment or sess.segment),
        ts_utc=ts_utc,
        ts_ist=ts_ist,
    )
