import os
import tempfile
import pytest
from core.active_position_manager import ActivePositionManager

def test_target_1_hit_requires_option_gain_milestone():
    """Verify that Target 1 milestone (+15 pts) is strictly governed by option gain.
    
    A delta-decayed OTM/ITM option where underlying spot moves +19 pts but option only moves
    +7.2 pts must NOT trigger target_1_hit.
    """
    with tempfile.TemporaryDirectory() as td:
        wal_path = os.path.join(td, "test_wal.json")
        apm = ActivePositionManager(wal_path=wal_path)

        apm.arm_and_enter(
            position_id="TEST_TARGET_MILESTONE_PE",
            direction="PE",
            contract="NIFTY 24350 PE 09 NOV 26",
            entry_price=24583.95,
            entry_time_str="2026-11-06T10:55:04",
            sl_pts=15.0,
            tp_pts=66.95,
            opt_quote={"symbol": "NIFTY 24350 PE", "ltp": 92.70, "bid": 92.45, "ask": 92.70},
            is_runner_mode=False,
        )

        # 1. Spot moves favorably by +19.2 pts (24583.95 -> 24564.75), but option only expands by +7.2 pts (92.70 -> 99.90)
        state, p = apm.evaluate_tick(current_spot=24564.75, current_opt_ltp=99.90)
        assert p["max_spot_excursion"] == 19.2
        assert p["max_opt_excursion"] == 7.2
        assert p["target_1_hit"] is False, "target_1_hit must NOT be triggered when option gain is below +15 pts"

        # 2. Option price surges to +15.2 pts gain (92.70 -> 107.90)
        state, p = apm.evaluate_tick(current_spot=24550.00, current_opt_ltp=107.90)
        assert p["max_opt_excursion"] == 15.2
        assert p["target_1_hit"] is True, "target_1_hit MUST trigger once option gain reaches +15 pts"
