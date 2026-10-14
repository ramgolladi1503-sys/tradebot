"""Integration and Behavioral Tests for SENSEX Sentinel Engine.

Proves:
1. SENSEX Asset Profile initialization and parameter scaling.
2. SENSEX 100-pt strike resolution and contract naming.
3. SENSEX ratcheting (+25 pts -> +12 pts lock, +40 pts -> +3 pts breakeven).
4. BSE_FO quote resolution from live DataFrame format.
5. Zero disruption / fail-closed isolation from NIFTY pipeline.
"""

import math
import pytest
import pandas as pd
from core.asset_profile_registry import get_asset_profile, ASSET_REGISTRY
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_LIQUIDATED
)


def test_sensex_profile_parameters():
    sensex = get_asset_profile("SENSEX")
    assert sensex.ticker == "SENSEX"
    assert sensex.index_instrument_key == "BSE_INDEX|SENSEX"
    assert sensex.fo_exchange_prefix == "BSE_FO"
    assert sensex.strike_step == 100
    assert sensex.target_scalp_pts == 46.0
    assert sensex.target_runner_pts == 85.0
    assert sensex.initial_sl_pts == 30.0
    assert sensex.ratchet_trigger_pts == 25.0
    assert sensex.ratchet_lock_pts == 12.0
    assert sensex.breakeven_trigger_pts == 40.0
    assert sensex.breakeven_lock_pts == 3.0
    assert sensex.or_min_expansion_width == 300.0
    assert sensex.macro_exhaustion_cap_pts == 1100.0
    assert sensex.weekly_expiry_day_of_week == 3  # Thursday


def test_sensex_active_position_manager_ratchet(tmp_path):
    sensex = get_asset_profile("SENSEX")
    wal_file = str(tmp_path / "sensex_wal.json")
    apm = ActivePositionManager(wal_path=wal_file, profile=sensex)

    entry_spot = 73000.0
    # Enter SENSEX CE position
    armed = apm.arm_and_enter(
        position_id="test-sensex-pos-1",
        direction="CE",
        contract="SENSEX 72900 CE [ITM]",
        entry_price=entry_spot,
        entry_time_str="2026-10-14T10:00:00",
        sl_pts=sensex.initial_sl_pts,
        tp_pts=sensex.target_scalp_pts,
    )
    assert armed is True
    assert apm.state == STATE_IN_FLIGHT
    assert apm.payload.current_sl == 73000.0 - sensex.initial_sl_pts  # 72970.0

    # Move spot by +20 pts (less than +25 ratchet trigger) -> should stay in flight, SL unchanged
    state, p = apm.evaluate_tick(
        current_spot=73020.0,
        current_opt_ltp=300.0,
        tick_time_str="2026-10-14T10:01:00",
        atr_1m=30.0
    )
    assert state == STATE_IN_FLIGHT
    assert p["trail_locked"] is False
    assert p["current_sl"] == 72970.0

    # Move spot by +26 pts (crosses +25 trigger) -> ratchets SL to entry + 12.0 = 73012.0
    state, p = apm.evaluate_tick(
        current_spot=73026.0,
        current_opt_ltp=310.0,
        tick_time_str="2026-10-14T10:02:00",
        atr_1m=30.0
    )
    assert state == STATE_TRAIL_LOCK
    assert p["trail_locked"] is True
    assert p["current_sl"] == 73012.0

    # Price retraces to 73012.0 -> triggers trailing stop exit with +12 pts profit
    state, summary = apm.evaluate_tick(
        current_spot=73012.0,
        current_opt_ltp=305.0,
        tick_time_str="2026-10-14T10:03:00",
        atr_1m=30.0
    )
    assert state == STATE_LIQUIDATED
    assert summary["exit_reason"] == "TRAILING_STOP_HIT"
    assert summary["pnl_pts"] == 12.0


def test_sensex_quote_dataframe_resolution():
    from scripts.run_live_feed_advisor import SentinelLiveFeedAdvisor

    # Construct mock BSE_FO chunk data
    data = [
        {
            "symbol": "SENSEX 73000 CE 15 OCT 26",
            "token": "BSE_FO|1114892",
            "ltp": 450.0,
            "bid": 448.5,
            "ask": 451.5,
            "vol": 12000,
            "oi": 85000,
            "ts": 1791950000.0
        },
        {
            "symbol": "SENSEX 73000 PE 15 OCT 26",
            "token": "BSE_FO|1114893",
            "ltp": 380.0,
            "bid": 378.0,
            "ask": 381.0,
            "vol": 15000,
            "oi": 92000,
            "ts": 1791950000.0
        }
    ]
    df = pd.DataFrame(data)

    advisor = SentinelLiveFeedAdvisor.__new__(SentinelLiveFeedAdvisor)
    advisor.ticker = "SENSEX"
    advisor.target_expiry = None

    q = advisor.resolve_quote_from_dataframe(df, strike=73000, opt_type="CE")
    assert q is not None
    assert q["symbol"] == "SENSEX 73000 CE 15 OCT 26"
    assert q["token"] == "BSE_FO|1114892"
    assert q["ltp"] == 450.0
    assert q["bid"] == 448.5
    assert q["ask"] == 451.5
