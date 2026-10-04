from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.market_calendar import IN_HOLIDAYS, NSE_FNO_2026_HOLIDAYS, NSE_FNO_HOLIDAY_SOURCE_BY_DATE
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


def test_preflight_and_shared_runtime_calendar_use_one_nse_fno_holiday_set():
    assert date(2026, 1, 15) in NSE_FNO_2026_HOLIDAYS
    assert set(NSE_FNO_2026_HOLIDAYS).issubset(set(IN_HOLIDAYS))
    for holiday in NSE_FNO_2026_HOLIDAYS:
        result = validate_nse_session_day(holiday)
        assert result["session_day_allowed"] is False
        assert result["listed_as_trading_holiday"] is True
        expected_source = NSE_FNO_HOLIDAY_SOURCE_BY_DATE.get(
            holiday, "https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf"
        )
        assert result["official_source"] == expected_source


def test_session_day_verification_retains_authoritative_source():
    result = validate_nse_session_day(date(2026, 8, 4))
    assert result["official_source"].startswith("https://nsearchives.nseindia.com/")
    assert result["verification_errors"] == []
