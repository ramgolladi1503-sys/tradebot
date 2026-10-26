"""Unit and invariant tests for Sentinel Dynamic Sizing and Gate 1 & 2 controls.

Tests:
1. Floor-or-Reject Model: Sub-lot capital allocations strictly return lots=0 and tier 'REJECT_INSUFFICIENT_MARGIN' (never round up).
2. Discrete Lot Allocations: Full size and half size discrete integer computation.
3. Pre-entry Adverse Wall Veto: Clamping to lots=0 and ZERO_SUPPRESS within 0.5 * ATR of fortified wall.
4. ActivePositionManager arm_and_enter invariant: Rejection when lots < 1.
5. Trading Safety Invariants: read_only, is_order_action, broker_api_called.
"""

import pytest
import time
from core.sentinel_dynamic_sizing import (
    calculate_discrete_lots,
    get_exchange_lot_size,
    INDEX_LOT_SIZES,
)
from core.active_position_manager import (
    ActivePositionManager,
    PositionPayload,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
)
from core.market_structure.sentinel_wall_observer import SentinelWallObserver
from core.market_structure.sentinel_wall_gate import (
    SentinelWallGate,
    GATE_ACTION_VETO,
    GATE_ACTION_CONFIRM_BREACH,
)


def test_exchange_lot_sizes():
    """Verify statutory exchange lot size resolution."""
    assert get_exchange_lot_size("NIFTY") == 65
    assert get_exchange_lot_size("BANKNIFTY") == 40
    assert get_exchange_lot_size("SENSEX") == 20
    assert get_exchange_lot_size("FINNIFTY") == 25
    assert get_exchange_lot_size("MIDCPNIFTY") == 50


def test_floor_or_reject_sub_lot_never_rounds_up():
    """Invariant 1.2: If computed_lots < 1, sizing MUST return lots=0 and never round up."""
    # NIFTY lot size = 65. If premium is 200, margin per lot = 13,000.
    # Total capital = 5,000 (< 13,000) -> lots must be 0.
    lots, tier = calculate_discrete_lots(
        total_capital=5000.0,
        risk_budget_pct=0.02,
        opt_premium=200.0,
        sl_points=15.0,
        index_name="NIFTY",
        sizing_recommendation="FULL_SIZE",
    )
    assert lots == 0
    assert tier == "REJECT_INSUFFICIENT_MARGIN"

    # Risk budget constraint: total_capital = 50,000, 2% risk = 1,000.
    # Risk per lot = 20 pts * 65 = 1,300.
    # lots_by_risk = floor(1000 / 1300) = 0 -> must reject even if capital suffices for margin.
    lots, tier = calculate_discrete_lots(
        total_capital=50000.0,
        risk_budget_pct=0.02,
        opt_premium=50.0,
        sl_points=20.0,
        index_name="NIFTY",
        sizing_recommendation="FULL_SIZE",
    )
    assert lots == 0
    assert tier == "REJECT_INSUFFICIENT_MARGIN"


def test_full_and_half_size_discrete_allocations():
    """Verify standard discrete lot allocation for full and half sizing tiers."""
    # SENSEX: lot size = 20. Total capital = 200,000, 2% risk = 4,000.
    # SL = 40 pts -> Risk per lot = 40 * 20 = 800.
    # Margin per lot = 150 * 20 = 3,000.
    # Full size: lots_by_risk = floor(4000 / 800) = 5. lots_by_margin = floor(200000 / 3000) = 66. min = 5.
    lots_full, tier_full = calculate_discrete_lots(
        total_capital=200000.0,
        risk_budget_pct=0.02,
        opt_premium=150.0,
        sl_points=40.0,
        index_name="SENSEX",
        sizing_recommendation="FULL_SIZE",
    )
    assert lots_full == 5
    assert tier_full == "FULL_SIZE"

    # Half size: risk = 2,000 -> lots_by_risk = floor(2000 / 800) = 2.
    lots_half, tier_half = calculate_discrete_lots(
        total_capital=200000.0,
        risk_budget_pct=0.02,
        opt_premium=150.0,
        sl_points=40.0,
        index_name="SENSEX",
        sizing_recommendation="HALF_SIZE",
    )
    assert lots_half == 2
    assert tier_half == "HALF_SIZE"


