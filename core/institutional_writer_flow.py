"""Institutional Option Writer Flow Engine.

Calculates and tracks real-time:
1. Near-The-Money (NTM) Put-Call Ratio (PCR) across ATM ± 3 strikes.
2. Strike-Level Call and Put Open Interest (OI) Walls (Support & Resistance).
3. Live Writer Unwinding vs Piling: Change in OI (Delta OI).
4. Writer Wall Collision & Divergence Veto Gate.

Preserves Trading Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import re


@dataclass(frozen=True)
class StrikeOIData:
    strike: int
    call_oi: float
    put_oi: float
    call_ltp: float
    put_ltp: float


@dataclass(frozen=True)
class WriterFlowState:
    ntm_pcr: float
    pcr_trend: str  # "BULLISH_RISING", "BEARISH_FALLING", "NEUTRAL"
    major_call_wall_strike: int
    major_put_wall_strike: int
    call_wall_oi: float
    put_wall_oi: float
    call_unwinding_detected: bool  # Call writers covering panic (Delta OI < 0)
    put_unwinding_detected: bool   # Put writers covering panic (Delta OI < 0)


class InstitutionalWriterFlowEngine:
    """Monitors live options order flow to detect institutional writer walls and traps."""

    def __init__(self, strike_step: int = 100, ntm_strikes_count: int = 3):
        self.strike_step = strike_step
        self.ntm_strikes_count = ntm_strikes_count
        self.history_oi: Dict[str, float] = {}  # symbol -> last observed OI
        self.pcr_history: List[float] = []

    def compute_ntm_flow(
        self,
        spot_price: float,
        live_option_book: Dict[str, Dict[str, float]],
        asset_prefix: str = "SENSEX"
    ) -> WriterFlowState:
        """Parses active live option book and extracts Near-The-Money writer dynamics.

        Args:
            spot_price: Current underlying spot close (e.g. 72,920.0).
            live_option_book: Map of symbol -> {"ltp": float, "oi": float, ...}
            asset_prefix: "SENSEX" or "NIFTY".
        """
        # Determine ATM Strike
        step = self.strike_step
        atm_strike = int(round(spot_price / float(step)) * step)

        ntm_strikes = [
            atm_strike + (offset * step)
            for offset in range(-self.ntm_strikes_count, self.ntm_strikes_count + 1)
        ]

        total_call_oi = 0.0
        total_put_oi = 0.0
        max_call_oi = 0.0
        max_call_strike = atm_strike + step
        max_put_oi = 0.0
        max_put_strike = atm_strike - step

        call_unwinding = False
        put_unwinding = False

        # Scan active book for matching strikes
        for sym, data in live_option_book.items():
            if asset_prefix not in sym:
                continue

            # Extract strike and direction (e.g. 'SENSEX 72700 CE 15 OCT 26')
            match = re.search(r"(\d{5,6})\s+(CE|PE)", sym)
            if not match:
                continue

            strike = int(match.group(1))
            opt_type = match.group(2)
            cur_oi = float(data.get("oi", 0.0) or 0.0)

            # Check unwinding (Delta OI drop)
            prev_oi = self.history_oi.get(sym, cur_oi)
            if prev_oi > 0 and cur_oi > 0:
                delta_oi = cur_oi - prev_oi
                if opt_type == "CE" and strike == atm_strike and delta_oi < -1000:
                    call_unwinding = True
                elif opt_type == "PE" and strike == atm_strike and delta_oi < -1000:
                    put_unwinding = True
            self.history_oi[sym] = cur_oi

            # Filter Near-The-Money strikes
            if strike in ntm_strikes:
                if opt_type == "CE":
                    total_call_oi += cur_oi
                    if cur_oi > max_call_oi:
                        max_call_oi = cur_oi
                        max_call_strike = strike
                else:  # PE
                    total_put_oi += cur_oi
                    if cur_oi > max_put_oi:
                        max_put_oi = cur_oi
                        max_put_strike = strike

        # Compute NTM PCR
        ntm_pcr = round(total_put_oi / max(1.0, total_call_oi), 3) if total_call_oi > 0 else 1.0
        self.pcr_history.append(ntm_pcr)
        if len(self.pcr_history) > 10:
            self.pcr_history.pop(0)

        # Determine PCR trend
        pcr_trend = "NEUTRAL"
        if len(self.pcr_history) >= 3:
            if self.pcr_history[-1] > self.pcr_history[0] + 0.05:
                pcr_trend = "BULLISH_RISING"
            elif self.pcr_history[-1] < self.pcr_history[0] - 0.05:
                pcr_trend = "BEARISH_FALLING"

        return WriterFlowState(
            ntm_pcr=ntm_pcr,
            pcr_trend=pcr_trend,
            major_call_wall_strike=max_call_strike,
            major_put_wall_strike=max_put_strike,
            call_wall_oi=max_call_oi,
            put_wall_oi=max_put_oi,
            call_unwinding_detected=call_unwinding,
            put_unwinding_detected=put_unwinding
        )

    def validate_writer_gate(
        self,
        entry_direction: str,
        spot_price: float,
        flow_state: WriterFlowState,
        min_runway_pts: float = 35.0
    ) -> Tuple[bool, str]:
        """Validates that a proposed entry does not run directly into an unyielding institutional writer wall.

        Returns:
            (passes_gate, reason)
        """
        if entry_direction == "CE":
            # 1. Bearish Divergence: Bullish breakout with low / falling PCR
            if flow_state.ntm_pcr < 0.70 and flow_state.pcr_trend == "BEARISH_FALLING":
                return False, f"VETO_BEARISH_PCR_DIVERGENCE (PCR {flow_state.ntm_pcr:.2f} falling into call writing)"

            # 2. Wall Collision: Buying right beneath a massive Call Wall without writer panic
            dist_to_call_wall = flow_state.major_call_wall_strike - spot_price
            if 0 < dist_to_call_wall < min_runway_pts and not flow_state.call_unwinding_detected:
                return False, f"VETO_CALL_WALL_COLLISION (Only {dist_to_call_wall:.1f}pts to Call Wall {flow_state.major_call_wall_strike} with zero unwinding)"

        elif entry_direction == "PE":
            # 1. Bullish Divergence: Bearish breakdown with high / rising PCR
            if flow_state.ntm_pcr > 1.30 and flow_state.pcr_trend == "BULLISH_RISING":
                return False, f"VETO_BULLISH_PCR_DIVERGENCE (PCR {flow_state.ntm_pcr:.2f} rising into put writing)"

            # 2. Wall Collision: Selling right above a massive Put Floor without writer panic
            dist_to_put_floor = spot_price - flow_state.major_put_wall_strike
            if 0 < dist_to_put_floor < min_runway_pts and not flow_state.put_unwinding_detected:
                return False, f"VETO_PUT_FLOOR_COLLISION (Only {dist_to_put_floor:.1f}pts to Put Floor {flow_state.major_put_wall_strike} with zero unwinding)"

        return True, "PASSED_WRITER_FLOW_VERIFIED"
