"""
Unit & Regression Tests for Option Mate RBFN Strategy.

Proves:
1. Non-linear Gaussian volatility expansion calculation.
2. Directional discipline (Call above Trend Decider, Put below Trend Decider).
3. Dynamic Slingshot strike selection at step size boundaries.
4. Non-negotiable repository safety invariants (read_only=True, is_order_action=False).
"""

import pytest
from strategies.optionmate_rbfn_strategy import OptionMateRBFNStrategy, OptionMateGrid, OptionMateSignal


def test_optionmate_grid_calculation():
    strategy = OptionMateRBFNStrategy(step_size=50)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23570.0,
        prev_close=23550.0,
        atr_14=130.0,
        vix=14.0,
        pro_client_divergence=50000.0,
    )

    # 1. Trend Decider: 0.5 * (23570 + 23550) + (0.05 * 130 * 1.0) = 23560 + 6.5 = 23566.5
    assert grid.trend_decider == 23566.5

    # 2. Reversal Price 1 (38.2%): 23566.5 + (0.382 * 130.0 * 1.0) = 23566.5 + 49.66 = 23616.16
    assert abs(grid.rp1_upper - 23616.16) < 0.1
    # 3. Reversal Price 2 (68.2%): 23566.5 + (0.682 * 130.0 * 1.0) = 23566.5 + 88.66 = 23655.16
    assert abs(grid.rp2_upper - 23655.16) < 0.1

    # 4. Slingshot Strike Selection:
    # Call strike should be rounded to nearest 50 for 23616.16 -> 23600.0
    assert grid.call_strike == 23600.0
    # Put strike should be rounded to nearest 50 for 23566.5 - 49.66 = 23516.84 -> 23500.0
    assert grid.put_strike == 23500.0


def test_optionmate_directional_signal_bullish():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23650.0,
        prev_close=23550.0,
        atr_14=140.0,
        vix=14.0,
    )
    # Trend Decider is 23600.0
    assert grid.trend_decider == 23600.0

    # Test spot at 09:30 is 23620.0 (Above Trend Decider)
    signal = strategy.generate_signal(grid, current_spot=23620.0, current_atr=140.0, vix=14.0)
    assert signal.action == "BUY_CALL"
    assert signal.target_strike == grid.call_strike
    assert signal.invalidation_spot < grid.trend_decider
    assert signal.take_profit_pts > signal.stop_loss_pts * 2.0  # Asymmetric R:R
    assert signal.is_vetoed is False


def test_optionmate_directional_signal_bearish():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23500.0,
        prev_close=23550.0,
        atr_14=140.0,
        vix=14.0,
    )
    # Trend Decider is 23525.0
    assert grid.trend_decider == 23525.0

    # Test spot at 09:30 is 23480.0 (Below Trend Decider)
    signal = strategy.generate_signal(grid, current_spot=23480.0, current_atr=140.0, vix=14.0)
    assert signal.action == "BUY_PUT"
    assert signal.target_strike == grid.put_strike
    assert signal.invalidation_spot > grid.trend_decider
    assert signal.take_profit_pts > signal.stop_loss_pts * 2.0
    assert signal.is_vetoed is False


def test_optionmate_gate_2_atr_veto():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=150.0)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23650.0,
        prev_close=23550.0,
        atr_14=120.0,  # Below 150 hurdle
        vix=14.0,
    )
    signal = strategy.generate_signal(grid, current_spot=23620.0, current_atr=120.0, vix=14.0)
    assert signal.action == "ABSTAIN"
    assert signal.is_vetoed is True
    assert "GATE_2_VETO" in signal.veto_reason


def test_optionmate_gate_3_midday_reversal_confirmation():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0, reversal_confirmation_bars=2)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23500.0,
        prev_close=23500.0,
        atr_14=160.0,
        vix=14.0,
    )
    # rp1_upper is ~23561.12
    # Case A: False touch (wick touches rp1_upper, but closes continue up - NO reversal)
    unconfirmed = strategy.evaluate_midday_reversal(
        grid=grid,
        current_spot=23570.0,
        recent_candle_closes=[23565.0, 23570.0],  # Closes above rp1_upper - 5.0
        recent_candle_highs=[23568.0, 23575.0],
        recent_candle_lows=[23550.0, 23560.0],
        current_atr=160.0,
        vix=14.0,
    )
    assert unconfirmed is None  # Fading breakout prevented!

    # Case B: Confirmed 2-bar rejection close below rp1_upper - 5.0
    confirmed = strategy.evaluate_midday_reversal(
        grid=grid,
        current_spot=23545.0,
        recent_candle_closes=[23550.0, 23545.0],  # Confirmed rejection closes
        recent_candle_highs=[23570.0, 23555.0],   # Touched RP1 upper
        recent_candle_lows=[23540.0, 23540.0],
        current_atr=160.0,
        vix=14.0,
    )
    assert confirmed is not None
    assert confirmed.action == "BUY_PUT"
    assert confirmed.trade_phase == "MIDDAY_REVERSAL"
    assert confirmed.target_1_spot == grid.trend_decider
    assert "Gate 3 Reversal Confirmed" in confirmed.narrative


def test_safety_and_governance_invariants():
    strategy = OptionMateRBFNStrategy(step_size=50)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=24000.0,
        prev_close=24000.0,
        atr_14=100.0,
        vix=12.0,
    )
    signal = strategy.generate_signal(grid, current_spot=24010.0, current_atr=100.0)

    # Repository safety compliance
    assert grid.read_only is True
    assert grid.is_order_action is False
    assert grid.broker_api_called is False
    assert grid.allowed_for_live_execution is False

    assert signal.read_only is True
    assert signal.is_order_action is False
    assert signal.broker_api_called is False
    assert signal.allowed_for_live_execution is False
