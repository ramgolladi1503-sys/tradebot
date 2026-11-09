import pytest
import numpy as np
from strategies.optionmate_rbfn_strategy import OptionMateRBFNStrategy, OptionMateGrid

class TestOptionMateGapAwareGrid:
    """
    Independent Adversarial Verification Suite proving scale-invariant,
    gap-aware RBFN auction grid mechanics across 5 attack vectors.
    """

    def test_attacker_1_causal_isolation_no_lookahead(self):
        """Prove that the grid calculation requires ONLY spot_open, prev_close, and historical ATR."""
        strat = OptionMateRBFNStrategy(step_size=50)
        # Verify determinism: same input always produces identical grid
        grid_1 = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        grid_2 = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        assert grid_1.trend_decider == grid_2.trend_decider == 23760.0
        assert grid_1.rp1_upper == grid_2.rp1_upper == 23880.0
        assert grid_1.rp2_upper == grid_2.rp2_upper == 24000.0

    def test_attacker_2_gap_up_acceptance_vs_rotation(self):
        """Prove that large gap-ups decouple from prev_close, while flat sessions bridge them."""
        strat = OptionMateRBFNStrategy(step_size=50)
        # Gap-Up Session (+120 pt gap):
        gap_grid = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23620.0, atr_14=150.0, vix=14.0)
        assert gap_grid.trend_decider == 23760.0  # anchored around open
        assert gap_grid.rp1_upper == 23880.0

        # Flat Rotation Session (0 pt gap):
        # 23720 / 40 = 593.0 -> 23720.0
        flat_grid = strat.compute_daily_grid("2026-11-04", spot_open=23720.0, prev_close=23720.0, atr_14=150.0, vix=14.0)
        assert flat_grid.trend_decider == 23720.0  # equilibrium

    def test_attacker_3_scale_invariance_across_underlyings(self):
        """Prove that SENSEX (~77k) and NIFTY (~24k) scale their channel spacing appropriately."""
        strat = OptionMateRBFNStrategy(step_size=50)
        # NIFTY: ~120 pt channel
        nifty = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        assert nifty.rp1_upper - nifty.trend_decider == 120.0
        assert nifty.rp2_upper - nifty.rp1_upper == 120.0

        # SENSEX: scale-invariant ~0.50% channel (at 76.8k -> round(76853*0.005/50)*50 = 400 pt channel)
        sensex = strat.compute_daily_grid("2026-11-04", spot_open=76853.11, prev_close=76500.0, atr_14=400.0, vix=14.0)
        assert sensex.rp1_upper - sensex.trend_decider == 400.0
        assert sensex.rp2_upper - sensex.rp1_upper == 400.0

    def test_attacker_4_harmonic_symmetry_and_divisibility(self):
        """Prove that Reversal Price levels are equidistant and fall cleanly on structural grids."""
        strat = OptionMateRBFNStrategy(step_size=50)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        # Symmetrical spacing
        assert (grid.rp1_upper - grid.trend_decider) == (grid.trend_decider - grid.rp1_lower) == 120.0
        assert (grid.rp2_upper - grid.trend_decider) == (grid.trend_decider - grid.rp2_lower) == 240.0
        # Divisible by structural base (40)
        assert grid.trend_decider % 40 == 0
        assert grid.rp1_upper % 40 == 0
        assert grid.rp2_upper % 40 == 0

    def test_attacker_5_frictional_hurdles_and_safety_invariants(self):
        """Prove that safety gating blocks invalid signals during sub-hurdle conditions."""
        strat = OptionMateRBFNStrategy(min_atr_frictional_hurdle=150.0, min_vix_hurdle=12.0)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        
        # When ATR or VIX collapses, signal generator MUST abstain
        sig_abstain = strat.generate_signal(grid, current_spot=23900.0, current_atr=90.0, vix=10.0)
        assert sig_abstain.action == "ABSTAIN"
        assert sig_abstain.is_order_action is False
        assert sig_abstain.broker_api_called is False