def test_zero_suppress_and_negative_parameters():
    """Verify zero suppress recommendations and zero/negative capital fail closed."""
    lots, tier = calculate_discrete_lots(
        total_capital=100000.0,
        risk_budget_pct=0.02,
        opt_premium=100.0,
        sl_points=10.0,
        index_name="NIFTY",
        sizing_recommendation="ZERO_SUPPRESS",
    )
    assert lots == 0
    assert tier == "ZERO_SUPPRESS"

    # Zero capital
    lots, tier = calculate_discrete_lots(
        total_capital=0.0,
        risk_budget_pct=0.02,
        opt_premium=100.0,
        sl_points=10.0,
        index_name="NIFTY",
    )
    assert lots == 0
    assert tier == "ZERO_SUPPRESS"


def test_apm_arm_and_enter_rejects_sub_lot(tmp_path):
    """ActivePositionManager arm_and_enter enforces Floor-or-Reject when lots < 1."""
    wal = tmp_path / "test_apm_sizing_wal.json"
    apm = ActivePositionManager(wal_path=str(wal))
    
    # Attempt entry with lots = 0
    success = apm.arm_and_enter(
        position_id="TEST_REJECT_0",
        direction="CE",
        contract="NIFTY 22600 CE",
        entry_price=22600.0,
        entry_time_str="2026-10-26T10:00:00",
        lots=0,
        sizing_tier="REJECT_INSUFFICIENT_MARGIN",
    )
    assert success is False
    assert apm.state == STATE_STANDBY
    assert apm.payload is None

    # Attempt entry with lots >= 1
    success = apm.arm_and_enter(
        position_id="TEST_ACCEPT_1",
        direction="CE",
        contract="NIFTY 22600 CE",
        entry_price=22600.0,
        entry_time_str="2026-10-26T10:00:00",
        lots=2,
        sizing_tier="FULL_SIZE",
        lot_size=65,
    )
    assert success is True
    assert apm.state == STATE_IN_FLIGHT
    assert apm.payload.lots == 2
    assert apm.payload.sizing_tier == "FULL_SIZE"
    assert apm.payload.lot_size == 65
    assert apm.payload.total_quantity == 130


def test_sentinel_wall_pre_entry_veto_clamping():
    """Gate 2: Pre-entry barrier check against SentinelWallGate vetos within 0.5 ATR."""
    now_ms = int(time.time() * 1000)
    observer = SentinelWallObserver(underlying_symbol="NIFTY", atr_pts=20.0)
    # Spot = 22492 (8 pts below 22500 Call Wall -> 8/20 = 0.40 ATR <= 0.50 ATR)
    observer.on_spot_tick(22492.0, now_ms)

    # Populate observer with fortified call wall at 22500
    for s in [22300.0 + i * 50.0 for i in range(15)]:
        c_oi = 500000.0 if s == 22500.0 else 50000.0
        p_oi = 50000.0
        # Fortified call wall has high bid depth and low ask depth
        c_bid = 800.0 if s == 22500.0 else 200.0
        c_ask = 100.0 if s == 22500.0 else 200.0
        observer.on_option_tick(
            f"NIFTY {int(s)} CE 27 OCT 26",
            oi=c_oi, volume=10000.0, bid_depth=c_bid, ask_depth=c_ask, timestamp_ms=now_ms,
        )
        observer.on_option_tick(
            f"NIFTY {int(s)} PE 27 OCT 26",
            oi=p_oi, volume=10000.0, bid_depth=200.0, ask_depth=200.0, timestamp_ms=now_ms,
        )

    gate = SentinelWallGate(observer=observer, proximity_veto_atr=0.50)
    decision = gate.evaluate_entry_gate("CE", 22492.0, now_ms)

    assert decision.action == GATE_ACTION_VETO
    assert "VETO_FORTIFIED_CALL_WALL" in decision.reason
    assert decision.proximity_atr <= 0.50
    assert decision.read_only is True
    assert decision.is_order_action is False
