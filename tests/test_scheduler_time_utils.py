from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.time_utils import now_ist, ist_date_key, within_window


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
