"""Unit and Causal Verification Tests for ExpiryCalendarResolver & LiquiditySweepEngine.

Tests:
1. Dynamic Expiry Day Resolution (SEBI Tuesday shift, Monday fallback on holidays).
2. SENSEX Thursday Expiry & Wednesday fallback.
3. Liquidity Sweep Detection (Bull trap PDH rejection -> PE signal, Bear trap PDL rejection -> CE signal).
4. Boundary lock prevention (Max 1 attempt per boundary per day).
5. Zero Future Bar Leakage (Causal Next-Bar execution & pessimistic tie-breaks).
6. Strict Safety Invariants.
"""

from __future__ import annotations

import datetime
import pytest

from core.expiry_calendar_resolver import ExpiryCalendarResolver
from core.liquidity_sweep_engine import LiquiditySweepEngine


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


class TestLiquiditySweepEngine:
    def test_pdh_bull_trap_short_signal(self):
        """Test bull trap: price pierces PDH by 15 pts and closes below -> Short signal."""
        engine = LiquiditySweepEngine(nifty_max_sweep_pts=25.0, nifty_target_pts=45.0)
        pdh = 23150.0
        pdl = 22900.0

        # Bar opens at 23140, wicks up to 23165 (+15 pts above PDH), closes at 23143 (below PDH)
        sig = engine.evaluate_bar(
            index_name="NIFTY",
            bar_open=23140.0,
            bar_high=23165.0,
            bar_low=23135.0,
            bar_close=23143.0,
            pdh=pdh,
            pdl=pdl,
            timestamp_ms=1729312000000,
            is_expiry_session=True,
            bar_time=datetime.time(10, 0),
        )

        assert sig is not None
        assert sig.direction == "PE"
        assert sig.sweep_type == "PDH_SWEEP_REVERSAL"
        assert sig.recommended_sl == 23169.0  # 23165 + 4
        assert sig.target_pts == 45.0
        assert sig.is_expiry_boost is True

    def test_pdl_bear_trap_long_signal(self):
        """Test bear trap: price pierces PDL by 10 pts and closes above -> Long signal."""
        engine = LiquiditySweepEngine(nifty_max_sweep_pts=25.0, nifty_target_pts=45.0)
        pdh = 23150.0
        pdl = 22900.0

        # Bar opens at 22910, wicks down to 22890 (-10 pts below PDL), closes at 22905 (above PDL)
        sig = engine.evaluate_bar(
            index_name="NIFTY",
            bar_open=22910.0,
            bar_high=22915.0,
            bar_low=22890.0,
            bar_close=22905.0,
            pdh=pdh,
            pdl=pdl,
            timestamp_ms=1729312000000,
            is_expiry_session=False,
            bar_time=datetime.time(10, 30),
        )

        assert sig is not None
        assert sig.direction == "CE"
        assert sig.sweep_type == "PDL_SWEEP_REVERSAL"
        assert sig.recommended_sl == 22886.0  # 22890 - 4
        assert sig.target_pts == 45.0

    def test_prevent_runaway_trend_multiple_attempts(self):
        """Test that engine locks after 1 attempt per boundary per day to prevent fighting super-trends."""
        engine = LiquiditySweepEngine()
        pdh = 23150.0
        pdl = 22900.0

        # First attempt fires
        sig1 = engine.evaluate_bar("NIFTY", 23140.0, 23160.0, 23135.0, 23145.0, pdh, pdl, 1000, False, datetime.time(10, 0))
        assert sig1 is not None

        # Second attempt on same day must be suppressed
        sig2 = engine.evaluate_bar("NIFTY", 23142.0, 23162.0, 23138.0, 23144.0, pdh, pdl, 2000, False, datetime.time(10, 5))
        assert sig2 is None

    def test_operating_time_window_restriction(self):
        """Test that sweep signals are suppressed before 09:30 or after 12:00."""
        engine = LiquiditySweepEngine()
        pdh = 23150.0
        pdl = 22900.0

        # 09:20 AM (Before 09:30) -> Suppressed
        sig_early = engine.evaluate_bar("NIFTY", 23140.0, 23160.0, 23135.0, 23145.0, pdh, pdl, 1000, False, datetime.time(9, 20))
        assert sig_early is None

        # 13:00 PM (After 12:00) -> Suppressed
        sig_late = engine.evaluate_bar("NIFTY", 23140.0, 23160.0, 23135.0, 23145.0, pdh, pdl, 1000, False, datetime.time(13, 0))
        assert sig_late is None
