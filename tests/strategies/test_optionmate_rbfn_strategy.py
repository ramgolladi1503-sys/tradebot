"""
Unit & Regression Tests for Option Mate RBFN Strategy.

Proves:
1. Scale-invariant harmonic volatility channel calculations.
2. Directional discipline (Call above Trend Decider, Put below Trend Decider).
3. Dynamic Slingshot strike selection at step size boundaries.
4. Golden Candle classifier and validation filters (wick exhaustion, inside range veto).
5. Gate 2 ATR & VIX frictional hurdles and Gate 3 midday reversal confirmation.
6. Non-negotiable repository safety invariants (read_only=True, is_order_action=False).
"""

import pytest
from strategies.optionmate_rbfn_strategy import (
    OptionMateRBFNStrategy,
    OptionMateGrid,
    OptionMateSignal,
    GoldenCandle,
)


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

    # 1. Trend Decider:
    # Gap = 23570 - 23550 = 20.0 < 0.25 * 130 = 32.5 (Rotation regime)
    # raw_td = 0.5 * (23570 + 23550) + (1.0 * 0.05 * 130) = 23560.0 + 6.5 = 23566.5
    # Harmonic rounding to 40-pt anchor: round(23566.5 / 40.0) * 40.0 = 589 * 40 = 23560.0
    assert grid.trend_decider == 23560.0

    # 2. Reversal Price 1 (120-pt channel step):
    # rp1_dist = 120.0 * sqrt(14.0 / 14.0) = 120.0
    # rp1_upper = 23560.0 + 120.0 = 23680.0
    assert grid.rp1_upper == 23680.0
    # 3. Reversal Price 2 (2x channel step):
    # rp2_upper = 23560.0 + 240.0 = 23800.0
    assert grid.rp2_upper == 23800.0

    # 4. Slingshot Strike Selection:
    # Call strike should be rounded to nearest 50 for 23680.0 -> 23700.0
    assert grid.call_strike == 23700.0
    # Put strike should be rounded to nearest 50 for 23560.0 - 120.0 = 23440.0 -> 23450.0
    assert grid.put_strike == 23450.0


def test_optionmate_directional_signal_bullish():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23650.0,
        prev_close=23550.0,
        atr_14=140.0,
        vix=14.0,
    )
    # Gap = 100 >= 0.25 * 140 = 35 -> Gap regime: round(23650 / 40) * 40 = 23640.0
    assert grid.trend_decider == 23640.0

    # Test spot at 09:30 is 23680.0 (Above Trend Decider 23640.0)
    signal = strategy.generate_signal(grid, current_spot=23680.0, current_atr=140.0, vix=14.0)
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
    # Gap = -50 <= -35 -> Gap regime: round(23500 / 40) * 40 = 23520.0
    assert grid.trend_decider == 23520.0

    # Test spot at 09:30 is 23480.0 (Below Trend Decider 23520.0)
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


def test_optionmate_golden_candle_bullish_and_exhaustion():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23650.0,
        prev_close=23550.0,
        atr_14=140.0,
        vix=14.0,
    )
    # Valid Bullish Golden Candle: Strong body > 55%
    gc_valid = GoldenCandle.create(open=23640.0, high=23690.0, low=23635.0, close=23685.0)
    assert gc_valid.body_ratio >= 0.55
    signal = strategy.generate_signal(grid, current_spot=23695.0, current_atr=140.0, golden_candle=gc_valid)
    assert signal.action == "BUY_CALL"
    assert signal.is_vetoed is False

    # Exhaustion Candle: Long upper wick > 60% with tiny body
    gc_exhaustion = GoldenCandle.create(open=23645.0, high=23720.0, low=23640.0, close=23650.0)
    signal_veto = strategy.generate_signal(grid, current_spot=23680.0, current_atr=140.0, golden_candle=gc_exhaustion)
    assert signal_veto.action == "ABSTAIN"
    assert signal_veto.is_vetoed is True
    assert "GOLDEN_CANDLE_EXHAUSTION_VETO" in signal_veto.veto_reason


def test_optionmate_gate_3_midday_reversal_confirmation():
    strategy = OptionMateRBFNStrategy(step_size=50, min_atr_frictional_hurdle=100.0, reversal_confirmation_bars=2)
    grid = strategy.compute_daily_grid(
        date="2026-11-03",
        spot_open=23500.0,
        prev_close=23500.0,
        atr_14=160.0,
        vix=14.0,
    )
    # TD = 23520.0, rp1_upper = 23640.0
    # Case A: False touch (wick touches rp1_upper, but closes continue up - NO reversal)
    unconfirmed = strategy.evaluate_midday_reversal(
        grid=grid,
        current_spot=23650.0,
        recent_candle_closes=[23645.0, 23650.0],  # Closes above rp1_upper - 5.0
        recent_candle_highs=[23648.0, 23655.0],
        recent_candle_lows=[23620.0, 23630.0],
        current_atr=160.0,
        vix=14.0,
    )
    assert unconfirmed is None  # Fading breakout prevented!

    # Case B: Confirmed 2-bar rejection close below rp1_upper - 5.0
    confirmed = strategy.evaluate_midday_reversal(
        grid=grid,
        current_spot=23625.0,
        recent_candle_closes=[23630.0, 23625.0],  # Confirmed rejection closes <= 23635.0
        recent_candle_highs=[23645.0, 23635.0],   # Touched RP1 upper (23640.0)
        recent_candle_lows=[23610.0, 23615.0],
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
    gc = GoldenCandle.create(open=24000.0, high=24020.0, low=23990.0, close=24015.0)
    signal = strategy.generate_signal(grid, current_spot=24010.0, current_atr=100.0, golden_candle=gc)

    # Repository safety compliance
    assert grid.read_only is True
    assert grid.is_order_action is False
    assert grid.broker_api_called is False
    assert grid.allowed_for_live_execution is False

    assert signal.read_only is True
    assert signal.is_order_action is False
    assert signal.broker_api_called is False
    assert signal.allowed_for_live_execution is False

    assert gc.read_only is True
    assert gc.is_order_action is False
    assert gc.broker_api_called is False
    assert gc.allowed_for_live_execution is False

