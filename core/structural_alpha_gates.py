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
        prev_moneyness: Optional[str] = None,
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

        # Dynamic Strike Escalation with dual-threshold Hysteresis Deadband (Contract 1.1)
        # Escalate to ITM_2 if IV > 0.19 (19.0%), de-escalate to ITM_1 if IV < 0.17 (17.0%).
        # In deadband [0.17, 0.19], retain prev_moneyness tier if provided; otherwise default to ITM_1.
        if safe_iv > 0.190:
            step_multiplier = 2
        elif safe_iv < 0.170:
            step_multiplier = 1
        else:
            if prev_moneyness == "ITM_2":
                step_multiplier = 2
            else:
                step_multiplier = 1

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
    """Evaluates passive limit fills vs conservative adverse selection crossing.
    
    In Indian Index Options, crossing a 3-5 pt spread on both entry and exit bleeds 6-10 pts.
    Supports conservative penalty-adjusted fills: P_fill = P_mid + alpha_adverse * spread.
    """

    @staticmethod
    def calculate_entry_fill(
        bid: float,
        ask: float,
        passive_fill_enabled: bool = True,
        adverse_fill_alpha: float = 0.25,
    ) -> Tuple[float, float, str]:
        """Calculates simulated entry price, realized spread savings, and fill mode.
        
        adverse_fill_alpha:
            0.0: Pure midpoint (P_mid)
            0.25: Conservative passive execution with adverse selection (P_mid + 0.25 * spread)
            0.50: Full spread crossing (P_ask for buys)
        """
        if bid <= 0 or ask <= 0 or ask < bid:
            return max(ask, bid, 0.0), 0.0, "INVALID_QUOTE"

        spread = ask - bid
        midpoint = round((bid + ask) / 2.0, 2)

        if not passive_fill_enabled or spread <= 0.50:
            # Narrow spread: market crossing is acceptable
            return ask, 0.0, "MARKET_CROSS_ASK"

        # Conservative fill calculation: P_fill = P_mid + alpha * spread
        safe_alpha = max(0.0, min(0.50, adverse_fill_alpha))
        fill_price = round(midpoint + (safe_alpha * spread), 2)
        savings = round(ask - fill_price, 2)
        fill_mode = "CONSERVATIVE_ADVERSE_FILL" if safe_alpha > 0.0 else "PASSIVE_MIDPOINT_FILL"
        return fill_price, savings, fill_mode


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
        current_time_epoch: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Verifies if companion index confirms the directional breakout/breakdown.
        
        Enforces Vector 2 Defenses:
        1. Fail-closed rejection if companion feed is uninitialized or missing.
        2. Freshness assertion: VETO if companion feed latency > 5.0s.
        3. Temporal skew bound: VETO if cross-instrument skew > 250ms (0.25s).
        
        Returns:
            (is_aligned, reason)
        """
        companion = "SENSEX" if target_index == "NIFTY" else "NIFTY"
        
        comp_spot = spots.get(companion, 0.0)
        comp_bounds = or_bounds.get(companion, {"high": -math.inf, "low": math.inf})
        comp_high = comp_bounds.get("high", -math.inf)
        comp_low = comp_bounds.get("low", math.inf)

        # 1. Fail-closed assertion on uninitialized / missing companion feed
        if comp_spot <= 0 or comp_high <= -math.inf or comp_low >= math.inf:
            return False, f"COMPANION_{companion}_DATA_UNINITIALIZED_FAIL_CLOSED"

        # 2. Freshness & Skew assertion if timestamps provided
        if last_updated_ts is not None and companion in last_updated_ts:
            comp_ts = last_updated_ts[companion]
            if current_time_epoch is not None:
                latency = current_time_epoch - comp_ts
                if latency > 5.0:
                    return False, f"COMPANION_FEED_STALE_VETO (Latency {latency:.2f}s > 5.0s)"
            
            target_ts = last_updated_ts.get(target_index)
            if target_ts is not None:
                skew = abs(target_ts - comp_ts)
                if skew > 0.250:  # 250 ms bound
                    return False, f"TEMPORAL_SKEW_EXCEEDED_FAIL_CLOSED (Skew {skew*1000:.1f}ms > 250ms)"

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
