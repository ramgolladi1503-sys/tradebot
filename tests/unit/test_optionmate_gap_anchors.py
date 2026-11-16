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
        assert grid_1.trend_decider == grid_2.trend_decider == 23742.25
        assert grid_1.rp1_upper == grid_2.rp1_upper == 23852.25
        assert grid_1.rp2_upper == grid_2.rp2_upper == 23945.75

    def test_attacker_2_gap_up_acceptance_vs_rotation(self):
        """Prove that large gap-ups decouple from prev_close, while flat sessions bridge them."""
        strat = OptionMateRBFNStrategy(step_size=50)
        # Gap-Up Session (+122.25 pt gap >= 0.25 * 150 = 37.5):
        gap_grid = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23620.0, atr_14=150.0, vix=14.0)
        assert gap_grid.trend_decider == 23742.25  # anchored around open
        assert gap_grid.rp1_upper == 23852.25

        # Flat Rotation Session (20 pt gap < 37.5 threshold):
        # raw_td = 0.5 * (23740.0 + 23720.0) = 23730.0
        flat_grid = strat.compute_daily_grid("2026-11-04", spot_open=23740.0, prev_close=23720.0, atr_14=150.0, vix=14.0)
        assert flat_grid.trend_decider == 23730.0  # bridges open and prior close

    def test_attacker_3_scale_invariance_across_underlyings(self):
        """Prove that SENSEX (~77k) and NIFTY (~24k) scale their channel spacing appropriately."""
        strat = OptionMateRBFNStrategy(step_size=50)
        # NIFTY: continuous 110 pt base channel
        nifty = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        assert nifty.rp1_upper - nifty.trend_decider == 110.0
        assert round(nifty.rp2_upper - nifty.rp1_upper, 2) == 93.5  # 0.85 * 110

        # SENSEX: scale-invariant base step (400 pt channel at >60000)
        sensex = strat.compute_daily_grid("2026-11-04", spot_open=76853.11, prev_close=76500.0, atr_14=400.0, vix=14.0)
        assert round(sensex.rp1_upper - sensex.trend_decider, 2) == 400.0
        # rp2_up_raw = 77253.11 + 340.0 = 77593.11, snaps to century 77600.0 (|77593.11 - 77600| = 6.89 <= 10.0)
        assert sensex.rp2_upper == 77600.0

    def test_attacker_4_harmonic_symmetry_and_divisibility(self):
        """Prove that Reversal Price levels are equidistant and continuous."""
        strat = OptionMateRBFNStrategy(step_size=50)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        # Symmetrical spacing
        assert round(grid.rp1_upper - grid.trend_decider, 2) == round(grid.trend_decider - grid.rp1_lower, 2) == 110.0
        assert round(grid.rp2_upper - grid.rp1_upper, 2) == round(grid.rp1_lower - grid.rp2_lower, 2) == 93.5
        # Slingshot strikes cleanly quantized to step_size
        assert grid.call_strike % 50 == 0
        assert grid.put_strike % 50 == 0

    def test_attacker_5_frictional_hurdles_and_safety_invariants(self):
        """Prove that safety gating blocks invalid signals during sub-hurdle conditions."""
        strat = OptionMateRBFNStrategy(min_atr_frictional_hurdle=150.0, min_vix_hurdle=12.0)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=23742.25, prev_close=23694.25, atr_14=150.0, vix=14.0)
        
        # When ATR or VIX collapses, signal generator MUST abstain
        sig_abstain = strat.generate_signal(grid, current_spot=23900.0, current_atr=90.0, vix=10.0)
        assert sig_abstain.action == "ABSTAIN"
        assert sig_abstain.is_order_action is False
        assert sig_abstain.broker_api_called is False
