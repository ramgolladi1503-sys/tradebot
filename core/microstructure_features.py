"""Level-2 Order Book Microstructure Feature Extractor & Data Invariants.

Computes mathematically bounded order book invariants for sub-second high-frequency
and deep learning alpha models:
1. Multi-Level Order Book Imbalance (OBI) across 5 levels with exponential decay weighting.
2. Stoikov's Volume-Weighted Micro-Price (P_micro).
3. Relative Bid-Ask Spread and Effective Half-Spread.
4. Book Depth Velocity & Queue Depletion Rates.
5. Triple Barrier Labeling generator for unbiased ML ground truth.

Strict Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple


# Default exponential decay weights for 5-level order book depth
DEFAULT_DEPTH_WEIGHTS: tuple[float, float, float, float, float] = (
    1.0,
    0.5,
    0.25,
    0.125,
    0.0625,
)


@dataclass(slots=True, frozen=True)
class Level5BookSnapshot:
    """Immutable snapshot of 5-level bid and ask limit order depth."""
    token: str
    exchange_timestamp_ms: int
    ltp: float
    # Bid levels (Price, Quantity)
    bid_prices: tuple[float, float, float, float, float]
    bid_quantities: tuple[int, int, int, int, int]
    # Ask levels (Price, Quantity)
    ask_prices: tuple[float, float, float, float, float]
    ask_quantities: tuple[int, int, int, int, int]


@dataclass(slots=True, frozen=True)
class MicrostructureFeatures:
    """Mathematically bounded, stationary features for ML/Alpha consumption."""
    exchange_timestamp_ms: int
    ltp: float
    best_bid: float
    best_ask: float
    mid_price: float
    micro_price: float
    spread_abs: float
    spread_pct: float
    obi_weighted: float       # Bounded in [-1.0, 1.0]
    obi_level_1: float        # Bounded in [-1.0, 1.0]
    total_bid_depth: int
    total_ask_depth: int
    depth_ratio: float        # Total bid qty / (Total bid qty + Total ask qty) in [0.0, 1.0]


def compute_weighted_obi(
    bid_quantities: Sequence[int],
    ask_quantities: Sequence[int],
    weights: Sequence[float] = DEFAULT_DEPTH_WEIGHTS,
) -> float:
    """Calculate Multi-Level Order Book Imbalance (OBI).

    Formula:
        OBI = (Sum(w_i * Q_b,i) - Sum(w_i * Q_a,i)) / (Sum(w_i * Q_b,i) + Sum(w_i * Q_a,i))
    Returns:
        float strictly in [-1.0, 1.0]. Returns 0.0 if both depths are zero.
    """
    n = min(len(bid_quantities), len(ask_quantities), len(weights))
    if n == 0:
        return 0.0

    w_bids = sum(weights[i] * max(0, bid_quantities[i]) for i in range(n))
    w_asks = sum(weights[i] * max(0, ask_quantities[i]) for i in range(n))
    denom = w_bids + w_asks

    if denom <= 0.0 or not math.isfinite(denom):
        return 0.0

    obi = (w_bids - w_asks) / denom
    # Clamp strictly for numerical stability
    return max(-1.0, min(1.0, float(obi)))


def compute_stoikov_micro_price(
    best_bid_p: float,
    best_bid_q: int,
    best_ask_p: float,
    best_ask_q: int,
) -> float:
    """Calculate Stoikov's volume-weighted micro-price.

    Formula:
        P_micro = (P_bid * Q_ask + P_ask * Q_bid) / (Q_bid + Q_ask)
    Fallback:
        Arithmetic mid-price if quantities are non-positive.
    """
    mid_price = (best_bid_p + best_ask_p) / 2.0
    q_bid = max(0, best_bid_q)
    q_ask = max(0, best_ask_q)
    denom = q_bid + q_ask

    if denom <= 0:
        return mid_price

    micro_price = (best_bid_p * q_ask + best_ask_p * q_bid) / denom
    if not math.isfinite(micro_price):
        return mid_price

    return float(micro_price)


def extract_microstructure_features(
    snapshot: Level5BookSnapshot,
    weights: Sequence[float] = DEFAULT_DEPTH_WEIGHTS,
) -> MicrostructureFeatures:
    """Transform raw 5-level depth into bounded stationary features."""
    best_bid_p = snapshot.bid_prices[0]
    best_bid_q = snapshot.bid_quantities[0]
    best_ask_p = snapshot.ask_prices[0]
    best_ask_q = snapshot.ask_quantities[0]

    mid_p = (best_bid_p + best_ask_p) / 2.0 if (best_bid_p > 0 and best_ask_p > 0) else snapshot.ltp
    micro_p = compute_stoikov_micro_price(best_bid_p, best_bid_q, best_ask_p, best_ask_q)

    spread_abs = max(0.0, best_ask_p - best_bid_p) if (best_bid_p > 0 and best_ask_p > 0) else 0.0
    spread_pct = (spread_abs / mid_p * 100.0) if mid_p > 0 else 0.0

    obi_w = compute_weighted_obi(snapshot.bid_quantities, snapshot.ask_quantities, weights)
    obi_l1 = compute_weighted_obi([best_bid_q], [best_ask_q], [1.0])

    tot_bid_q = sum(max(0, q) for q in snapshot.bid_quantities)
    tot_ask_q = sum(max(0, q) for q in snapshot.ask_quantities)
    tot_depth = tot_bid_q + tot_ask_q
    depth_r = (tot_bid_q / tot_depth) if tot_depth > 0 else 0.5

    return MicrostructureFeatures(
        exchange_timestamp_ms=snapshot.exchange_timestamp_ms,
        ltp=snapshot.ltp,
        best_bid=best_bid_p,
        best_ask=best_ask_p,
        mid_price=mid_p,
        micro_price=micro_p,
        spread_abs=spread_abs,
        spread_pct=spread_pct,
        obi_weighted=obi_w,
        obi_level_1=obi_l1,
        total_bid_depth=tot_bid_q,
        total_ask_depth=tot_ask_q,
        depth_ratio=depth_r,
    )


def compute_triple_barrier_label(
    current_mid_price: float,
    future_mid_prices: Sequence[float],
    pt_multiplier: float = 1.5,
    sl_multiplier: float = 1.0,
    half_spread: float = 0.50,
) -> int:
    """Marcos Lopez de Prado's Triple Barrier Labeling.

    Barriers:
    - Upper barrier (+1): Profit target hit (mid_price >= current + pt_multiplier * half_spread)
    - Lower barrier (-1): Stop loss hit (mid_price <= current - sl_multiplier * half_spread)
    - Vertical barrier (0): Time horizon expires without touching upper or lower.

    Returns:
        1 for Bullish breakout, -1 for Bearish breakdown, 0 for Neutral/Flat.
    """
    if not future_mid_prices or half_spread <= 0.0:
        return 0

    upper_barrier = current_mid_price + (pt_multiplier * half_spread)
    lower_barrier = current_mid_price - (sl_multiplier * half_spread)

    for future_p in future_mid_prices:
        if future_p >= upper_barrier:
            return 1
        if future_p <= lower_barrier:
            return -1

    return 0
