from __future__ import annotations

# Migration note:
# Use compute_age_sec(ts_epoch, now_epoch) for deterministic age calculations.

from datetime import datetime, timedelta, timezone, time as dt_time
from zoneinfo import ZoneInfo
from typing import Any, Optional

from core.session_calendar import is_open, get_session

IST_TZ = ZoneInfo("Asia/Kolkata")


def now_utc_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def normalize_epoch_seconds(value: Any) -> Optional[float]:
    """
    Normalize epoch-like values to UTC seconds.

    Accepts:
    - seconds epoch (float/int)
    - milliseconds epoch (int/float)
    - microseconds epoch (int/float)
    - datetime / ISO-8601 strings (via _coerce_dt_utc)
    """
    if value is None:
        return None
    dt_utc = _coerce_dt_utc(value)
    if dt_utc is not None:
        return dt_utc.timestamp()
    try:
        raw = float(value)
    except Exception:
        return None
    if raw <= 0:
        return None
    abs_raw = abs(raw)
    if abs_raw >= 1e15:
        raw = raw / 1_000_000.0
    elif abs_raw >= 1e12:
        raw = raw / 1_000.0
    return raw


def compute_age_sec(ts_epoch: Any, now_epoch: Any) -> Optional[float]:
    """
    Deterministically compute non-negative age in seconds from epoch-like inputs.
    Returns None when either side cannot be normalized.
    """
    ts_norm = normalize_epoch_seconds(ts_epoch)
    now_norm = normalize_epoch_seconds(now_epoch)
    if ts_norm is None or now_norm is None:
        return None
    age = float(now_norm) - float(ts_norm)
    if age < 0:
        return 0.0
    return age


def now_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST_TZ)


def to_ist(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST_TZ)


def ist_date_key(now: Optional[datetime] = None) -> str:
    now = now or now_ist()
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST_TZ)
    return now.date().isoformat()


def within_window(
    now: Optional[datetime] = None,
    target_hhmm: str = "09:00",
    grace_minutes: int = 10,
) -> bool:
    now = now or now_ist()
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST_TZ)
    try:
        hh, mm = [int(x) for x in target_hhmm.split(":", 1)]
    except Exception:
        hh, mm = 9, 0
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < target:
        return False
    return (now - target).total_seconds() <= max(0, grace_minutes) * 60


def _coerce_dt_utc(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except Exception:
            return None
    elif isinstance(ts, str):
        s = ts.strip()
        if not s:
            return None
        if "-" not in s and "/" not in s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            try:
                from dateutil import parser as _parser  # type: ignore
                dt = _parser.parse(s)
            except Exception:
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def parse_ts_ist(ts: Any) -> Optional[datetime]:
    dt_utc = _coerce_dt_utc(ts)
    if dt_utc is None:
        return None
    return to_ist(dt_utc)


def is_today_ist(ts: Any, now: Optional[datetime] = None) -> bool:
    dt = parse_ts_ist(ts)
    if dt is None:
        return False
    now = now or now_ist()
    return dt.date() == now.date()


def age_minutes_ist(ts: Any, now: Optional[datetime] = None) -> Optional[float]:
    dt = parse_ts_ist(ts)
    if dt is None:
        return None
    now = now or now_ist()
    return (now - dt).total_seconds() / 60.0


def is_market_open_ist(
    now: Optional[datetime] = None,
    open_time: dt_time | None = None,
    close_time: dt_time | None = None,
    segment: str | None = None,
) -> bool:
    now = now or now_ist()
    if open_time or close_time:
        # Backward-compatible override, but prefer session calendar.
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST_TZ)
        if now.weekday() >= 5:
            return False
        open_time = open_time or dt_time(9, 15)
        close_time = close_time or dt_time(15, 30)
        open_dt = now.replace(hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0)
        close_dt = now.replace(hour=close_time.hour, minute=close_time.minute, second=0, microsecond=0)
        return open_dt <= now <= close_dt
    return is_open(now, segment=segment or get_session().segment)


def next_market_open_ist(now: Optional[datetime] = None) -> datetime:
    now = now or now_ist()
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST_TZ)
    sess = get_session()
    open_time = sess.open_time
    candidate = now.replace(hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0)
    if is_market_open_ist(now=now):
        return candidate
    if now < candidate and now.weekday() < 5:
        return candidate
    days_ahead = 1
    while True:
        nxt = (now + timedelta(days=days_ahead)).replace(
            hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0
        )
        if nxt.weekday() < 5:
            return nxt
        days_ahead += 1


# Backward-compatible aliases (deprecated names)
def now_local() -> datetime:
    return now_ist()


def parse_ts_local(ts: Any) -> Optional[datetime]:
    return parse_ts_ist(ts)


def is_today_local(ts: Any, now: Optional[datetime] = None) -> bool:
    return is_today_ist(ts, now=now)


def age_minutes_local(ts: Any, now: Optional[datetime] = None) -> Optional[float]:
    return age_minutes_ist(ts, now=now)

# Backward-compat alias (some modules import ist_now)
try:
    ist_now  # noqa: F401
except NameError:
    try:
        ist_now = now_ist  # type: ignore
    except NameError:
        def ist_now() -> datetime:
            return datetime.now(timezone.utc).astimezone(IST_TZ)
