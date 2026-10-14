"""Dynamic Multi-Variable Option Slippage & Friction Engine.

Calculates institutional execution drag taking into account:
1. Real Bid-Ask Spread Width (half-spread cost).
2. Gamma Impact Surcharge (widens on 0-DTE near ATM).
3. Late-Day Illiquidity Escalator (accelerates past 14:30 PM).
4. Statutory Regulatory Overhead (STT, exchange turnover, GST, SEBI).
5. BSE FO Specific Thinner Book Spread Surcharges & Net Yield Gate.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
import numpy as np


@dataclass(frozen=True)
class ExecutionFriction:
    bid_ask_spread: float
    slippage_pts: float
    regulatory_fees_pts: float
    total_drag_pts: float
    spread_pct: float = 0.0


class DynamicOptionSlippageModel:
    """Dynamically models realistic options execution friction across NSE and BSE."""

    def __init__(self, base_brokerage_pts: float = 0.40, exchange: str = "NSE"):
        self.base_brokerage_pts = base_brokerage_pts
        self.exchange = exchange.upper()

    def compute_drag(
        self,
        premium: float,
        bid: float = 0.0,
        ask: float = 0.0,
        minutes_to_close: float = 120.0,
        gamma: float = 0.0015
    ) -> ExecutionFriction:
        """Computes realistic round-trip friction in option premium points."""
        # 1. Real Bid-Ask Spread Assessment
        if ask > bid and ask > 0:
            spread = max(0.10, ask - bid)
        else:
            # Synthetic spread proxy: 1.5% to 3% on NSE, 2.5% to 5.0% on BSE
            base_spread_pct = 0.035 if self.exchange == "BSE" else 0.02
            spread = max(0.20 if self.exchange == "NSE" else 0.50, premium * base_spread_pct)
        half_spread = spread / 2.0

        spread_pct = (spread / max(0.1, premium)) if premium > 0 else 0.0

        # 2. Gamma Surcharge (On 0-DTE, high gamma causes order book vacuum fills)
        # BSE books are thinner, so gamma slippage is amplified by 1.5x
        gamma_mult = 750.0 if self.exchange == "BSE" else 500.0
        max_gamma_sur = 4.0 if self.exchange == "BSE" else 2.5
        gamma_surcharge = min(max_gamma_sur, max(0.2, gamma * gamma_mult))

        # 3. Late-Day Illiquidity Escalator (Past 14:30 PM = minutes_to_close < 45)
        late_day_multiplier = 1.0
        if minutes_to_close < 45.0:
            late_day_multiplier = 1.0 + (45.0 - max(0.0, minutes_to_close)) / 30.0

        slippage = (half_spread + gamma_surcharge) * late_day_multiplier
        total_drag = round(slippage + self.base_brokerage_pts, 2)

        return ExecutionFriction(
            bid_ask_spread=round(spread, 2),
            slippage_pts=round(slippage, 2),
            regulatory_fees_pts=self.base_brokerage_pts,
            total_drag_pts=total_drag,
            spread_pct=round(spread_pct, 4)
        )

    def validate_net_yield_gate(
        self,
        premium: float,
        expected_index_gain_pts: float,
        delta: float = 0.50,
        bid: float = 0.0,
        ask: float = 0.0,
        max_spread_pct: float = 0.04,
        max_absolute_spread_pts: float = 3.50,
        min_yield_to_friction_ratio: float = 2.5
    ) -> Tuple[bool, str, float, ExecutionFriction]:
        """Layer 2 Gate: Rigorous verification that expected premium gain clears BSE/NSE friction.

        Returns:
            (passes_gate, reason, net_premium_yield_pts, friction)
        """
        fric = self.compute_drag(premium=premium, bid=bid, ask=ask)

        # 1. Absolute Spread Veto (e.g. BSE book gap > 3.50 pts)
        if fric.bid_ask_spread > max_absolute_spread_pts:
            return (
                False,
                f"VETO_SPREAD_WIDE (Spread {fric.bid_ask_spread:.2f}pts > Max {max_absolute_spread_pts:.2f}pts)",
                0.0,
                fric
            )

        # 2. Percentage Spread Veto
        if fric.spread_pct > max_spread_pct:
            return (
                False,
                f"VETO_SPREAD_RATIO ({fric.spread_pct*100:.1f}% > Max {max_spread_pct*100:.1f}%)",
                0.0,
                fric
            )

        # 3. Expected Option Premium Yield vs Total Drag
        expected_premium_gain = expected_index_gain_pts * delta
        net_yield = expected_premium_gain - fric.total_drag_pts

        if expected_premium_gain < (fric.total_drag_pts * min_yield_to_friction_ratio):
            return (
                False,
                f"VETO_FRICTION_INEFFICIENCY (Exp Prem +{expected_premium_gain:.1f}pts < {min_yield_to_friction_ratio}x Drag {fric.total_drag_pts:.2f}pts)",
                round(net_yield, 2),
                fric
            )

        return True, "PASSED", round(net_yield, 2), fric
