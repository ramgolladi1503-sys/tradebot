from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.session_calendar import is_open
from scripts.run_market_event_graph_live_session_v1 import validate_nse_session_day


IST = ZoneInfo("Asia/Kolkata")


def test_weekday_session_day_is_independent_of_intraday_open_state():
    result = validate_nse_session_day(date(2026, 8, 4))
    assert result["session_day_allowed"] is True
    assert is_open(datetime(2026, 8, 4, 0, 0, tzinfo=IST), segment="NSE_FNO") is False
    assert is_open(datetime(2026, 8, 4, 9, 8, tzinfo=IST), segment="NSE_FNO") is False
    assert is_open(datetime(2026, 8, 4, 10, 0, tzinfo=IST), segment="NSE_FNO") is True


def test_weekend_is_not_a_session_day():
    assert validate_nse_session_day(date(2026, 8, 8))["session_day_allowed"] is False


def test_authoritative_nse_holiday_is_not_a_session_day():
    assert validate_nse_session_day(date(2026, 3, 3))["session_day_allowed"] is False
    assert validate_nse_session_day(date(2026, 3, 3))["listed_as_trading_holiday"] is True


def test_session_day_verification_retains_authoritative_source():
    result = validate_nse_session_day(date(2026, 8, 4))
    assert result["official_source"].startswith("https://nsearchives.nseindia.com/")
    assert result["verification_errors"] == []
