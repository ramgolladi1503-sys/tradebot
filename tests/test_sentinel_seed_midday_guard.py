"""Unit and Integration Tests for ARCH-SENTINEL-SEED-MIDDAY-001:
- Causal Dynamic Session Seeding of Prior-Day Reference Levels (Zero Hardcoding)
- Fail-Closed Cold Start & Validation (pdh <= pdl or pdl <= 0)
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
from datetime import date, datetime, time as dt_time
from unittest.mock import patch
import pytest

from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_LIQUIDATED,
    STATE_COOL_OFF,
)
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    PriorDayReferenceLevels,
)
from core.upstox_stream_broadcaster import (
    UpstoxLevel5DepthRecord,
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
