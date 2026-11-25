"""Expiry calendar regression tests for shared schedule and session consumers."""

from __future__ import annotations

import datetime

from core.expiry_calendar_resolver import ExpiryCalendarResolver


class TestExpiryCalendarResolver:
    def test_pre_september_2025_thursday_expiry(self):
        """Test old era Thursday expiry resolution."""
        resolver = ExpiryCalendarResolver()
        # 2024-10-31 is Thursday
        res = resolver.classify_session(datetime.date(2024, 10, 31))
        assert res.is_nifty_expiry is True
        assert res.day_name == "Thursday"
        assert res.fallback_from_holiday is False

    def test_post_september_2025_tuesday_expiry(self):
        """Test new era Tuesday expiry resolution."""
        resolver = ExpiryCalendarResolver()
        # 2026-10-13 is Tuesday
        res = resolver.classify_session(datetime.date(2026, 10, 13))
        assert res.is_nifty_expiry is True
        assert res.day_name == "Tuesday"
        assert res.active_expiry_index == "NIFTY"
        assert res.fallback_from_holiday is False

    def test_monday_holiday_fallback(self):
        """Test Monday fallback when Tuesday is a known holiday."""
        # Known holiday: 2026-10-20 is Tuesday holiday (Dussehra)
        resolver = ExpiryCalendarResolver()
        mon_date = datetime.date(2026, 10, 19)
        res = resolver.classify_session(mon_date)
        assert res.day_name == "Monday"
        assert res.is_nifty_expiry is True
        assert res.fallback_from_holiday is True
        assert res.active_expiry_index == "NIFTY"

    def test_sensex_thursday_expiry(self):
        """Test SENSEX Thursday expiry resolution."""
        resolver = ExpiryCalendarResolver()
        # 2026-10-15 is Thursday
        res = resolver.classify_session(datetime.date(2026, 10, 15))
        assert res.is_sensex_expiry is True
        assert res.day_name == "Thursday"
        assert res.active_expiry_index == "SENSEX"
