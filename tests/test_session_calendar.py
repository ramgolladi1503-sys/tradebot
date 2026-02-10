from datetime import datetime
from zoneinfo import ZoneInfo

from core.session_calendar import minutes_since_open, minutes_to_close, is_open


def test_nse_fno_open_10am():
    tz = ZoneInfo("Asia/Kolkata")
    dt = datetime(2026, 2, 3, 10, 0, tzinfo=tz)
    assert is_open(dt, segment="NSE_FNO") is True


def test_nse_fno_closed_before_open():
    tz = ZoneInfo("Asia/Kolkata")
    dt = datetime(2026, 2, 3, 8, 59, tzinfo=tz)
    assert is_open(dt, segment="NSE_FNO") is False


def test_minutes_since_open():
    tz = ZoneInfo("Asia/Kolkata")
    dt = datetime(2026, 2, 3, 9, 16, tzinfo=tz)
    assert minutes_since_open(dt, segment="NSE_FNO") == 1


def test_minutes_to_close():
    tz = ZoneInfo("Asia/Kolkata")
    dt = datetime(2026, 2, 3, 15, 29, tzinfo=tz)
    assert minutes_to_close(dt, segment="NSE_FNO") == 1
