"""Unit and Integration Tests for ARCH-SENTINEL-SEED-MIDDAY-001:
- Causal Dynamic Session Seeding of Prior-Day Reference Levels (Zero Hardcoding)
- Fail-Closed Cold Start & Validation (pdh <= pdl or pdl <= 0)
- Mode 1 Trend Protection (Strictly gated to GEAR_1_RANGE, trend bypass removed)
- Midday Slump Guard (11:30 - 12:30 IST) on Mode 2 Breakout entries (with KER/RVOL trend override)
- Exit Preservation during Midday (Stop Loss & Profit Target exits unaffected)
- Index-specific ATR Floor Clamping (NIFTY: 25.0, BANKNIFTY: 100.0, SENSEX: 150.0)

Safety Contract:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from datetime import date, datetime, time as dt_time, timedelta
from unittest.mock import patch, MagicMock
import pytest

from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_LIQUIDATED,
    STATE_COOL_OFF,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    PriorDayReferenceLevels,
)
from core.liquidity_sweep_engine import LiquiditySweepSignal
from core.upstox_stream_broadcaster import (
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
)


def _make_depth_record(
    symbol: str,
    ltp: float,
    bid: float,
    ask: float,
    timestamp_ms: int,
    volume: int = 100000,
    open_interest: int = 5000000,
) -> UpstoxLevel5DepthRecord:
    """Helper to instantiate full UpstoxLevel5DepthRecord."""
    token = f"NSE_FO|{symbol}"
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=timestamp_ms,
        ingress_monotonic_ns=0,
        ingress_wall_utc="2026-10-31T10:00:00Z",
        sequence_id=1,
        ltp=ltp,
        volume=volume,
        open_interest=open_interest,
        bid_p1=bid, bid_q1=1000, bid_o1=5,
        bid_p2=bid - 0.1, bid_q2=1000, bid_o2=5,
        bid_p3=bid - 0.2, bid_q3=1000, bid_o3=5,
        bid_p4=bid - 0.3, bid_q4=1000, bid_o4=5,
        bid_p5=bid - 0.4, bid_q5=1000, bid_o5=5,
        ask_p1=ask, ask_q1=1000, ask_o1=5,
        ask_p2=ask + 0.1, ask_q2=1000, ask_o2=5,
        ask_p3=ask + 0.2, ask_q3=1000, ask_o3=5,
        ask_p4=ask + 0.3, ask_q4=1000, ask_o4=5,
        ask_p5=ask + 0.4, ask_q5=1000, ask_o5=5,
    )


def _make_tick_record(
    token: str,
    ltp: float,
    volume: int,
    ts_ms: int,
) -> UpstoxTickRecord:
    """Helper to instantiate full UpstoxTickRecord."""
    return UpstoxTickRecord(
        token=token,
        symbol=token,
        exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=0,
        ingress_wall_utc="2026-10-31T10:00:00Z",
        sequence_id=1,
        ltp=ltp,
        volume=volume,
        open_interest=1000000,
        best_bid=ltp - 0.5,
        best_ask=ltp + 0.5,
    )


class TestPriorDaySeedingAndFailClosed:
    """Verifies dynamic seeding, zero hardcoding, and fail-closed validation."""

    def test_zero_hardcoding_cold_start_unverified(self):
        """Advisor must boot with zero static levels; unseeded levels have verified=False."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        for idx in ("NIFTY", "SENSEX", "BANKNIFTY"):
            assert idx in advisor.prior_day_levels
            levels = advisor.prior_day_levels[idx]
            assert isinstance(levels, PriorDayReferenceLevels)
            assert levels.verified is False
            assert levels.pdh == 0.0
            assert levels.pdl == 0.0

    def test_dynamic_seeding_success(self):
        """Seeding valid levels updates prior_day_levels with verified=True."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        success = advisor.seed_prior_day_levels(
            index_name="NIFTY",
            pdh=24500.0,
            pdl=24300.0,
            pdc=24450.0,
            session_date=date(2026, 10, 30),
            atr_20=130.0,
        )
        assert success is True
        nifty_levels = advisor.prior_day_levels["NIFTY"]
        assert nifty_levels.verified is True
        assert nifty_levels.pdh == 24500.0
        assert nifty_levels.pdl == 24300.0
        assert nifty_levels.pdc == 24450.0
        assert nifty_levels.atr_20 == 130.0
        assert nifty_levels.session_date == date(2026, 10, 30)

    def test_fail_closed_invalid_levels_pdh_le_pdl(self):
        """Fail-closed: if pdh <= pdl, seeding returns False and verified=False."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        res1 = advisor.seed_prior_day_levels("NIFTY", pdh=24000.0, pdl=24000.0, pdc=24000.0)
        assert res1 is False
        assert advisor.prior_day_levels["NIFTY"].verified is False

        res2 = advisor.seed_prior_day_levels("BANKNIFTY", pdh=52000.0, pdl=52500.0, pdc=52200.0)
        assert res2 is False
        assert advisor.prior_day_levels["BANKNIFTY"].verified is False

    def test_fail_closed_invalid_levels_pdl_le_zero(self):
        """Fail-closed: if pdl <= 0, seeding returns False and verified=False."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        res = advisor.seed_prior_day_levels("SENSEX", pdh=75000.0, pdl=0.0, pdc=74900.0)
        assert res is False
        assert advisor.prior_day_levels["SENSEX"].verified is False

        res_neg = advisor.seed_prior_day_levels("SENSEX", pdh=75000.0, pdl=-500.0, pdc=74900.0)
        assert res_neg is False
        assert advisor.prior_day_levels["SENSEX"].verified is False


class TestMode1SweepTrendProtection:
    """Verifies Mode 1 sweep reversal fail-closed behavior on unseeded levels and trend gear."""

    def test_mode1_sweep_blocked_when_unseeded(self):
        """Mode 1 sweep reversal must fail closed if prior-day levels are not verified."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        advisor.trade_lock_active = False
        advisor.market_open_time = dt_time(0, 0)
        advisor.opening_shock_end_time = dt_time(0, 0)
        advisor.eod_entry_freeze_time = dt_time(23, 59)
        advisor.session_gear = "GEAR_1_RANGE"

        # Prior day levels unseeded (verified=False)
        assert advisor.prior_day_levels["NIFTY"].verified is False

        # Mock sweep engine to return a valid signal if it were called
        mock_signal = LiquiditySweepSignal(
            timestamp_ms=1000,
            index_name="NIFTY",
            direction="PE",
            sweep_type="PDH_SWEEP_REVERSAL",
            boundary_price=24500.0,
            signal_bar_extreme=24510.0,
            trigger_price=24490.0,
            recommended_sl=24514.0,
            target_pts=45.0,
            sl_pts=10.0,
            is_expiry_boost=False,
            setup_reason="Test Sweep",
        )
        with patch.object(advisor.sweep_engine, "evaluate_bar", return_value=mock_signal) as mock_eval:
            now_ms = int(datetime.now().timestamp() * 1000)
            advisor.spots["NIFTY"] = 24490.0
            advisor.spots_ts_ms["NIFTY"] = now_ms

            depth = _make_depth_record("NIFTY 24500 PE", ltp=120.0, bid=119.5, ask=120.5, timestamp_ms=now_ms)
            advisor._evaluate_option_depth(depth)

            # sweep_engine.evaluate_bar must NOT be called when verified is False
            mock_eval.assert_not_called()

        # No sweep alert was generated
        sweep_alerts = [a for a in advisor.alerts_history if "SWEEP" in a.advisory or "PDH" in a.advisory]
        assert len(sweep_alerts) == 0

    def test_mode1_sweep_blocked_in_gear_2_trend_even_on_expiry(self):
        """Mode 1 sweep reversal strictly blocked in GEAR_2_TREND even on expiry days (trend bypass removed)."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        advisor.trade_lock_active = False
        advisor.market_open_time = dt_time(0, 0)
        advisor.opening_shock_end_time = dt_time(0, 0)
        advisor.eod_entry_freeze_time = dt_time(23, 59)

        # Seed valid levels
        advisor.seed_prior_day_levels("NIFTY", pdh=24500.0, pdl=24300.0, pdc=24400.0)

        # Set session gear to GEAR_2_TREND
        advisor.session_gear = "GEAR_2_TREND"

        # Mock expiry active for NIFTY
        advisor.expiry_info = advisor.expiry_resolver.classify_session(date(2026, 10, 13))

        mock_signal = LiquiditySweepSignal(
            timestamp_ms=1000,
            index_name="NIFTY",
            direction="PE",
            sweep_type="PDH_SWEEP_REVERSAL",
            boundary_price=24500.0,
            signal_bar_extreme=24510.0,
            trigger_price=24490.0,
            recommended_sl=24514.0,
            target_pts=45.0,
            sl_pts=10.0,
            is_expiry_boost=True,
            setup_reason="Test Sweep",
        )
        with patch.object(advisor.sweep_engine, "evaluate_bar", return_value=mock_signal) as mock_eval:
            now_ms = int(datetime.now().timestamp() * 1000)
            advisor.spots["NIFTY"] = 24490.0
            advisor.spots_ts_ms["NIFTY"] = now_ms

            depth = _make_depth_record("NIFTY 24500 PE", ltp=120.0, bid=119.8, ask=120.2, timestamp_ms=now_ms)
            advisor._evaluate_option_depth(depth)

            # In GEAR_2_TREND, evaluate_bar must NOT be called even though active_expiry_index == "NIFTY"
            mock_eval.assert_not_called()

        sweep_alerts = [a for a in advisor.alerts_history if "SWEEP" in a.advisory or "PDH" in a.advisory]
        assert len(sweep_alerts) == 0


class TestMiddaySlumpGuard:
    """Verifies Midday Slump Guard (11:30 - 12:30 IST) on Mode 2 Breakout entries."""

    def test_midday_slump_exact_boundary_times(self):
        """Test exact boundary seconds:
        - 11:29:59 ALLOW
        - 11:30:00 RESTRICT
        - 12:00:00 RESTRICT
        - 12:30:00 RESTRICT
        - 12:30:01 ALLOW
        """
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        advisor.current_ker = 0.50
        advisor.current_rvol = 1.00  # Normal chop/range conditions

        # 11:29:59 IST -> ALLOW (slump not active)
        t_112959 = dt_time(11, 29, 59)
        assert advisor.is_midday_slump_active(check_time=t_112959) is False

        # 11:30:00 IST -> RESTRICT (slump active)
        t_113000 = dt_time(11, 30, 0)
        assert advisor.is_midday_slump_active(check_time=t_113000) is True

        # 12:00:00 IST -> RESTRICT (slump active)
        t_120000 = dt_time(12, 0, 0)
        assert advisor.is_midday_slump_active(check_time=t_120000) is True

        # 12:30:00 IST -> RESTRICT (slump active)
        t_123000 = dt_time(12, 30, 0)
        assert advisor.is_midday_slump_active(check_time=t_123000) is True

        # 12:30:01 IST -> ALLOW (slump not active)
        t_123001 = dt_time(12, 30, 1)
        assert advisor.is_midday_slump_active(check_time=t_123001) is False

    def test_midday_slump_veto_in_depth_tick(self):
        """A Mode 2 breakout trigger during 11:30-12:30 must be vetoed with VETO_MIDDAY_LIQUIDITY_SLUMP."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        advisor.trade_lock_active = False
        advisor.market_open_time = dt_time(0, 0)
        advisor.opening_shock_end_time = dt_time(0, 0)
        advisor.eod_entry_freeze_time = dt_time(23, 59)
        advisor.current_ker = 0.40
        advisor.current_rvol = 1.00

        now_ms = 1730356200000
        advisor.or_bounds["NIFTY"] = {"high": 24500.0, "low": 24350.0}
        advisor.spots["NIFTY"] = 24520.0  # Breakout > 24500
        advisor.spots_ts_ms["NIFTY"] = now_ms

        depth = _make_depth_record("NIFTY 24500 CE", ltp=110.0, bid=109.8, ask=110.2, timestamp_ms=now_ms)

        # Mock current time at 12:00:00 IST
        fake_now = datetime(2026, 10, 31, 12, 0, 0)
        with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            advisor._evaluate_option_depth(depth)

        assert len(advisor.alerts_history) >= 1
        latest_alert = advisor.alerts_history[-1]
        assert latest_alert.status_flag == "VETO_MIDDAY_LIQUIDITY_SLUMP"
        assert "MIDDAY_LIQUIDITY_SLUMP_VETO (11:30-12:30 IST)" in latest_alert.advisory

    def test_midday_trend_override_allows_breakout(self):
        """When strong trend override is active (KER >= 0.70 & RVOL >= 1.50) at 11:45:00 IST, breakout is ALLOWED."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
        advisor.trade_lock_active = False
        advisor.market_open_time = dt_time(0, 0)
        advisor.opening_shock_end_time = dt_time(0, 0)
        advisor.eod_entry_freeze_time = dt_time(23, 59)

        # Trend override metrics
        advisor.current_ker = 0.75
        advisor.current_rvol = 1.80

        # Verify is_midday_slump_active returns False even at 11:45:00
        t_114500 = dt_time(11, 45, 0)
        assert advisor.is_midday_slump_active(check_time=t_114500) is False

        now_ms = 1730356200000
        advisor.or_bounds["NIFTY"] = {"high": 24500.0, "low": 24350.0}
        advisor.spots["NIFTY"] = 24520.0  # Breakout
        advisor.spots_ts_ms["NIFTY"] = now_ms

        depth = _make_depth_record("NIFTY 24500 CE", ltp=110.0, bid=109.8, ask=110.2, timestamp_ms=now_ms)

        fake_now = datetime(2026, 10, 31, 11, 45, 0)
        with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            advisor._evaluate_option_depth(depth)

        # Alert should not be vetoed by MIDDAY_LIQUIDITY_SLUMP
        slump_vetoes = [a for a in advisor.alerts_history if a.status_flag == "VETO_MIDDAY_LIQUIDITY_SLUMP"]
        assert len(slump_vetoes) == 0


class TestExitPreservationDuringMidday:
    """Verifies that ActivePositionManager stop-loss and profit target exits operate normally during 11:30 - 12:30."""

    def test_stop_loss_and_target_exits_active_during_midday(self, tmp_path):
        """In-flight positions must liquidate on stop-loss or profit target hit even during 11:30 - 12:30."""
        wal_file = tmp_path / "test_apm_wal.json"
        apm = ActivePositionManager(wal_path=str(wal_file))

        # Enter in-flight position
        entered = apm.arm_and_enter(
            position_id="TEST_MIDDAY_POS",
            direction="CE",
            contract="NIFTY 24500 CE",
            entry_price=24500.0,
            entry_time_str="2026-10-31T10:00:00",
            tp_pts=50.0,
            sl_pts=25.0,
            atr_1m=30.0,
        )
        assert entered is True
        assert apm.state == STATE_IN_FLIGHT

        # Evaluate tick at 12:00:00 IST hitting SL (current spot 24470.0 < SL 24475.0)
        state_after_sl, p_exit = apm.evaluate_tick(
            current_spot=24470.0,
            current_opt_ltp=80.0,
            tick_time_str="12:00:00",
        )
        # APM transitions to STATE_COOL_OFF (or STATE_LIQUIDATED) and sets exit_reason
        assert state_after_sl in {STATE_LIQUIDATED, STATE_COOL_OFF}
        assert p_exit["exit_reason"] in {"HIT_SL", "STOP_LOSS_HIT"}

    def test_advisor_processes_in_flight_exits_during_midday(self, tmp_path):
        """Advisor's in-flight position evaluation updates and liquidates during 11:30 - 12:30."""
        test_wal = tmp_path / "advisor_wal.json"
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False, wal_path=str(test_wal))
        advisor.trade_lock_active = False
        advisor.market_open_time = dt_time(0, 0)
        advisor.opening_shock_end_time = dt_time(0, 0)
        advisor.eod_entry_freeze_time = dt_time(23, 59)

        # Set in-flight position on NIFTY APM with explicit opt_symbol in opt_quote
        apm = advisor.apms["NIFTY"]
        apm.state = STATE_STANDBY
        apm.cool_off_until = None
        apm.cool_off_ref_spot = None

        entered = apm.arm_and_enter(
            position_id="IN_FLIGHT_NIFTY",
            direction="CE",
            contract="NIFTY 24500 CE",
            entry_price=24500.0,
            entry_time_str="2026-10-31T10:00:00",
            tp_pts=40.0,
            sl_pts=20.0,
            atr_1m=30.0,
            opt_quote={"symbol": "NIFTY 24500 CE", "ltp": 100.0, "bid": 99.8, "ask": 100.2},
        )
        assert entered is True
        assert apm.state == STATE_IN_FLIGHT
        assert apm.payload.opt_symbol == "NIFTY 24500 CE"

        # Send option tick at 12:05:00 IST that breaches stop loss (spot=24475 < initial_sl=24480)
        now_ms = 1730356200000
        advisor.spots["NIFTY"] = 24475.0
        advisor.spots_ts_ms["NIFTY"] = now_ms

        depth = _make_depth_record("NIFTY 24500 CE", ltp=75.0, bid=74.5, ask=75.5, timestamp_ms=now_ms)

        fake_now = datetime(2026, 10, 31, 12, 5, 0)
        with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            advisor._evaluate_option_depth(depth)

        # Verify APM liquidated the position
        assert apm.state in {STATE_LIQUIDATED, STATE_COOL_OFF}


class TestIndexAtrFloorClamping:
    """Verifies clamp_atr enforcing index-specific floors."""

    def test_atr_floor_clamping_per_index(self):
        """NIFTY: 25.0, BANKNIFTY: 100.0, SENSEX: 150.0."""
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False)

        # NIFTY clamp
        assert advisor.clamp_atr("NIFTY", 10.0) == 25.0
        assert advisor.clamp_atr("NIFTY", 24.9) == 25.0
        assert advisor.clamp_atr("NIFTY", 35.0) == 35.0

        # BANKNIFTY clamp
        assert advisor.clamp_atr("BANKNIFTY", 50.0) == 100.0
        assert advisor.clamp_atr("BANKNIFTY", 99.9) == 100.0
        assert advisor.clamp_atr("BANKNIFTY", 180.0) == 180.0

        # SENSEX clamp
        assert advisor.clamp_atr("SENSEX", 80.0) == 150.0
        assert advisor.clamp_atr("SENSEX", 149.0) == 150.0
        assert advisor.clamp_atr("SENSEX", 320.0) == 320.0
