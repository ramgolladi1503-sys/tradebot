import pytest
import math
from strategies.sensex_optionmate_rbfn_strategy import (
    SensexOptionMateRBFNStrategy,
    SensexOptionMateGrid,
    SensexOptionMateSignal,
)

class TestSensexStrictGate2AndAttackerVectors:
    """
    Adversarial verification suite proving Strict Gate 2 mechanics,
    dynamic sustainable price anchor derivation, and fakeout defenses across 5 attack vectors.
    """

    def test_attacker_1_sustainable_price_derivation_not_hardcoded(self):
        """Prove that the Sustainable Price is dynamically derived from DTE and VIX, not an arbitrary hardcode."""
        strat = SensexOptionMateRBFNStrategy()
        # Wednesday (1 DTE, VIX 13.5%)
        grid_wed = strat.compute_daily_grid("2026-11-04", spot_open=77000.0, prev_close=76500.0, atr_14=550.0, vix=13.5, dte=1)
        # Expected ATM half-straddle: 77000 * 0.8 * 0.135 * sqrt(1/365) / 2 ≈ 217.7 Rs
        assert 210.0 <= grid_wed.sustainable_price_anchor <= 225.0

        # Expiry Day (0.2 DTE, VIX 13.5%)
        grid_exp = strat.compute_daily_grid("2026-11-05", spot_open=77000.0, prev_close=77000.0, atr_14=550.0, vix=13.5, dte=0)
        # Expected ATM half-straddle on expiry day collapses to ~95 Rs
        assert grid_exp.sustainable_price_anchor < grid_wed.sustainable_price_anchor

    def test_attacker_2_fakeout_veto_unconfirmed_breakout(self):
        """Prove that single-tick spikes above RP1 are blocked without 2-candle confirmation."""
        strat = SensexOptionMateRBFNStrategy(reversal_confirmation_bars=2)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=77000.0, prev_close=76500.0, atr_14=550.0, vix=13.5, dte=1)
        
        # Only 1 close above RP1 -> MUST ABSTAIN
        sig = strat.generate_signal(
            grid,
            current_spot=grid.rp1_upper + 10.0,
            current_atr=550.0,
            vix=13.5,
            or_range=250.0,
            consecutive_closes_outside_rp1=1,
        )
        assert sig.action == "ABSTAIN"
        assert sig.is_vetoed is True
        assert sig.veto_reason == "GATE_2_UNCONFIRMED_BREAKOUT"

    def test_attacker_3_opening_range_chop_veto(self):
        """Prove that narrow, non-expanding morning ranges (< 0.35 * ATR) are vetoed."""
        strat = SensexOptionMateRBFNStrategy()
        grid = strat.compute_daily_grid("2026-11-04", spot_open=77000.0, prev_close=76500.0, atr_14=550.0, vix=13.5, dte=1)
        
        # Opening range is only 120 pts (< 0.35 * 550 = 192.5) -> MUST ABSTAIN
        sig = strat.generate_signal(
            grid,
            current_spot=grid.rp1_upper + 10.0,
            current_atr=550.0,
            vix=13.5,
            or_range=120.0,
            consecutive_closes_outside_rp1=2,
        )
        assert sig.action == "ABSTAIN"
        assert sig.is_vetoed is True
        assert sig.veto_reason == "GATE_2_COMPRESSION_CHOP"

    def test_attacker_4_frictional_hurdle_veto(self):
        """Prove that low-volatility or low-VIX environments fail closed."""
        strat = SensexOptionMateRBFNStrategy(min_atr_frictional_hurdle=450.0, min_vix_hurdle=12.0)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=77000.0, prev_close=76500.0, atr_14=380.0, vix=10.5, dte=1)
        
        sig = strat.generate_signal(grid, current_spot=77500.0, current_atr=380.0, vix=10.5)
        assert sig.action == "ABSTAIN"
        assert sig.is_vetoed is True
        assert sig.veto_reason == "GATE_2_FRICTIONAL_HURDLE"

    def test_attacker_5_target_strike_resolution_at_rp2(self):
        """Prove that the Slingshot strike resolves to RP2 (the strike that converts to ATM)."""
        strat = SensexOptionMateRBFNStrategy(step_size=100)
        grid = strat.compute_daily_grid("2026-11-04", spot_open=76853.11, prev_close=76500.0, atr_14=400.0, vix=13.5, dte=1)
        # Dynamic channel step = 400 pts; RP2 Upper is ~77,700
        assert grid.target_call_strike == 77700.0
        # Valid confirmed signal targets RP2 Upper
        sig = strat.generate_signal(
            grid,
            current_spot=grid.rp1_upper + 5.0,
            current_atr=550.0,
            vix=13.5,
            or_range=220.0,
            consecutive_closes_outside_rp1=2,
        )
        assert sig.action == "BUY_CALL"
        assert sig.target_strike == 77700.0
        assert sig.target_1_spot == grid.rp2_upper
        assert sig.is_order_action is False
        assert sig.broker_api_called is False
