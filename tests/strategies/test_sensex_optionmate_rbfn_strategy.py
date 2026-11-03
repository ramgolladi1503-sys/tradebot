"""
Unit Test Suite for Sensex Option Mate RBFN Strategy Engine
==========================================================
Verifies:
1. Sensex 100-point step size rounding.
2. DTE-adaptive sustainable price anchors (Wednesday DTE=2: Rs 220, Expiry DTE=0: Rs 28).
3. Directional discipline (Calls strictly above TD, Puts strictly below TD).
4. Gate 2 Frictional Hurdle (ATR >= 450.0, VIX >= 12.0).
5. Gate 3 Confirmed Midday Reversal (2 consecutive 5m candle closes inside boundary).
6. Strict safety invariants (read_only=True, is_order_action=False, broker_api_called=False).
"""

import pytest
from strategies.sensex_optionmate_rbfn_strategy import (
    SensexOptionMateRBFNStrategy,
    SensexOptionMateGrid,
    SensexOptionMateSignal,
)


def test_sensex_daily_grid_boundaries_and_dte_anchors():
    strat = SensexOptionMateRBFNStrategy(step_size=100)
    
    # Wednesday session (DTE = 2)
    grid_wed = strat.compute_daily_grid(
        date="2026-11-04",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=600.0,
        vix=14.0,
        dte=2,
    )
    
    assert grid_wed.trend_decider == 79300.0
    assert grid_wed.sustainable_price_anchor == 220.0
    assert grid_wed.rp1_upper == pytest.approx(79300.0 + 0.382 * 600.0, 0.1)
    assert grid_wed.rp1_lower == pytest.approx(79300.0 - 0.382 * 600.0, 0.1)
    assert grid_wed.target_call_strike % 100 == 0
    assert grid_wed.target_put_strike % 100 == 0

    # Expiry session (DTE = 0)
    grid_exp = strat.compute_daily_grid(
        date="2026-11-06",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=600.0,
        vix=14.0,
        dte=0,
    )
    assert grid_exp.sustainable_price_anchor == 28.0


def test_sensex_directional_discipline_bullish():
    strat = SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=400.0)
    grid = strat.compute_daily_grid(
        date="2026-11-04",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=550.0,
        vix=13.5,
        dte=2,
    )
    # Spot 79350 > TD (79300) + 20
    sig = strat.generate_signal(grid, current_spot=79350.0, current_atr=550.0, vix=13.5)
    assert sig.action == "BUY_CALL"
    assert sig.target_strike == grid.target_call_strike
    assert sig.target_strike % 100 == 0
    assert sig.is_vetoed is False
    assert sig.entry_premium_est == 220.0


def test_sensex_directional_discipline_bearish():
    strat = SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=400.0)
    grid = strat.compute_daily_grid(
        date="2026-11-04",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=550.0,
        vix=13.5,
        dte=2,
    )
    # Spot 79250 < TD (79300) - 20
    sig = strat.generate_signal(grid, current_spot=79250.0, current_atr=550.0, vix=13.5)
    assert sig.action == "BUY_PUT"
    assert sig.target_strike == grid.target_put_strike
    assert sig.target_strike % 100 == 0
    assert sig.is_vetoed is False


def test_sensex_gate_2_frictional_hurdle_veto():
    strat = SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=450.0, min_vix_hurdle=12.0)
    grid = strat.compute_daily_grid(
        date="2026-11-04",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=350.0,  # Below 450.0 hurdle
        vix=11.5,      # Below 12.0 hurdle
        dte=2,
    )
    sig = strat.generate_signal(grid, current_spot=79350.0, current_atr=350.0, vix=11.5)
    assert sig.action == "ABSTAIN"
    assert sig.is_vetoed is True
    assert "GATE_2" in sig.veto_reason


def test_sensex_gate_3_midday_reversal_confirmation():
    strat = SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=400.0)
    grid = strat.compute_daily_grid(
        date="2026-11-04",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=500.0,
        vix=14.0,
        dte=2,
    )
    # RP1 Upper = 79300 + 0.382 * 500 = 79491.0
    # Spot touched 79500 (tested RP1), now candles close at 79470, 79465 (inside boundary)
    rev_sig = strat.evaluate_midday_reversal(
        grid=grid,
        current_spot=79465.0,
        recent_candle_closes=[79470.0, 79465.0],
        recent_candle_highs=[79510.0, 79480.0],
        recent_candle_lows=[79450.0, 79440.0],
        current_atr=500.0,
        vix=14.0,
    )
    assert rev_sig is not None
    assert rev_sig.action == "BUY_PUT"
    assert rev_sig.target_1_spot == grid.trend_decider
    assert rev_sig.trade_phase == "MIDDAY_REVERSAL"
    assert rev_sig.is_vetoed is False


def test_sensex_safety_invariants():
    strat = SensexOptionMateRBFNStrategy(step_size=100, min_atr_frictional_hurdle=400.0)
    grid = strat.compute_daily_grid(
        date="2026-11-04",
        spot_open=79400.0,
        prev_close=79200.0,
        atr_14=500.0,
        vix=14.0,
        dte=2,
    )
    sig = strat.generate_signal(grid, current_spot=79350.0, current_atr=500.0, vix=14.0)
    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False
    assert sig.allowed_for_live_execution is False
