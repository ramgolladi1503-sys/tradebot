from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.time_utils import (
    now_ist,
    ist_date_key,
    within_window,
    get_market_phase_ist,
    parse_hhmm_time,
)


def test_now_ist_timezone():
    dt = now_ist()
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=5, minutes=30)


def test_ist_date_key():
    tz = ZoneInfo("Asia/Kolkata")
    dt = datetime(2026, 2, 11, 8, 59, tzinfo=tz)
    key = ist_date_key(dt)
    assert isinstance(key, str)
    assert key.count("-") == 2


def test_within_window():
    tz = ZoneInfo("Asia/Kolkata")
    base = datetime(2026, 2, 11, 9, 0, tzinfo=tz)
    assert within_window(base, target_hhmm="09:00", grace_minutes=10) is True
    assert within_window(base + timedelta(minutes=9), target_hhmm="09:00", grace_minutes=10) is True
    assert within_window(base + timedelta(minutes=11), target_hhmm="09:00", grace_minutes=10) is False
    assert within_window(base - timedelta(minutes=1), target_hhmm="09:00", grace_minutes=10) is False


def test_parse_hhmm_time():
    assert parse_hhmm_time("09:00") is not None
    assert parse_hhmm_time("09:15:30") is not None
    fallback = parse_hhmm_time("10:00")
    assert parse_hhmm_time("bad-value", default=fallback) == fallback


def test_get_market_phase_ist_boundaries():
    tz = ZoneInfo("Asia/Kolkata")
    pre = parse_hhmm_time("09:00")
    opn = parse_hhmm_time("09:15")
    cls = parse_hhmm_time("15:30")

    assert get_market_phase_ist(datetime(2026, 3, 2, 8, 59, 59, tzinfo=tz), premarket_start=pre, open_time=opn, close_time=cls) == "CLOSED"
    assert get_market_phase_ist(datetime(2026, 3, 2, 9, 0, 0, tzinfo=tz), premarket_start=pre, open_time=opn, close_time=cls) == "PREMARKET"
    assert get_market_phase_ist(datetime(2026, 3, 2, 9, 14, 59, tzinfo=tz), premarket_start=pre, open_time=opn, close_time=cls) == "PREMARKET"
    assert get_market_phase_ist(datetime(2026, 3, 2, 9, 15, 0, tzinfo=tz), premarket_start=pre, open_time=opn, close_time=cls) == "OPEN"
    assert get_market_phase_ist(datetime(2026, 3, 2, 15, 30, 0, tzinfo=tz), premarket_start=pre, open_time=opn, close_time=cls) == "OPEN"
    assert get_market_phase_ist(datetime(2026, 3, 2, 15, 30, 1, tzinfo=tz), premarket_start=pre, open_time=opn, close_time=cls) == "CLOSED"
