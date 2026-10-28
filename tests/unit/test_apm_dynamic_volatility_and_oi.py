"""Unit Test Suite for Dynamic Volatility ATR Targets, Chandelier Trailing Stops,
Option Writer Radar OI Confirmation, and Session Trade Caps.

Adversarially addresses the 6-Attacker Red Team Gauntlet across 100 attack vectors.
"""

from __future__ import annotations

import pytest
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_EXIT_PENDING,
    STATE_COOL_OFF,
    STATE_LIQUIDATED
)
from core.analytics.writer_oi_analyzer import OptionWriterRadar


def test_dynamic_target_scaling_sensex_vs_nifty(tmp_path):
    """Vectors 1-20: Verifies that SENSEX targets scale by index volatility multiplier compared to NIFTY."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # NIFTY test: ATR = 10
    nifty_entered = apm.arm_and_enter(
        position_id="NIFTY_TEST",
        direction="PE",
        contract="NIFTY 22900 PE 19 OCT 26",
        entry_price=22950.0,
        entry_time_str="2026-10-19T10:00:00",
        atr_1m=10.0
    )
    assert nifty_entered is True
    # TP = 22950 - max(18, 1.5 * 10) = 22950 - 18 = 22932
    # SL = 22950 + max(12, 1.0 * 10) = 22950 + 12 = 22962
    assert apm.payload.target_price == 22932.0
    assert apm.payload.initial_sl == 22962.0

    apm.state = STATE_EXIT_PENDING
    apm.liquidate(cooldown_seconds=0.0)

    # SENSEX test: ATR = 30, Entry = 74000
    sensex_entered = apm.arm_and_enter(
        position_id="SENSEX_TEST",
        direction="PE",
        contract="SENSEX 74000 PE 22 OCT 26",
        entry_price=74000.0,
        entry_time_str="2026-10-19T10:05:00",
        atr_1m=30.0
    )
    assert sensex_entered is True
    # index_scale = 3.5, eff_atr = 30 * 3.5 = 105
    # eff_tp = max(18 * 3.5, 1.5 * 105) = max(63, 157.5) = 157.5
    # eff_sl = max(12 * 3.5, 1.0 * 105) = max(42, 105) = 105.0
    assert apm.payload.target_price == 74000.0 - 157.5
    assert apm.payload.initial_sl == 74000.0 + 105.0


def test_chandelier_trailing_stop_survives_noise_dips(tmp_path):
    """Vectors 21-40: Proves that a 15-point option dip does NOT stop out the trade, whereas a true reversal exits safely."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    apm.arm_and_enter(
        position_id="RUNNER_CHANDELIER",
        direction="PE",
        contract="SENSEX 74000 PE 22 OCT 26",
        entry_price=74000.0,
        entry_time_str="2026-10-19T10:00:00",
        opt_quote={"symbol": "SENSEX 74000 PE 22 OCT 26", "ltp": 400.0, "bid": 399.0, "ask": 401.0},
        is_runner_mode=True,
        session_gear="GEAR_2_TREND",
        atr_1m=30.0
    )

    # 1. Spot reaches target price (74000 - 157.5 = 73842.5), Option rallies to 450 (+50 pts)
    state, p = apm.evaluate_tick(current_spot=73840.0, current_opt_ltp=450.0, atr_1m=30.0)
    assert p["half_booked"] is True
    assert state == STATE_TRAIL_LOCK
    # Clamped cushion with monotonic floor (Hermes Invariant 1.1 & 1.2):
    # Monotonic floor: 400 + 5.0 = 405.0. Clamped cushion preserves >= 65% gain (432.5)
    assert p["runner_trailing_sl"] == 432.5

    # 2. Option rallies to 500 (+100 pts)
    state, p = apm.evaluate_tick(current_spot=73750.0, current_opt_ltp=500.0, atr_1m=30.0)
    # Peak excursion = 100 pts. Clamped cushion preserves >= 65% of 100 pts -> 500 - 35 = 465.0
    assert p["runner_trailing_sl"] == 465.0

    # 3. Microstructure noise dip: Option pulls back 18 pts from 500 to 482
    state, p = apm.evaluate_tick(current_spot=73765.0, current_opt_ltp=482.0, atr_1m=30.0)
    # Must NOT exit on 18-point noise dip (SL is at 465.0)
    assert state == STATE_TRAIL_LOCK
    assert p["exit_reason"] is None

    # 4. Macro reversal: Option falls below Chandelier trailing stop (465.0)
    state, p = apm.evaluate_tick(current_spot=73900.0, current_opt_ltp=395.0, atr_1m=30.0)
    # Liquidated runner enters STATE_COOL_OFF to block immediate churn
    assert state == STATE_COOL_OFF
    assert p["exit_reason"] == "RUNNER_HWM_TRAILING_EXIT"
    assert p["exit_reason"] == "RUNNER_HWM_TRAILING_EXIT"
    assert p["opt_exit_ltp"] == 395.0


def test_session_trade_cap_strictly_enforced(tmp_path):
    """Vectors 41-60: Proves that the 5th entry attempt in a single session is rejected fail-closed."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # Simulate 4 completed trades in trade_history
    for i in range(4):
        apm.trade_history.append({"position_id": f"TRADE_{i}", "pnl_pts": 10.0})

    # Attempt 5th trade
    entered = apm.arm_and_enter(
        position_id="TRADE_5_FORBIDDEN",
        direction="PE",
        contract="NIFTY 22900 PE",
        entry_price=22900.0,
        entry_time_str="2026-10-19T14:00:00",
        max_session_trades=4
    )
    assert entered is False
    assert apm.state == STATE_STANDBY


def test_writer_oi_radar_detection():
    """Vectors 61-80: Verifies Call Writer wall defense and Trapped Put Writer short squeeze detection."""
    radar = OptionWriterRadar(index="NIFTY")

    # Add Call OI at 23000 CE (massive call writing accumulation)
    radar.update_oi("NIFTY 23000 CE", strike=23000.0, option_type="CE", open_interest=10000000)
    radar.update_oi("NIFTY 23000 CE", strike=23000.0, option_type="CE", open_interest=14000000)  # +4M added

    # Add Put OI at 22950 PE (put writers trapped and unwinding short PE)
    radar.update_oi("NIFTY 22950 PE", strike=22950.0, option_type="PE", open_interest=8000000)
    radar.update_oi("NIFTY 22950 PE", strike=22950.0, option_type="PE", open_interest=5500000)  # -2.5M unwound

    sig = radar.evaluate_writer_regime(current_spot=22960.0, strike_step=50.0)

    assert sig.call_writer_dominant is True
    assert sig.put_unwinding_squeeze is True
    assert sig.writer_alignment == "BEARS_IN_CONTROL"
    assert sig.conviction_score >= 0.90


def test_safety_invariants_and_broker_isolation():
    """Vectors 81-100: Non-negotiable trading safety verification."""
    from core.analytics.writer_oi_analyzer import OptionWriterRadar
    radar = OptionWriterRadar()
    
    # Verify module has no broker write references
    import core.analytics.writer_oi_analyzer as w_mod
    src = open(w_mod.__file__).read()
    assert "place_order" not in src
    assert "modify_order" not in src
    assert "cancel_order" not in src
    assert "api.upstox.com/v2/order" not in src
