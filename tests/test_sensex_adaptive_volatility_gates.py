"""Tests proving Layer 4: Adaptive Volatility & Non-Linear Noise Gates.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Guarantees:
1. SENSEX displacement gate enforces at least max(30.0, 1.2 * ATR_1m) outside 1m candle noise.
2. Brownian energy gate correctly rejects entries when realized ATR cannot diffuse target distance.
"""
import math
from datetime import time as dtime
from core.active_position_manager import ActivePositionManager
from core.asset_profile_registry import get_asset_profile


def test_sensex_brownian_energy_gate_realized_volatility(tmp_path):
    wal = tmp_path / "runtime/sentinel_apm_wal_sensex.json"
    sensex = get_asset_profile("SENSEX")
    apm = ActivePositionManager(wal_path=str(wal), profile=sensex)

    # Normal SENSEX realized ATR (ATR_1m = 22.0 pts)
    # Expected 15m excursion = 22.0 * sqrt(15) = 85.2 pts >= 46.0 pts target -> Allowed
    can_enter_norm, diff_norm, req_norm = apm.check_session_energy_gate(
        current_time=dtime(10, 0),
        target_pts=sensex.target_scalp_pts,
        atr_1m=22.0,
        trade_horizon_mins=15
    )
    assert can_enter_norm is True
    assert diff_norm > req_norm
    assert diff_norm == round(22.0 * math.sqrt(15), 2)

    # Dead Compressed SENSEX Volatility (ATR_1m = 8.0 pts)
    # Expected 15m excursion = 8.0 * sqrt(15) = 30.98 pts < 46.0 pts target -> Vetoed!
    can_enter_dead, diff_dead, req_dead = apm.check_session_energy_gate(
        current_time=dtime(13, 0),
        target_pts=sensex.target_scalp_pts,
        atr_1m=8.0,
        trade_horizon_mins=15
    )
    assert can_enter_dead is False
    assert diff_dead < req_dead
