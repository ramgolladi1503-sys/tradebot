"""
Option Mate (Damodhar Rao) RBFN Trend Decider & Slingshot Strike Strategy.

Reconstructed from masterclass transcripts and empirical backtests.
Implements non-linear Gaussian volatility surfaces for NIFTY/BANKNIFTY/SENSEX options.

Author: GSD & Hermes Architecture
Governance: TradeBot Agent OS (read_only=True, is_order_action=False)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass(frozen=True)
class GoldenCandle:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    range_pts: float = 0.0
    body_ratio: float = 0.0
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False

    @classmethod
    def create(cls, open: float, high: float, low: float, close: float, volume: float = 0.0) -> "GoldenCandle":
        rng = max(float(high - low), 1e-6)
        body = abs(float(close - open))
        range_pts = max(round(rng, 2), 0.01)
        return cls(
            open=round(float(open), 2),
            high=round(float(high), 2),
            low=round(float(low), 2),
            close=round(float(close), 2),
            volume=float(volume),
            range_pts=range_pts,
            body_ratio=round(body / rng, 4),
        )


@dataclass(frozen=True)
class OptionMateGrid:
    date: str
    spot_open: float
    trend_decider: float
    rp1_upper: float
    rp2_upper: float
    rp1_lower: float
    rp2_lower: float
    call_strike: float
    put_strike: float
    recommended_bias: str
    target_strike: float
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


@dataclass(frozen=True)
class OptionMateSignal:
    date: str
    action: str  # 'BUY_CALL', 'BUY_PUT', or 'ABSTAIN'
    target_strike: float
    spot_entry: float
    target_1_spot: float
    target_2_spot: float
    invalidation_spot: float
    entry_premium_est: float
    stop_loss_pts: float
    take_profit_pts: float
    narrative: str
    trade_phase: str = "MORNING_DRIVE"  # 'MORNING_DRIVE' or 'MIDDAY_REVERSAL'
    is_vetoed: bool = False
    veto_reason: Optional[str] = None
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


class OptionMateRBFNStrategy:
    """
    Directional options strategy computing non-linear volatility expansion barriers
    and executing the Slingshot OTM-to-ATM migration setup (Strategy Name: 'golden').
    """
    strategy_name: str = "golden"

    ASSET_CONFIGS = {
        "BANKNIFTY": {"base_step": 250.0, "strike_step": 100},
        "SENSEX": {"base_step": 400.0, "strike_step": 100},
        "NIFTY": {"base_step": 110.0, "strike_step": 50},
    }

    @classmethod
    def _resolve_asset_params(cls, symbol: Optional[str] = None, effective_spot: float = 0.0) -> tuple[str, float, int]:
        """
        Resolves (asset_name, base_step, strike_step) deterministically.
        Explicit symbol takes priority; falls back to price level threshold.
        """
        if symbol:
            sym_clean = symbol.upper().replace(" ", "")
            for asset, cfg in cls.ASSET_CONFIGS.items():
                if asset in sym_clean:
                    return asset, cfg["base_step"], cfg["strike_step"]
        if effective_spot > 60000:
            return "SENSEX", 400.0, 100
        elif effective_spot > 40000:
            return "BANKNIFTY", 250.0, 100
        else:
            return "NIFTY", 110.0, 50

    def __init__(
        self,
        symbol: Optional[str] = None,
        step_size: Optional[int] = None,
        reference_vix: float = 14.0,
        min_atr_frictional_hurdle: float = 150.0,
        min_vix_hurdle: float = 12.0,
        reversal_confirmation_bars: int = 2,
    ):
        self.symbol = symbol
        self.reference_vix = reference_vix
        self.min_atr_frictional_hurdle = min_atr_frictional_hurdle
        self.min_vix_hurdle = min_vix_hurdle
        self.reversal_confirmation_bars = reversal_confirmation_bars

        if step_size is not None:
            self.step_size = step_size
        elif symbol is not None:
            _, _, default_strike_step = self._resolve_asset_params(symbol=symbol)
            self.step_size = default_strike_step
        else:
            self.step_size = 50

    def compute_daily_grid(
        self,
        date: str,
        spot_open: float,
        prev_close: float,
        atr_14: float,
        vix: float,
        pro_client_divergence: float = 0.0,
        bar_5m_equilibrium: Optional[GoldenCandle] = None,
        symbol: Optional[str] = None,
    ) -> OptionMateGrid:
        """
        Calculates Trend Decider (TD) and Reversal Price (RP1, RP2) lines
        using scale-invariant, gap-aware Gaussian volatility dispersion.
        """
        if atr_14 <= 0:
            raise ValueError(f"ATR_14 must be strictly positive, got {atr_14}")

        # VIX guard: fallback to reference_vix (14.0) if None, NaN, or non-positive
        try:
            vix_val = float(vix)
            if np.isnan(vix_val) or vix_val <= 0:
                vix_val = self.reference_vix
        except (TypeError, ValueError):
            vix_val = self.reference_vix

        effective_spot = spot_open
        if bar_5m_equilibrium is not None:
            # If 09:20 5m bar completed, anchor around true closed 5m equilibrium price
            effective_spot = float(bar_5m_equilibrium.close)

        gap = effective_spot - prev_close
        gap_threshold = 0.25 * atr_14

        # 1. Asset-tiered dynamic base step & VIX modulation
        resolved_sym = symbol or self.symbol
        _, base_step, default_strike_step = self._resolve_asset_params(symbol=resolved_sym, effective_spot=effective_spot)
        strike_step = self.step_size if self.step_size is not None else default_strike_step

        vix_eff = min(max(vix_val, 9.0), 50.0)
        vol_scale = np.sqrt(vix_eff / self.reference_vix)
        channel_step = round(base_step * vol_scale, 2)

        # Enforce minimum floor if bar_5m_equilibrium is present
        if bar_5m_equilibrium is not None and bar_5m_equilibrium.range_pts > 0:
            channel_step = max(channel_step, round(0.35 * bar_5m_equilibrium.range_pts, 2))

        # 2. Trend Decider Price (Central Equilibrium)
        # Remove discrete anchor_round_base = 40.0/50.0/100.0 integer rounding
        if bar_5m_equilibrium is not None:
            o = float(bar_5m_equilibrium.open)
            h = float(bar_5m_equilibrium.high)
            l = float(bar_5m_equilibrium.low)
            c = float(bar_5m_equilibrium.close)
            range_pts = max(float(h - l), 1e-6)
            body = abs(float(c - o))
            wick = range_pts - body
            # Wick-Damped 5m Equilibrium when wide wick is present
            if wick > 1.5 * body:
                trend_decider = round(((o + c) / 2.0 + (h + l) / 2.0) / 2.0, 2)
            else:
                trend_decider = round((o + h + l + c) / 4.0, 2)
        else:
            flow_bias = np.sign(pro_client_divergence) * 0.05 * atr_14
            if abs(gap) >= gap_threshold:
                anchor_spot = spot_open if abs(spot_open - prev_close) >= gap_threshold else effective_spot
                raw_td = anchor_spot + flow_bias
                trend_decider = round(float(raw_td), 2)
            else:
                raw_td = 0.5 * (effective_spot + prev_close) + flow_bias
                trend_decider = round(float(raw_td), 2)

        # 3. Non-linear compression for RP2 and Century strike snapping
        rp1_up = round(trend_decider + channel_step, 2)
        rp1_down = round(trend_decider - channel_step, 2)
        rp2_up_raw = round(rp1_up + 0.85 * channel_step, 2)
        rp2_down_raw = round(rp1_down - 0.85 * channel_step, 2)

        century_up = round(rp2_up_raw / 100.0) * 100.0
        rp2_up = century_up if abs(rp2_up_raw - century_up) <= 10.0 else rp2_up_raw

        century_dn = round(rp2_down_raw / 100.0) * 100.0
        rp2_down = century_dn if abs(rp2_down_raw - century_dn) <= 10.0 else rp2_down_raw

        # 4. Dynamic Slingshot Strike Selection (Target strike that converts to ATM)
        call_strike = round(rp1_up / strike_step) * strike_step
        put_strike = round(rp1_down / strike_step) * strike_step

        if effective_spot > trend_decider:
            bias = "BULL"
        elif effective_spot < trend_decider:
            bias = "BEAR"
        else:
            # effective_spot == trend_decider: tie-break by opening gap
            if gap > 0:
                bias = "BULL"
            elif gap < 0:
                bias = "BEAR"
            else:
                bias = "NEUTRAL"

        target_strike = call_strike if bias == "BULL" else put_strike

        return OptionMateGrid(
            date=date,
            spot_open=round(float(spot_open), 2),
            trend_decider=round(float(trend_decider), 2),
            rp1_upper=round(float(rp1_up), 2),
            rp2_upper=round(float(rp2_up), 2),
            rp1_lower=round(float(rp1_down), 2),
            rp2_lower=round(float(rp2_down), 2),
            call_strike=float(call_strike),
            put_strike=float(put_strike),
            recommended_bias=bias,
            target_strike=float(target_strike),
        )

    def generate_signal(
        self,
        grid: OptionMateGrid,
        current_spot: float,
        current_atr: float,
        vix: float = 14.0,
        time_str: str = "09:30",
        golden_candle: Optional[GoldenCandle] = None,
    ) -> OptionMateSignal:
        """
        Generates causal entry signal at 09:30 AM based on spot position
        relative to the Trend Decider line and Golden Candle confirmation,
        guarded by Gate 2 ATR hurdle.
        """
        # VIX guard: fallback to reference_vix (14.0) if None, NaN, or non-positive
        try:
            vix_val = float(vix)
            if np.isnan(vix_val) or vix_val <= 0:
                vix_val = self.reference_vix
        except (TypeError, ValueError):
            vix_val = self.reference_vix

        # Production Gate 2: ATR & VIX Frictional Hurdle Check
        if current_atr < self.min_atr_frictional_hurdle or vix_val < self.min_vix_hurdle:
            return OptionMateSignal(
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
                trade_phase="MORNING_DRIVE",
                is_vetoed=True,
                veto_reason=(
                    f"GATE_2_VETO: Insufficient volatility expansion potential "
                    f"(ATR={current_atr:.1f} < {self.min_atr_frictional_hurdle:.1f} or "
                    f"VIX={vix_val:.1f} < {self.min_vix_hurdle:.1f}). Over-trading suppressed."
                ),
                narrative=(
                    f"[{time_str}] Session suppressed by Gate 2: Low-volatility regime "
                    f"(ATR={current_atr:.1f}, VIX={vix_val:.1f}) fails frictional hurdle."
                ),
            )

        # Golden Candle Validation (if provided)
        if golden_candle is not None:
            # Zero-volume or zero-range chop check (Attacker 2 guard)
            if golden_candle.volume == 0.0 or golden_candle.range_pts < 1.0:
                return OptionMateSignal(
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
                    trade_phase="MORNING_DRIVE",
                    is_vetoed=True,
                    veto_reason=(
                        f"GATE_2_ZERO_RANGE_CHOP: Candle range ({golden_candle.range_pts:.2f}) < 1.0 "
                        f"or volume ({golden_candle.volume:.0f}) == 0. Illiquid / synthetic artifact suppressed."
                    ),
                    narrative=f"[{time_str}] Suppressed by Gate 2: Zero volume or micro-range chop ({golden_candle.range_pts:.2f} pts).",
                )
            # Wick exhaustion check: If adverse wick > 60% of total range, reject blind chasing
            upper_wick = golden_candle.high - max(golden_candle.open, golden_candle.close)
            lower_wick = min(golden_candle.open, golden_candle.close) - golden_candle.low
            adverse_wick_ratio = max(upper_wick, lower_wick) / max(golden_candle.range_pts, 1e-6)

            if adverse_wick_ratio > 0.60 and golden_candle.body_ratio < 0.35:
                return OptionMateSignal(
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
                    trade_phase="MORNING_DRIVE",
                    is_vetoed=True,
                    veto_reason=f"GOLDEN_CANDLE_EXHAUSTION_VETO: Adverse wick ratio {adverse_wick_ratio:.2f} > 0.60 with weak body {golden_candle.body_ratio:.2f}.",
                    narrative=f"[{time_str}] Golden Candle shows exhaustion wick ({adverse_wick_ratio:.2f}). Breakout suppressed.",
                )

            # Golden Candle directional alignment check
            # For BULL: Spot must hold above TD and either Golden Candle closed bullish or spot pierced high
            if current_spot >= grid.trend_decider:
                if golden_candle.close < grid.trend_decider and current_spot < golden_candle.high:
                    return OptionMateSignal(
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
                        trade_phase="MORNING_DRIVE",
                        is_vetoed=True,
                        veto_reason="GOLDEN_CANDLE_CONFLICT_VETO: Spot above TD but Golden Candle closed below TD without high breakout.",
                        narrative=f"[{time_str}] Directional conflict: Spot above TD but Golden Candle not confirmed.",
                    )
            else:
                # For BEAR: Spot must trade below TD and either Golden Candle closed bearish or spot broke low
                if golden_candle.close >= grid.trend_decider and current_spot > golden_candle.low:
                    return OptionMateSignal(
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
                        trade_phase="MORNING_DRIVE",
                        is_vetoed=True,
                        veto_reason="GOLDEN_CANDLE_CONFLICT_VETO: Spot below TD but Golden Candle closed above TD without low breakdown.",
                        narrative=f"[{time_str}] Directional conflict: Spot below TD but Golden Candle not confirmed.",
                    )

        entry_prem_est = 0.16 * current_atr
        stop_loss_pts = 0.35 * entry_prem_est
        take_profit_pts = 0.95 * entry_prem_est

        if current_spot >= grid.trend_decider:
            # Bullish Direction: Buy Call matching RP1_UP
            return OptionMateSignal(
                date=grid.date,
                action="BUY_CALL",
                target_strike=grid.call_strike,
                spot_entry=current_spot,
                target_1_spot=grid.rp1_upper,
                target_2_spot=grid.rp2_upper,
                invalidation_spot=grid.trend_decider - 15.0,
                entry_premium_est=round(entry_prem_est, 2),
                stop_loss_pts=round(stop_loss_pts, 2),
                take_profit_pts=round(take_profit_pts, 2),
                trade_phase="MORNING_DRIVE",
                is_vetoed=False,
                veto_reason=None,
                narrative=(
                    f"[{time_str}] Spot ({current_spot:.2f}) holding above Trend Decider "
                    f"({grid.trend_decider:.2f}). Bullish Slingshot target strike "
                    f"{grid.call_strike:.0f} CE targeting RP1 ({grid.rp1_upper:.2f})."
                ),
            )
        else:
            # Bearish Direction: Buy Put matching RP1_DOWN
            return OptionMateSignal(
                date=grid.date,
                action="BUY_PUT",
                target_strike=grid.put_strike,
                spot_entry=current_spot,
                target_1_spot=grid.rp1_lower,
                target_2_spot=grid.rp2_lower,
                invalidation_spot=grid.trend_decider + 15.0,
                entry_premium_est=round(entry_prem_est, 2),
                stop_loss_pts=round(stop_loss_pts, 2),
                take_profit_pts=round(take_profit_pts, 2),
                trade_phase="MORNING_DRIVE",
                is_vetoed=False,
                veto_reason=None,
                narrative=(
                    f"[{time_str}] Spot ({current_spot:.2f}) trading below Trend Decider "
                    f"({grid.trend_decider:.2f}). Bearish Slingshot target strike "
                    f"{grid.put_strike:.0f} PE targeting RP1 ({grid.rp1_lower:.2f})."
                ),
            )

    def evaluate_midday_reversal(
        self,
        grid: OptionMateGrid,
        current_spot: float,
        recent_candle_closes: list[float],
        recent_candle_highs: list[float],
        recent_candle_lows: list[float],
        current_atr: float,
        vix: float = 14.0,
        time_str: str = "11:30",
    ) -> Optional[OptionMateSignal]:
        """
        Gate 3 Production Filter: Evaluates Midday Reversal (Trade 2) between 10:45 and 13:30.
        Requires multi-bar confirmation of rejection at RP1/RP2 to prevent fading trend days.
        """
        # Gate 2 Check: Suppress midday reversals if daily ATR is below hurdle
        # VIX guard: fallback to reference_vix (14.0) if None, NaN, or non-positive
        try:
            vix_val = float(vix)
            if np.isnan(vix_val) or vix_val <= 0:
                vix_val = self.reference_vix
        except (TypeError, ValueError):
            vix_val = self.reference_vix

        if current_atr < self.min_atr_frictional_hurdle or vix_val < self.min_vix_hurdle:
            return None

        if len(recent_candle_closes) < self.reversal_confirmation_bars:
            return None

        _, _, default_strike_step = self._resolve_asset_params(symbol=self.symbol, effective_spot=grid.trend_decider)
        strike_step = self.step_size if self.step_size is not None else default_strike_step

        entry_prem_est = 0.16 * current_atr
        stop_loss_pts = 0.35 * entry_prem_est
        take_profit_pts = 0.95 * entry_prem_est

        # Case 1: Bearish Reversal off RP1 Upper -> Buy PE back to Trend Decider
        # Confirmation condition: At least one recent bar tested >= RP1 Upper,
        # and last 2 consecutive candle closes are strictly BELOW RP1 Upper - 5.0 pts
        tested_rp1_upper = any(h >= grid.rp1_upper for h in recent_candle_highs[-3:])
        closed_below_rp1_upper = all(c <= (grid.rp1_upper - 5.0) for c in recent_candle_closes[-self.reversal_confirmation_bars:])
        
        if tested_rp1_upper and closed_below_rp1_upper and current_spot > grid.trend_decider:
            put_strike = round(grid.trend_decider / strike_step) * strike_step
            return OptionMateSignal(
                date=grid.date,
                action="BUY_PUT",
                target_strike=float(put_strike),
                spot_entry=current_spot,
                target_1_spot=grid.trend_decider,
                target_2_spot=grid.rp1_lower,
                invalidation_spot=grid.rp1_upper + 20.0,
                entry_premium_est=round(entry_prem_est, 2),
                stop_loss_pts=round(stop_loss_pts, 2),
                take_profit_pts=round(take_profit_pts, 2),
                trade_phase="MIDDAY_REVERSAL",
                is_vetoed=False,
                veto_reason=None,
                narrative=(
                    f"[{time_str}] Gate 3 Reversal Confirmed: Spot tested RP1 Upper "
                    f"({grid.rp1_upper:.2f}) and confirmed {self.reversal_confirmation_bars}-bar "
                    f"rejection close. Buying {put_strike:.0f} PE targeting Trend Decider ({grid.trend_decider:.2f})."
                ),
            )

        # Case 2: Bullish Reversal off RP1 Lower -> Buy CE back to Trend Decider
        # Confirmation condition: At least one recent bar tested <= RP1 Lower,
        # and last 2 consecutive candle closes are strictly ABOVE RP1 Lower + 5.0 pts
        tested_rp1_lower = any(l <= grid.rp1_lower for l in recent_candle_lows[-3:])
        closed_above_rp1_lower = all(c >= (grid.rp1_lower + 5.0) for c in recent_candle_closes[-self.reversal_confirmation_bars:])

        if tested_rp1_lower and closed_above_rp1_lower and current_spot < grid.trend_decider:
            call_strike = round(grid.trend_decider / strike_step) * strike_step
            return OptionMateSignal(
                date=grid.date,
                action="BUY_CALL",
                target_strike=float(call_strike),
                spot_entry=current_spot,
                target_1_spot=grid.trend_decider,
                target_2_spot=grid.rp1_upper,
                invalidation_spot=grid.rp1_lower - 20.0,
                entry_premium_est=round(entry_prem_est, 2),
                stop_loss_pts=round(stop_loss_pts, 2),
                take_profit_pts=round(take_profit_pts, 2),
                trade_phase="MIDDAY_REVERSAL",
                is_vetoed=False,
                veto_reason=None,
                narrative=(
                    f"[{time_str}] Gate 3 Reversal Confirmed: Spot tested RP1 Lower "
                    f"({grid.rp1_lower:.2f}) and confirmed {self.reversal_confirmation_bars}-bar "
                    f"rejection close. Buying {call_strike:.0f} CE targeting Trend Decider ({grid.trend_decider:.2f})."
                ),
            )

        return None
