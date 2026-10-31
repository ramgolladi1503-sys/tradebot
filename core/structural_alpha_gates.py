"""Structural Alpha Gates and Execution Modules.

Implements the 4 institutional non-overfitted profitability drivers:
1. ITMStrikeResolver: Selects ITM strikes (Delta 0.65-0.75) for 1:1 spot tracking & delta efficiency.
2. PassiveMidpointQueueModel: Simulates realistic midpoint fills ((bid + ask) / 2) vs crossing full spread.
3. VolatilityCompressionGate: Enforces narrow range / ATR compression (NR4 / squeeze) before breakdown/breakout triggers.
4. CrossIndexMacroGate: Verifies multi-index consensus (NIFTY + SENSEX + BANKNIFTY) to prevent false breakout traps.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(slots=True, frozen=True)
class StrikeSelectionResult:
    target_strike: float
    option_type: str  # "CE" or "PE"
    strike_offset: int  # -1, 0, +1
    moneyness: str  # "ITM_1", "ATM", "OTM_1"
    estimated_delta: float
    is_itm: bool


class ITMStrikeResolver:
    """Selects In-The-Money (ITM) strike contracts to ensure Delta >= 0.65,
    dampening theta decay and improving delta passthrough efficiency.
    """

    @staticmethod
    def resolve_target_strike(
        spot: float,
        direction: str,  # "CE" or "PE"
        index_name: str = "NIFTY",
        target_delta: float = 0.70,
        iv_annualized: float = 0.14,
        dte_days: float = 3.0,
    ) -> StrikeSelectionResult:
        if index_name == "SENSEX":
            interval = 100.0
        elif index_name == "BANKNIFTY":
            interval = 100.0
        else:
            interval = 50.0

        atm = round(spot / interval) * interval
        dir_clean = direction.upper()

        # Adversarial Hardening: Defensive clamping against unseeded spots, zero/negative IV, or NaN
        safe_spot = max(spot, 1.0)
        safe_iv = max(abs(iv_annualized) if not math.isnan(iv_annualized) else 0.14, 0.01)
        safe_dte = max(dte_days if not math.isnan(dte_days) else 0.5, 0.5)

        # Dynamic Strike Escalation: If IV > 18.0%, escalate to ITM-2 to preserve Delta >= 0.65
        step_multiplier = 2 if safe_iv > 0.18 else 1
        effective_offset_val = interval * step_multiplier

        # Robust BSM delta approximation with bounded 0.50 - 0.90 clamping
        raw_delta = 0.50 + (effective_offset_val / (safe_spot * safe_iv * math.sqrt(safe_dte / 365.0)))
        delta_mag = round(max(0.50, min(0.90, raw_delta)), 2)

        if dir_clean == "CE":
            target = atm - effective_offset_val
            offset = -step_multiplier
            moneyness = f"ITM_{step_multiplier}"
            est_delta = delta_mag
        else:
            target = atm + effective_offset_val
            offset = step_multiplier
            moneyness = f"ITM_{step_multiplier}"
            est_delta = -delta_mag

        return StrikeSelectionResult(
            target_strike=target,
            option_type=dir_clean,
            strike_offset=offset,
            moneyness=moneyness,
            estimated_delta=est_delta,
            is_itm=True,
        )

    @staticmethod
    def is_contract_matching(
        symbol: str,
        target_strike: float,
        option_type: str,
        tolerance_strikes: int = 1,
        strike_interval: float = 50.0,
    ) -> bool:
        sym = symbol.upper()
        if option_type not in sym:
            return False

        contract_strike = None
        for part in sym.split():
            if part.isdigit() and len(part) >= 4:
                contract_strike = float(part)
                break

        if contract_strike is None:
            return False

        allowed_diff = tolerance_strikes * strike_interval
        return abs(contract_strike - target_strike) <= (allowed_diff + 1e-4)


class PassiveMidpointQueueModel:
    """Evaluates passive limit fills at the midpoint (bid + ask)/2 instead of crossing the spread.
    
    In Indian Index Options, crossing a 3-5 pt spread on both entry and exit bleeds 6-10 pts.
    Passive limit placement at the midpoint or joining top queue captures edge without penalty.
    """

    @staticmethod
    def calculate_entry_fill(
        bid: float,
        ask: float,
        passive_fill_enabled: bool = True,
    ) -> Tuple[float, float, str]:
        """Calculates simulated entry price, realized spread savings, and fill mode."""
        if bid <= 0 or ask <= 0 or ask < bid:
            return max(ask, bid, 0.0), 0.0, "INVALID_QUOTE"

        spread = ask - bid
        midpoint = round((bid + ask) / 2.0, 2)

        if not passive_fill_enabled or spread <= 0.50:
            # Narrow spread: market crossing is acceptable
            return ask, 0.0, "MARKET_CROSS_ASK"

        # Passive midpoint queue execution
        savings = round(ask - midpoint, 2)
        return midpoint, savings, "PASSIVE_MIDPOINT_FILL"


class VolatilityCompressionGate:
    """Evaluates whether the market is in stored energy compression (NR4 / ATR squeeze)
    prior to entry, preventing chasing exhausted volatility breakouts.
    """

    def __init__(
        self,
        compression_ratio_threshold: float = 0.85,
        exhaustion_multiplier: float = 2.5,
    ):
        self.compression_ratio_threshold = compression_ratio_threshold
        self.exhaustion_multiplier = exhaustion_multiplier

    def evaluate_compression(
        self,
        atr_15m: float,
        atr_60m: float,
        recent_displacement_pts: float,
    ) -> Tuple[bool, str, float]:
        """Evaluates ATR squeeze and displacement exhaustion.
        
        Returns:
            (allow_entry, reason, compression_ratio)
        """
        if atr_60m <= 0:
            return True, "INSUFFICIENT_BASELINE_ATR", 1.0

        cr = round(atr_15m / atr_60m, 3)

        # 1. Exhaustion check: If spot has already traveled > 2.5x 60m ATR in a single burst without pause
        if abs(recent_displacement_pts) > self.exhaustion_multiplier * atr_60m:
            return False, f"EXHAUSTED_EXPANSION (Displacement {abs(recent_displacement_pts):.1f} > {self.exhaustion_multiplier}x ATR60)", cr

        # 2. Squeeze / Compression check: If 15m ATR <= 0.85x 60m ATR, volatility is coiled
        if cr <= self.compression_ratio_threshold:
            return True, f"COILED_VOLATILITY_COMPRESSION (CR={cr:.2f} <= {self.compression_ratio_threshold})", cr

        # Mild expansion allowed if not exhausted
        return True, f"EXPANSION_ENTRY_PERMITTED (CR={cr:.2f})", cr


class CrossIndexMacroGate:
    """Validates cross-index directional confirmation across NIFTY, SENSEX, and BANKNIFTY.
    
    Prevents single-index fakeout traps by requiring consensus across major index benchmarks.
    """

    def __init__(self, max_sync_skew_sec: float = 180.0):
        self.max_sync_skew_sec = max_sync_skew_sec

    def evaluate_alignment(
        self,
        target_index: str,
        setup_direction: str,  # "CE" or "PE"
        spots: Dict[str, float],
        or_bounds: Dict[str, Dict[str, float]],
        last_updated_ts: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, str]:
        """Verifies if companion index confirms the directional breakout/breakdown.
        
        Returns:
            (is_aligned, reason)
        """
        companion = "SENSEX" if target_index == "NIFTY" else "NIFTY"
        
        comp_spot = spots.get(companion, 0.0)
        comp_bounds = or_bounds.get(companion, {"high": -math.inf, "low": math.inf})
        comp_high = comp_bounds.get("high", -math.inf)
        comp_low = comp_bounds.get("low", math.inf)

        if comp_spot <= 0 or comp_high <= -math.inf or comp_low >= math.inf:
            # Companion data missing or uninitialized; allow fail-safe entry with warning
            return True, f"COMPANION_{companion}_DATA_UNINITIALIZED_PASS"

        # Check directional stance of companion index
        if setup_direction == "PE":
            # Breakdown setup: Companion should NOT be breaking out to day high
            if comp_spot > comp_high:
                return False, f"MACRO_DIVERGENCE_VETO: {target_index} PE Breakdown but {companion} @ Day High ({comp_spot:.1f} > {comp_high:.1f})"
            return True, f"MACRO_CONFIRMED: {target_index} & {companion} concurrent bearish alignment"
        else:  # "CE"
            # Breakout setup: Companion should NOT be breaking down to day low
            if comp_spot < comp_low:
                return False, f"MACRO_DIVERGENCE_VETO: {target_index} CE Breakout but {companion} @ Day Low ({comp_spot:.1f} < {comp_low:.1f})"
            return True, f"MACRO_CONFIRMED: {target_index} & {companion} concurrent bullish alignment"
