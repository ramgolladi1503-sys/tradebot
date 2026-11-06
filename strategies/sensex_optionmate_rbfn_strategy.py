"""
Sensex Option Mate RBFN Trend Decider & Slingshot Strategy Engine
================================================================
Decodes and implements Option Mate's (Damodhar Rao) BSE SENSEX trading model:
1. Dynamic RBFN Trend Decider (TD) & Gaussian Volatility Expansion Lines (RP1, RP2).
2. Scale-calibrated to Sensex 100-point strike step size and ~3.28x NIFTY beta.
3. Day-to-Expiry (DTE) adaptive sustainable price anchors:
   - DTE >= 2 (Wednesday / Mid-week): Sustainable Anchor = 220.0 pts.
   - DTE == 1 (Eve of Expiry): Sustainable Anchor = 128.0 pts.
   - DTE == 0 (Expiry Day): Low-Premium Slingshot Ladder = 28.0 / 38.0 / 88.0 pts.
4. Production Gates 2 & 3:
   - Gate 2: Frictional Hurdle (ATR_14 >= 450.0, VIX >= 12.0).
   - Gate 3: Confirmed Reversal (2 consecutive 5m candle closes inside boundary).
5. Strict Safety Invariants:
   - read_only = True
   - is_order_action = False
   - broker_api_called = False
   - allowed_for_live_execution = False
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime, time


@dataclass(frozen=True)
class SensexOptionMateGrid:
    date: str
    spot_open: float
    prev_close: float
    atr_14: float
    vix: float
    trend_decider: float
    rp1_upper: float
    rp2_upper: float
    rp1_lower: float
    rp2_lower: float
    target_call_strike: float
    target_put_strike: float
    sustainable_price_anchor: float
    dte: int


@dataclass(frozen=True)
class SensexOptionMateSignal:
    date: str
    action: str  # "BUY_CALL", "BUY_PUT", "ABSTAIN"
    target_strike: float
    spot_entry: float
    target_1_spot: float
    target_2_spot: float
    invalidation_spot: float
    entry_premium_est: float
    stop_loss_pts: float
    take_profit_pts: float
    narrative: str
    trade_phase: str  # "MORNING_DRIVE", "MIDDAY_REVERSAL"
    is_vetoed: bool
    veto_reason: str
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


class SensexOptionMateRBFNStrategy:
    """
    Autonomous Sensex Option Mate RBFN Engine.
    Scales Nifty mathematical geometry by the empirical BSE Sensex volatility factor.
    """

    def __init__(
        self,
        step_size: int = 100,
        min_atr_frictional_hurdle: float = 450.0,
        min_vix_hurdle: float = 12.0,
        reversal_confirmation_bars: int = 2,
    ):
        self.step_size = step_size
        self.min_atr_frictional_hurdle = min_atr_frictional_hurdle
        self.min_vix_hurdle = min_vix_hurdle
        self.reversal_confirmation_bars = reversal_confirmation_bars

    def compute_daily_grid(
        self,
        date: str,
        spot_open: float,
        prev_close: float,
        atr_14: float,
        vix: float,
        dte: int = 2,
        pro_client_divergence: float = 0.0,
    ) -> SensexOptionMateGrid:
        """
        Computes the official 5-line RBFN grid for Sensex with Gap-Aware Auction Decoupling.
        
        Gap-Aware Principles:
        - When an opening gap (|open - prev_close| >= 0.25 * ATR) occurs, the auction
          decouples from prior close and anchors TD to opening round-number equilibrium.
        - Harmonic channel spacing enforces 300-pt steps for Sensex (~0.75 * ATR).
        - Dynamic Sustainable Price Anchor scales with DTE and VIX under the Black-Scholes ATM half-straddle formula.
        """
        if atr_14 <= 0:
            raise ValueError(f"ATR_14 must be strictly positive, got {atr_14}")

        gap = spot_open - prev_close
        gap_threshold = 0.25 * atr_14
        step_round_base = 50.0
        anchor_round_base = 100.0
        channel_step = round((spot_open * 0.0050) / step_round_base) * step_round_base

        # Institutional flow offset
        flow_offset = 0.05 * atr_14 * math.copysign(1.0, pro_client_divergence) if abs(pro_client_divergence) > 0.0 else 0.0

        # 1. Dynamic Trend Decider (TD)
        if abs(gap) >= gap_threshold:
            # Gap Regime: Market accepts new value; anchor directly around opening settlement (e.g. 76853 -> 76900)
            raw_td = spot_open + flow_offset
            trend_decider = round(raw_td / anchor_round_base) * anchor_round_base
        else:
            # Rotation Regime: Equilibrium between open and prior close
            raw_td = 0.5 * (spot_open + prev_close) + flow_offset
            trend_decider = round(raw_td / anchor_round_base) * anchor_round_base

        # 2. Harmonic Volatility Bands (300-pt step for RP1, 600-pt step for RP2)
        vix_scale = math.sqrt(max(vix, 9.0) / 14.0)
        rp1_upper = trend_decider + (channel_step * vix_scale)
        rp1_lower = trend_decider - (channel_step * vix_scale)
        rp2_upper = trend_decider + (2.0 * channel_step * vix_scale)
        rp2_lower = trend_decider - (2.0 * channel_step * vix_scale)

        # 3. Slingshot Target Strike Resolution (Target strike at RP2 Upper/Lower that converts to ATM)
        target_call_strike = round(rp2_upper / self.step_size) * self.step_size
        target_put_strike = round(rp2_lower / self.step_size) * self.step_size

        # 4. Dynamic Sustainable Price Anchor (ATM Half-Straddle Floor)
        # S = 77000, sigma = VIX/100, T = DTE/365
        effective_dte = max(0.20, float(dte))
        straddle_fair_value = spot_open * 0.80 * (max(vix, 9.0) / 100.0) * math.sqrt(effective_dte / 365.0)
        sustainable_anchor = round(straddle_fair_value / 2.0, 1)

        return SensexOptionMateGrid(
            date=date,
            spot_open=spot_open,
            prev_close=prev_close,
            atr_14=atr_14,
            vix=vix,
            trend_decider=trend_decider,
            rp1_upper=rp1_upper,
            rp2_upper=rp2_upper,
            rp1_lower=rp1_lower,
            rp2_lower=rp2_lower,
            target_call_strike=target_call_strike,
            target_put_strike=target_put_strike,
            sustainable_price_anchor=sustainable_anchor,
            dte=dte,
        )

    def generate_signal(
        self,
        grid: SensexOptionMateGrid,
        current_spot: float,
        current_atr: float,
        vix: float = 14.0,
        time_str: str = "09:45",
        or_range: Optional[float] = None,
        consecutive_closes_outside_rp1: int = 2,
    ) -> SensexOptionMateSignal:
        """
        Evaluates Morning Drive (09:45 - 11:30) Slingshot signal targeting the Sustainable Anchor.
        Enforces Strict Gate 2:
        - Frictional Hurdle (ATR >= 450, VIX >= 12.0)
        - Opening Range Quality (OR >= 0.35 * ATR)
        - Confirmed 2-bar close outside RP1 before entry
        """
        # Strict Gate 2: ATR & VIX Frictional Hurdle
        if current_atr < self.min_atr_frictional_hurdle or vix < self.min_vix_hurdle:
            return SensexOptionMateSignal(
                date=grid.date,
                action="ABSTAIN",
                target_strike=0.0,
                spot_entry=current_spot,
                target_1_spot=0.0,
                target_2_spot=0.0,
                invalidation_spot=0.0,
                entry_premium_est=0.0,
                stop_loss_pts=0.0,
                take_profit_pts=0.0,
                narrative=f"GATE_2_VETO: Sensex ATR ({current_atr:.1f} < {self.min_atr_frictional_hurdle}) or VIX ({vix:.1f} < {self.min_vix_hurdle}) below frictional hurdle",
                trade_phase="MORNING_DRIVE",
                is_vetoed=True,
                veto_reason="GATE_2_FRICTIONAL_HURDLE",
            )

        # Strict Gate 2: Opening Range Quality Check
        if or_range is not None and or_range < (0.35 * current_atr):
            return SensexOptionMateSignal(
                date=grid.date,
                action="ABSTAIN",
                target_strike=0.0,
                spot_entry=current_spot,
                target_1_spot=0.0,
                target_2_spot=0.0,
                invalidation_spot=0.0,
                entry_premium_est=0.0,
                stop_loss_pts=0.0,
                take_profit_pts=0.0,
                narrative=f"GATE_2_VETO: Opening range compression ({or_range:.1f} < {0.35 * current_atr:.1f}). Stand-aside on chop.",
                trade_phase="MORNING_DRIVE",
                is_vetoed=True,
                veto_reason="GATE_2_COMPRESSION_CHOP",
            )

        # Two-Bar Close Confirmation Check
        if consecutive_closes_outside_rp1 < self.reversal_confirmation_bars:
            return SensexOptionMateSignal(
                date=grid.date,
                action="ABSTAIN",
                target_strike=0.0,
                spot_entry=current_spot,
                target_1_spot=0.0,
                target_2_spot=0.0,
                invalidation_spot=0.0,
                entry_premium_est=0.0,
                stop_loss_pts=0.0,
                take_profit_pts=0.0,
                narrative="GATE_2_VETO: Waiting for 2 consecutive candle closes beyond RP1.",
                trade_phase="MORNING_DRIVE",
                is_vetoed=True,
                veto_reason="GATE_2_UNCONFIRMED_BREAKOUT",
            )

        # Bullish Slingshot: Price accepts above RP1 Upper, targeting Sustainable Price at RP2 Upper
        if current_spot >= grid.rp1_upper:
            action = "BUY_CALL"
            target_strike = grid.target_call_strike
            target_1 = grid.rp2_upper  # Target is the sustainable expansion boundary
            target_2 = grid.rp2_upper + 300.0
            invalidation = grid.rp1_upper - 50.0  # Strict tight invalidation
            narrative = (
                f"SENSEX SLINGSHOT BULLISH: Spot {current_spot:.1f} accepted above RP1 {grid.rp1_upper:.1f}. "
                f"Target strike: {target_strike:.0f} CE (Sustainable Anchor: Rs {grid.sustainable_price_anchor:.0f}). Target RP2: {target_1:.1f}"
            )
        # Bearish Slingshot: Price accepts below RP1 Lower, targeting Sustainable Price at RP2 Lower
        elif current_spot <= grid.rp1_lower:
            action = "BUY_PUT"
            target_strike = grid.target_put_strike
            target_1 = grid.rp2_lower
            target_2 = grid.rp2_lower - 300.0
            invalidation = grid.rp1_lower + 50.0
            narrative = (
                f"SENSEX SLINGSHOT BEARISH: Spot {current_spot:.1f} accepted below RP1 {grid.rp1_lower:.1f}. "
                f"Target strike: {target_strike:.0f} PE (Sustainable Anchor: Rs {grid.sustainable_price_anchor:.0f}). Target RP2: {target_1:.1f}"
            )
        else:
            return SensexOptionMateSignal(
                date=grid.date,
                action="ABSTAIN",
                target_strike=0.0,
                spot_entry=current_spot,
                target_1_spot=0.0,
                target_2_spot=0.0,
                invalidation_spot=0.0,
                entry_premium_est=0.0,
                stop_loss_pts=0.0,
                take_profit_pts=0.0,
                narrative="SENSEX IN CORRIDOR: Spot between RP1 Upper and RP1 Lower. Stand-aside.",
                trade_phase="MORNING_DRIVE",
                is_vetoed=False,
                veto_reason="",
            )

        stop_loss_pts = abs(current_spot - invalidation)
        take_profit_pts = abs(target_1 - current_spot)

        return SensexOptionMateSignal(
            date=grid.date,
            action=action,
            target_strike=target_strike,
            spot_entry=current_spot,
            target_1_spot=target_1,
            target_2_spot=target_2,
            invalidation_spot=invalidation,
            entry_premium_est=grid.sustainable_price_anchor,
            stop_loss_pts=stop_loss_pts,
            take_profit_pts=take_profit_pts,
            narrative=narrative,
            trade_phase="MORNING_DRIVE",
            is_vetoed=False,
            veto_reason="",
        )

    def evaluate_midday_reversal(
        self,
        grid: SensexOptionMateGrid,
        current_spot: float,
        recent_candle_closes: List[float],
        recent_candle_highs: List[float],
        recent_candle_lows: List[float],
        current_atr: float,
        vix: float = 14.0,
        time_str: str = "11:30",
    ) -> Optional[SensexOptionMateSignal]:
        """
        Evaluates Midday Reversal (Gate 3) for Sensex.
        Requires 2 consecutive 5m candle closes strictly inside RP1 boundary.
        """
        if current_atr < self.min_atr_frictional_hurdle or vix < self.min_vix_hurdle:
            return None

        if len(recent_candle_closes) < self.reversal_confirmation_bars:
            return None

        # Tolerance buffer for Sensex: 15.0 points
        reversal_buffer = 15.0

        # Scenario A: Upper Reversal (Spot tested RP1 Upper, now rejected back down -> BUY PE)
        tested_rp1_upper = any(h >= grid.rp1_upper for h in recent_candle_highs)
        closes_inside_upper = all(
            c <= (grid.rp1_upper - reversal_buffer)
            for c in recent_candle_closes[-self.reversal_confirmation_bars :]
        )

        if tested_rp1_upper and closes_inside_upper:
            target_strike = round(grid.trend_decider / self.step_size) * self.step_size
            return SensexOptionMateSignal(
                date=grid.date,
                action="BUY_PUT",
                target_strike=target_strike,
                spot_entry=current_spot,
                target_1_spot=grid.trend_decider,
                target_2_spot=grid.rp1_lower,
                invalidation_spot=grid.rp1_upper + 30.0,
                entry_premium_est=grid.sustainable_price_anchor,
                stop_loss_pts=abs(grid.rp1_upper + 30.0 - current_spot),
                take_profit_pts=abs(current_spot - grid.trend_decider),
                narrative=f"GATE_3_CONFIRMED: SENSEX Upper RP1 ({grid.rp1_upper:.1f}) rejected with 2 confirmation closes. Reversion target TD {grid.trend_decider:.1f}",
                trade_phase="MIDDAY_REVERSAL",
                is_vetoed=False,
                veto_reason="",
            )

        # Scenario B: Lower Reversal (Spot tested RP1 Lower, now rejected back up -> BUY CE)
        tested_rp1_lower = any(l <= grid.rp1_lower for l in recent_candle_lows)
        closes_inside_lower = all(
            c >= (grid.rp1_lower + reversal_buffer)
            for c in recent_candle_closes[-self.reversal_confirmation_bars :]
        )

        if tested_rp1_lower and closes_inside_lower:
            target_strike = round(grid.trend_decider / self.step_size) * self.step_size
            return SensexOptionMateSignal(
                date=grid.date,
                action="BUY_CALL",
                target_strike=target_strike,
                spot_entry=current_spot,
                target_1_spot=grid.trend_decider,
                target_2_spot=grid.rp1_upper,
                invalidation_spot=grid.rp1_lower - 30.0,
                entry_premium_est=grid.sustainable_price_anchor,
                stop_loss_pts=abs(current_spot - (grid.rp1_lower - 30.0)),
                take_profit_pts=abs(grid.trend_decider - current_spot),
                narrative=f"GATE_3_CONFIRMED: SENSEX Lower RP1 ({grid.rp1_lower:.1f}) rejected with 2 confirmation closes. Reversion target TD {grid.trend_decider:.1f}",
                trade_phase="MIDDAY_REVERSAL",
                is_vetoed=False,
                veto_reason="",
            )

        return None
