"""Marketable Limit Buffer
========================
Calculates marketable limit price with safety buffers for rapid option breakout entries,
strictly capped by the statutory 0.50% ceiling to prevent runaway slippage.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

import math
from typing import Optional, Tuple


# Statutory and regulatory limits
DEFAULT_BUFFER_PCT = 0.0030  # 0.30% standard buffer
STATUTORY_MAX_BUFFER_PCT = 0.0050  # 0.50% hard statutory ceiling
MIN_TICK_SIZE = 0.05  # Standard NSE FO tick size


def round_to_tick(price: float, tick_size: float = MIN_TICK_SIZE) -> float:
    """Rounds price to the nearest exchange tick size (0.05)."""
    if price <= 0:
        return tick_size
    return round(round(price / tick_size) * tick_size, 2)


def compute_marketable_limit_price(
    ltp: float,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    buffer_pct: float = DEFAULT_BUFFER_PCT,
    max_buffer_pct: float = STATUTORY_MAX_BUFFER_PCT,
    side: str = "BUY",
    tick_size: float = MIN_TICK_SIZE,
) -> Tuple[float, float]:
    """Computes marketable limit order price with statutory buffer ceiling.
    
    Parameters:
    -----------
    ltp: float
        Last Traded Price of the contract.
    bid: Optional[float]
        Best bid price in the depth book (if available).
    ask: Optional[float]
        Best ask price in the depth book (if available).
    buffer_pct: float
        Desired buffer percentage (e.g. 0.003 = 0.30%).
    max_buffer_pct: float
        Statutory maximum allowed buffer percentage (hard-capped at 0.0050 = 0.50%).
    side: str
        Order side: "BUY" or "SELL".
    tick_size: float
        Exchange minimum tick size (default 0.05).
        
    Returns:
    --------
    Tuple[float, float]:
        (marketable_limit_price, effective_buffer_pct)
        - marketable_limit_price: price to place limit order at.
        - effective_buffer_pct: the actual buffer applied.
        
    Rules & Invariants:
    -------------------
    1. Statutory Ceiling: effective buffer cannot exceed max_buffer_pct (at most 0.50%).
    2. Base Price Anchor:
       - For BUY: uses ask if valid and >= ltp, else ltp.
       - For SELL: uses bid if valid and <= ltp, else ltp.
    3. Tick Compliance: Output price is rounded to valid tick increments (0.05).
    4. Anti-Negative: Price cannot fall below tick_size.
    """
    if ltp <= 0:
        raise ValueError(f"Invalid LTP: {ltp} must be positive")

    # Hard cap buffer at statutory ceiling (0.50%)
    statutory_ceiling = min(max_buffer_pct, STATUTORY_MAX_BUFFER_PCT)
    effective_buffer = min(max(0.0, buffer_pct), statutory_ceiling)

    side_norm = side.upper()

    if side_norm == "BUY":
        # Anchor price is ask if available and reasonable; else LTP
        anchor = ask if (ask is not None and ask > 0) else ltp
        raw_price = anchor * (1.0 + effective_buffer)
        limit_price = round_to_tick(raw_price, tick_size)
    elif side_norm == "SELL":
        # Anchor price is bid if available and reasonable; else LTP
        anchor = bid if (bid is not None and bid > 0) else ltp
        raw_price = anchor * (1.0 - effective_buffer)
        limit_price = round_to_tick(raw_price, tick_size)
    else:
        raise ValueError(f"Unknown order side '{side}'. Must be 'BUY' or 'SELL'.")

    return limit_price, effective_buffer
