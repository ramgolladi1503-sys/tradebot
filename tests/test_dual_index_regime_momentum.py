"""Unit tests for Dual-Index Regime Momentum Strategy.

Verifies:
1. Pure causality: zero lookahead, relies only on pre-market close & 09:15-09:20 open.
2. Positive consensus gap triggers ENTER_LONG / BUY_CALL.
3. Asymmetric or insufficient gap triggers NO_TRADE.
4. Timing window enforcement (09:20 - 09:30 IST only).
5. Invariant safety: read_only=True, is_order_action=False, broker_api_called=False.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from core.movement_contract import StrategyCandidate, StrategyContext
from strategies.dual_index_regime_momentum import (
    DualIndexRegimeInput,
    DualIndexRegimeSignal,
    calculate_gap_pct,
    evaluate_dual_index_momentum,
    generate_candidate,
    STRATEGY_ID,
)

IST = ZoneInfo("Asia/Kolkata")


def test_gap_percentage_calculation():
    # +1.0% gap
    gap = calculate_gap_pct(25250.0, 25000.0)
    assert round(gap, 2) == 1.0

    # -0.5% gap
    gap_down = calculate_gap_pct(24875.0, 25000.0)
    assert round(gap_down, 2) == -0.5

    # Zero denominator protection
    assert calculate_gap_pct(25000.0, 0.0) == 0.0


def test_dual_index_consensus_trigger_at_valid_time():
    eval_time = datetime(2026, 10, 22, 9, 21, 0, tzinfo=IST)
    inp = DualIndexRegimeInput(
        symbol="NIFTY",
        nifty_open=25100.0,
        nifty_prev_close=25000.0,  # +0.40% gap
        sensex_open=81500.0,
        sensex_prev_close=81200.0,  # +0.37% gap
        evaluation_time=eval_time,
        current_ltp=25110.0,
    )

    sig = evaluate_dual_index_momentum(inp, min_gap_pct=0.20, consensus_gap_pct=0.20)
    assert sig.decision == "ENTER_LONG"
    assert sig.direction == "BUY_CALL"
    assert sig.read_only is True
    assert sig.broker_api_called is False
    assert sig.is_causal is True
    assert "Consensus Gap confirmed" in sig.reason


def test_dual_index_asymmetric_gap_no_trade():
    eval_time = datetime(2026, 10, 22, 9, 21, 0, tzinfo=IST)
    # NIFTY gap up, but SENSEX flat / negative
    inp = DualIndexRegimeInput(
        symbol="NIFTY",
        nifty_open=25100.0,
        nifty_prev_close=25000.0,  # +0.40% gap
        sensex_open=81200.0,
        sensex_prev_close=81200.0,  # 0.00% gap
        evaluation_time=eval_time,
        current_ltp=25110.0,
    )

    sig = evaluate_dual_index_momentum(inp, min_gap_pct=0.20, consensus_gap_pct=0.20)
    assert sig.decision == "NO_TRADE"
    assert sig.direction == "NO_TRADE"
    assert "Threshold not met" in sig.reason


def test_timing_window_guard():
    # Outside allowed window: 09:15 (too early, opening bar not settled)
    too_early = datetime(2026, 10, 22, 9, 15, 30, tzinfo=IST)
    inp_early = DualIndexRegimeInput(
        symbol="NIFTY",
        nifty_open=25100.0,
        nifty_prev_close=25000.0,
        sensex_open=81500.0,
        sensex_prev_close=81200.0,
        evaluation_time=too_early,
        current_ltp=25110.0,
    )
    sig_early = evaluate_dual_index_momentum(inp_early)
    assert sig_early.decision == "NO_TRADE"
    assert "Outside allowed execution window" in sig_early.reason

    # Outside allowed window: 10:00 (too late to capture morning regime drift)
    too_late = datetime(2026, 10, 22, 10, 0, 0, tzinfo=IST)
    inp_late = DualIndexRegimeInput(
        symbol="NIFTY",
        nifty_open=25100.0,
        nifty_prev_close=25000.0,
        sensex_open=81500.0,
        sensex_prev_close=81200.0,
        evaluation_time=too_late,
        current_ltp=25110.0,
    )
    sig_late = evaluate_dual_index_momentum(inp_late)
    assert sig_late.decision == "NO_TRADE"
    assert "Outside allowed execution window" in sig_late.reason


def test_generate_candidate_contract_invariants():
    context = StrategyContext(
        symbol="NIFTY",
        spot_ltp=25110.0,
        open_price=25100.0,
    )
    market_snapshot = {
        "symbols": {
            "NIFTY": {
                "ltp": 25110.0,
                "prev_close": 25000.0,
                "ohlc": {"open": 25100.0, "high": 25120.0, "low": 25090.0, "close": 25110.0},
            },
            "SENSEX": {
                "ltp": 81510.0,
                "prev_close": 81200.0,
                "ohlc": {"open": 81500.0, "high": 81550.0, "low": 81490.0, "close": 81510.0},
            },
        }
    }

    # Running generate_candidate returns a valid StrategyCandidate
    candidate = generate_candidate(context, market_snapshot)
    assert isinstance(candidate, StrategyCandidate)
    assert candidate.strategy_id == STRATEGY_ID
    assert candidate.symbol == "NIFTY"
    assert candidate.evidence.get("read_only") is True
    assert candidate.evidence.get("is_order_action") is False
    assert candidate.evidence.get("broker_api_called") is False
