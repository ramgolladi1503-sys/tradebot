"""Liquidity Sweep & Straddle Pinning Reversal Engine.

Implements Strategy A & Hypothesis 2:
- Detects Previous Day High (PDH) or Previous Day Low (PDL) sweeps.
- Confirms institutional rejection when bar pierces extreme by 5-25 pts (NIFTY) / 20-70 pts (SENSEX)
  and closes back inside the prior-day boundary.
- Zero Lookahead: Signal evaluates on Bar T close; execution executes strictly on Bar T+1 Open.
- Asymmetric Risk/Reward: 4-6 pt stop loss above signal bar extreme targeting 45 pt (NIFTY) / 140 pt (SENSEX)
  snapback to session VWAP/midpoint (1:9 R:R).
- Max 1 attempt per boundary per day to prevent fighting runaway super-trends.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(slots=True, frozen=True)
class LiquiditySweepSignal:
    timestamp_ms: int
    index_name: str
    direction: str  # "PE" (Short / Fade PDH) or "CE" (Long / Fade PDL)
    sweep_type: str  # "PDH_SWEEP_REVERSAL" or "PDL_SWEEP_REVERSAL"
    boundary_price: float
    signal_bar_extreme: float
    trigger_price: float
    recommended_sl: float
    target_pts: float
    sl_pts: float
    is_expiry_boost: bool
    setup_reason: str


class LiquiditySweepEngine:
    """Detects and generates high-asymmetry reversal signals at prior-day extremes."""

    def __init__(
        self,
        nifty_max_sweep_pts: float = 25.0,
        sensex_max_sweep_pts: float = 70.0,
        nifty_target_pts: float = 45.0,
        sensex_target_pts: float = 140.0,
        nifty_sl_buffer_pts: float = 4.0,
        sensex_sl_buffer_pts: float = 15.0,
    ):
        self.nifty_max_sweep_pts = nifty_max_sweep_pts
        self.sensex_max_sweep_pts = sensex_max_sweep_pts
        self.nifty_target_pts = nifty_target_pts
        self.sensex_target_pts = sensex_target_pts
        self.nifty_sl_buffer_pts = nifty_sl_buffer_pts
        self.sensex_sl_buffer_pts = sensex_sl_buffer_pts

        # Guard: Track attempted sweeps per day per boundary to prevent fighting runaway super-trends
        self.attempted_boundaries: Dict[str, Dict[str, bool]] = {
            "NIFTY": {"PDH": False, "PDL": False},
            "SENSEX": {"PDH": False, "PDL": False},
            "BANKNIFTY": {"PDH": False, "PDL": False},
        }

    def reset_daily_boundaries(self) -> None:
        """Reset boundary attempt locks at the start of a new session."""
        for idx in self.attempted_boundaries:
            self.attempted_boundaries[idx]["PDH"] = False
            self.attempted_boundaries[idx]["PDL"] = False

    def evaluate_bar(
        self,
        index_name: str,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        pdh: float,
        pdl: float,
        timestamp_ms: int,
        is_expiry_session: bool = False,
        bar_time: Optional[datetime.time] = None,
    ) -> Optional[LiquiditySweepSignal]:
        """Evaluates a single 1-minute bar for a confirmed liquidity sweep."""
        # Liquidity sweep operating window: 09:30 to 12:00
        if bar_time is not None:
            if bar_time < datetime.time(9, 30) or bar_time > datetime.time(12, 0):
                return None

        if pdh <= 0 or pdl <= 0 or pdl >= pdh:
            return None

        is_sensex = (index_name == "SENSEX")
        max_sweep = self.sensex_max_sweep_pts if is_sensex else self.nifty_max_sweep_pts
        target_pts = self.sensex_target_pts if is_sensex else self.nifty_target_pts
        sl_buffer = self.sensex_sl_buffer_pts if is_sensex else self.nifty_sl_buffer_pts

        bounds = self.attempted_boundaries.get(index_name, {"PDH": False, "PDL": False})

        # 1. Bull Trap: PDH Sweep Reversal (Short / Buy PE)
        # Condition: Bar high pierced PDH by <= max_sweep, but bar closed back BELOW PDH
        if not bounds.get("PDH", False):
            if bar_high > pdh and (bar_high - pdh) <= max_sweep and bar_close < pdh:
                bounds["PDH"] = True
                sl_price = round(bar_high + sl_buffer, 2)
                sl_pts = round(sl_price - bar_close, 2)
                return LiquiditySweepSignal(
                    timestamp_ms=timestamp_ms,
                    index_name=index_name,
                    direction="PE",
                    sweep_type="PDH_SWEEP_REVERSAL",
                    boundary_price=pdh,
                    signal_bar_extreme=bar_high,
                    trigger_price=bar_close,
                    recommended_sl=sl_price,
                    target_pts=target_pts,
                    sl_pts=max(sl_pts, 4.0),
                    is_expiry_boost=is_expiry_session,
                    setup_reason=f"PDH Sweep ({bar_high:.1f} > {pdh:.1f}) Rejection Close {bar_close:.1f}",
                )

        # 2. Bear Trap: PDL Sweep Reversal (Long / Buy CE)
        # Condition: Bar low pierced PDL by <= max_sweep, but bar closed back ABOVE PDL
        if not bounds.get("PDL", False):
            if bar_low < pdl and (pdl - bar_low) <= max_sweep and bar_close > pdl:
                bounds["PDL"] = True
                sl_price = round(bar_low - sl_buffer, 2)
                sl_pts = round(bar_close - sl_price, 2)
                return LiquiditySweepSignal(
                    timestamp_ms=timestamp_ms,
                    index_name=index_name,
                    direction="CE",
                    sweep_type="PDL_SWEEP_REVERSAL",
                    boundary_price=pdl,
                    signal_bar_extreme=bar_low,
                    trigger_price=bar_close,
                    recommended_sl=sl_price,
                    target_pts=target_pts,
                    sl_pts=max(sl_pts, 4.0),
                    is_expiry_boost=is_expiry_session,
                    setup_reason=f"PDL Sweep ({bar_low:.1f} < {pdl:.1f}) Rejection Close {bar_close:.1f}",
                )

        return None
