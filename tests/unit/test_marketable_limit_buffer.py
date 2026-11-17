"""Unit Tests for Marketable Limit Buffer
========================================
Verifies marketable limit price computation, statutory 0.50% buffer ceiling,
tick rounding compliance, and depth-book ask/bid anchoring.

Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
"""

import pytest
from core.execution.marketable_limit_buffer import (
    compute_marketable_limit_price,
    STATUTORY_MAX_BUFFER_PCT,
    DEFAULT_BUFFER_PCT,
    round_to_tick,
)


def test_statutory_buffer_ceiling():
    # Attempting to use a buffer > 0.50% (e.g. 2.0% or 10.0%) must be hard-capped at 0.50%
    price, effective_buf = compute_marketable_limit_price(
        ltp=100.0,
        buffer_pct=0.02,  # 2% requested
        max_buffer_pct=0.0050,
    )
    assert effective_buf == STATUTORY_MAX_BUFFER_PCT
    # 100 * 1.0050 = 100.50
    assert price == 100.50

    # Even if max_buffer_pct argument is passed higher than statutory ceiling, statutory ceiling wins
    price_high, effective_buf_high = compute_marketable_limit_price(
        ltp=100.0,
        buffer_pct=0.05,  # 5% requested
        max_buffer_pct=0.10,  # 10% requested max
    )
    assert effective_buf_high == STATUTORY_MAX_BUFFER_PCT
    assert price_high == 100.50


def test_buy_limit_price_anchoring():
    # Case 1: Ask available and higher than LTP
    price_ask, _ = compute_marketable_limit_price(
        ltp=20.0,
        bid=19.90,
        ask=20.10,
        buffer_pct=0.0030,  # 0.30%
        side="BUY",
    )
    # 20.10 * 1.003 = 20.1603 -> nearest tick (0.05) is 20.15
    assert price_ask == 20.15

    # Case 2: No depth available -> uses LTP
    price_ltp, _ = compute_marketable_limit_price(
        ltp=20.0,
        bid=None,
        ask=None,
        buffer_pct=0.0030,
        side="BUY",
    )
    # 20.00 * 1.003 = 20.06 -> nearest tick is 20.05
    assert price_ltp == 20.05


def test_sell_limit_price_anchoring():
    # For SELL side: price is buffered downwards
    price_bid, _ = compute_marketable_limit_price(
        ltp=50.0,
        bid=49.80,
        ask=50.00,
        buffer_pct=0.0030,
        side="SELL",
    )
    # 49.80 * (1 - 0.003) = 49.6506 -> nearest tick is 49.65
    assert price_bid == 49.65


def test_tick_rounding():
    assert round_to_tick(18.63) == 18.65
    assert round_to_tick(18.62) == 18.60
    assert round_to_tick(18.60) == 18.60
    assert round_to_tick(-5.0) == 0.05  # Anti-negative clamp


def test_invalid_parameters():
    with pytest.raises(ValueError, match="Invalid LTP"):
        compute_marketable_limit_price(ltp=0.0)

    with pytest.raises(ValueError, match="Unknown order side"):
        compute_marketable_limit_price(ltp=50.0, side="HOLD")
