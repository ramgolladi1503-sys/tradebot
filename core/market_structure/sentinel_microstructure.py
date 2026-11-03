"""
Sentinel Real-Time CVD Absorption & Dealer GEX Regime Engine.

Provides deterministic, scale-invariant, real-time microstructure supervisory gating:
1. Cumulative Volume Delta (CVD) tracking & passive absorption divergence detection.
2. Regularized Dealer Gamma Exposure (GEX) calculation & regime classification.
3. Top-of-book bid-ask spread crossing verification and crossed/locked book detection.
4. Composite fail-closed supervisory decision gating.

Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
runtime_wiring_modified = False
fail_closed_mode = True
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Sequence


# Safety Invariant Declarations
SAFETY_DECLARATIONS: dict[str, bool] = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "runtime_wiring_modified": False,
    "fail_closed_mode": True,
}


class CVDState(str, Enum):
    NORMAL = "NORMAL"
    BULLISH_ABSORPTION = "BULLISH_ABSORPTION"   # Price new high, CVD stagnant/negative -> Longs VETOED
    BEARISH_ABSORPTION = "BEARISH_ABSORPTION"   # Price new low, CVD stagnant/positive -> Shorts VETOED
    UNKNOWN = "UNKNOWN"


class GEXRegime(str, Enum):
    POSITIVE_GAMMA = "POSITIVE_GAMMA"   # High dealer long gamma, mean-reverting -> Breakouts VETOED
    NEGATIVE_GAMMA = "NEGATIVE_GAMMA"   # High dealer short gamma, volatility squeeze -> Breakouts ALLOWED
    NEUTRAL_GAMMA = "NEUTRAL_GAMMA"     # Unconstrained flow
    UNKNOWN = "UNKNOWN"


class MicrostructureVetoReason(str, Enum):
    NONE = "NONE"
    BULLISH_ABSORPTION_VETO = "BULLISH_ABSORPTION_VETO"
    BEARISH_ABSORPTION_VETO = "BEARISH_ABSORPTION_VETO"
    POSITIVE_GAMMA_FRICTION_VETO = "POSITIVE_GAMMA_FRICTION_VETO"
    SPREAD_CROSSING_VETO = "SPREAD_CROSSING_VETO"
    INVALID_FEED_CORRUPTION_VETO = "INVALID_FEED_CORRUPTION_VETO"


@dataclass(frozen=True)
class MarketBarSnapshot:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_volume: Optional[float] = None
    sell_volume: Optional[float] = None


@dataclass(frozen=True)
class OptionStrikeSnapshot:
    strike_price: float
    call_oi: float
    put_oi: float
    implied_volatility: float
    dte_years: float                   # Time to expiry in annualized years


@dataclass(frozen=True)
class TopOfBookQuote:
    timestamp: float
    bid_price: float
    ask_price: float
    bid_size: float = 1.0
    ask_size: float = 1.0


@dataclass(frozen=True)
class MicrostructureParameters:
    cvd_lookback_bars: int = 14
    cvd_absorption_threshold_z: float = 1.2
    positive_gex_threshold: float = 1_000_000.0   # Scale-normalized gamma exposure boundary
    negative_gex_threshold: float = -1_000_000.0
    max_spread_bps: float = 6.0                  # Basis points threshold for crossing veto
    min_time_to_expiry_years: float = 15.0 / (365.0 * 24.0 * 60.0) # ~15 min regularizer (~2.85e-5)
    min_implied_volatility: float = 0.05          # 5% IV floor
    max_gamma_cap: float = 100.0
    underlying_lot_size: int = 25


@dataclass(frozen=True)
class SentinelMicrostructureDecision:
    timestamp: float
    cvd_state: CVDState
    gex_regime: GEXRegime
    spread_bps: float
    is_absorption_vetoed: bool
    is_spread_vetoed: bool
    is_entry_permitted: bool
    veto_reasons: tuple[MicrostructureVetoReason, ...]
    cvd_divergence_metric: float
    net_dealer_gex: float
    audit_metadata: Dict[str, Any]
    safety_declarations: Dict[str, bool] = field(default_factory=lambda: dict(SAFETY_DECLARATIONS))


# ---------------------------------------------------------------------------
# Mathematical & Microstructure Helper Functions
# ---------------------------------------------------------------------------

def regularized_gamma(
    spot: float,
    strike: float,
    implied_volatility: float,
    dte_years: float,
    params: MicrostructureParameters,
) -> float:
    """
    Calculate regularized Black-Scholes gamma with asymptotic floor bounds and cap.

    Prevents ZeroDivisionError, NaN, Inf, and gamma explosion as tau -> 0.
    """
    if spot <= 0.0 or strike <= 0.0:
        return 0.0

    sigma = max(float(implied_volatility), float(params.min_implied_volatility))
    tau = max(float(dte_years), float(params.min_time_to_expiry_years))

    if math.isnan(sigma) or math.isinf(sigma) or math.isnan(tau) or math.isinf(tau):
        return 0.0

    sqrt_tau = math.sqrt(tau)
    denominator = spot * sigma * sqrt_tau
    if denominator <= 0.0 or math.isnan(denominator) or math.isinf(denominator):
        return 0.0

    # d1 = (ln(S / K) + 0.5 * sigma^2 * tau) / (sigma * sqrt(tau))
    try:
        log_term = math.log(spot / strike)
        numerator = log_term + 0.5 * (sigma ** 2) * tau
        d1 = numerator / (sigma * sqrt_tau)

        # Standard normal PDF phi(d1) = (1 / sqrt(2 * pi)) * exp(-0.5 * d1^2)
        # Handle large d1 gracefully to avoid underflow exceptions
        if abs(d1) > 20.0:
            phi_d1 = 0.0
        else:
            phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * (d1 ** 2))

        raw_gamma = phi_d1 / denominator
        if math.isnan(raw_gamma) or math.isinf(raw_gamma):
            return 0.0

        return min(max(raw_gamma, 0.0), float(params.max_gamma_cap))
    except (ValueError, OverflowError, ZeroDivisionError):
        return 0.0


def calculate_spread_bps(
    quote: TopOfBookQuote,
    params: MicrostructureParameters,
) -> tuple[float, bool, Optional[MicrostructureVetoReason]]:
    """
    Compute basis points spread:
    Spread_bps = ((ask - bid) / ((ask + bid) / 2)) * 10,000

    Returns:
        (spread_bps, is_spread_vetoed, veto_reason_or_none)
    """
    if (
        math.isnan(quote.bid_price)
        or math.isinf(quote.bid_price)
        or math.isnan(quote.ask_price)
        or math.isinf(quote.ask_price)
        or quote.bid_price <= 0.0
        or quote.ask_price <= 0.0
    ):
        return float("nan"), True, MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO

    # Crossed or locked book detection: ask <= bid
    if quote.ask_price <= quote.bid_price:
        return 0.0, True, MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO

    mid_price = (quote.bid_price + quote.ask_price) / 2.0
    if mid_price <= 0.0:
        return float("nan"), True, MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO

    spread_bps = ((quote.ask_price - quote.bid_price) / mid_price) * 10_000.0

    if math.isnan(spread_bps) or math.isinf(spread_bps):
        return float("nan"), True, MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO

    if spread_bps > params.max_spread_bps:
        return spread_bps, True, MicrostructureVetoReason.SPREAD_CROSSING_VETO

    return spread_bps, False, None


def calculate_cvd_state(
    bars: Sequence[MarketBarSnapshot],
    spot_price: float,
    params: MicrostructureParameters,
) -> tuple[CVDState, float, bool, Optional[MicrostructureVetoReason], dict[str, Any]]:
    """
    Evaluate Cumulative Volume Delta (CVD) and absorption divergence over the lookback window.

    Returns:
        (cvd_state, cvd_divergence_metric, is_absorption_vetoed, veto_reason, audit_dict)
    """
    window = params.cvd_lookback_bars
    if len(bars) < window or window <= 1:
        return (
            CVDState.UNKNOWN,
            0.0,
            True,
            MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
            {"error": "insufficient_bars", "bar_count": len(bars), "required": window},
        )

    # Use the last `window` bars
    eval_bars = bars[-window:]

    # Check timestamps strictly increasing and bar values valid
    delta_volumes: list[float] = []
    for i, bar in enumerate(eval_bars):
        if (
            math.isnan(bar.open)
            or math.isnan(bar.high)
            or math.isnan(bar.low)
            or math.isnan(bar.close)
            or math.isnan(bar.volume)
            or bar.volume < 0.0
            or bar.high < bar.low
            or bar.open <= 0.0
            or bar.close <= 0.0
        ):
            return (
                CVDState.UNKNOWN,
                0.0,
                True,
                MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
                {"error": "corrupted_bar_metrics", "index": i},
            )

        if i > 0 and bar.timestamp < eval_bars[i - 1].timestamp:
            return (
                CVDState.UNKNOWN,
                0.0,
                True,
                MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
                {"error": "out_of_order_timestamps", "index": i},
            )

        # Delta volume calculation
        if bar.buy_volume is not None and bar.sell_volume is not None:
            # Volume conservation validation: |V_buy + V_sell - V_total| <= 1e-4
            if (
                math.isnan(bar.buy_volume)
                or math.isnan(bar.sell_volume)
                or bar.buy_volume < 0.0
                or bar.sell_volume < 0.0
                or abs((bar.buy_volume + bar.sell_volume) - bar.volume) > 1e-4
            ):
                return (
                    CVDState.UNKNOWN,
                    0.0,
                    True,
                    MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
                    {"error": "volume_conservation_violation", "index": i},
                )
            delta_v = bar.buy_volume - bar.sell_volume
        else:
            # Aggregated Feed fallback via Tick/Quote rule proxy
            # sign(close - open) or tick rule
            if bar.close > bar.open:
                delta_v = bar.volume
            elif bar.close < bar.open:
                delta_v = -bar.volume
            else:
                # Close equals open: check close vs previous close if available
                if i > 0:
                    prev_close = eval_bars[i - 1].close
                    if bar.close > prev_close:
                        delta_v = bar.volume
                    elif bar.close < prev_close:
                        delta_v = -bar.volume
                    else:
                        delta_v = 0.0
                else:
                    delta_v = 0.0

        delta_volumes.append(delta_v)

    # Calculate cumulative volume delta over lookback window
    # delta_cvd_w = CVD_t - CVD_{t-W+1} = sum(delta_volumes)
    delta_cvd_w = sum(delta_volumes)

    # Prior window highs and lows (excluding the current bar)
    prior_highs = [b.high for b in eval_bars[:-1]]
    prior_lows = [b.low for b in eval_bars[:-1]]

    max_prior_high = max(prior_highs)
    min_prior_low = min(prior_lows)

    current_bar = eval_bars[-1]
    ref_price = spot_price if spot_price > 0.0 else current_bar.close

    # Divergence metric: normalized delta cvd relative to total volume
    total_window_vol = sum(b.volume for b in eval_bars)
    norm_cvd_metric = delta_cvd_w / total_window_vol if total_window_vol > 0.0 else 0.0

    audit = {
        "delta_cvd_w": delta_cvd_w,
        "norm_cvd_metric": norm_cvd_metric,
        "max_prior_high": max_prior_high,
        "min_prior_low": min_prior_low,
        "ref_price": ref_price,
        "total_window_vol": total_window_vol,
    }

    # Bullish Absorption (Distribution into aggressive buying / Passive Ask Absorption):
    # S_t >= max_{k in [1, W]} High_{t-k} AND delta_cvd_w <= 0
    if ref_price >= max_prior_high and delta_cvd_w <= 0.0:
        return (
            CVDState.BULLISH_ABSORPTION,
            norm_cvd_metric,
            True,
            MicrostructureVetoReason.BULLISH_ABSORPTION_VETO,
            audit,
        )

    # Bearish Absorption (Accumulation into aggressive selling / Passive Bid Absorption):
    # S_t <= min_{k in [1, W]} Low_{t-k} AND delta_cvd_w >= 0
    if ref_price <= min_prior_low and delta_cvd_w >= 0.0:
        return (
            CVDState.BEARISH_ABSORPTION,
            norm_cvd_metric,
            True,
            MicrostructureVetoReason.BEARISH_ABSORPTION_VETO,
            audit,
        )

    return CVDState.NORMAL, norm_cvd_metric, False, None, audit


def calculate_dealer_gex(
    strikes: Sequence[OptionStrikeSnapshot],
    spot_price: float,
    params: MicrostructureParameters,
) -> tuple[GEXRegime, float, Optional[MicrostructureVetoReason], dict[str, Any]]:
    """
    Calculate aggregate Net Dealer Gamma Exposure (GEX):
    Dealer GEX_i = Gamma_{reg, i} * S^2 * (OI_{call, i} - OI_{put, i}) * lot_size
    Total GEX = sum_i(Dealer GEX_i)

    Returns:
        (gex_regime, total_gex, veto_reason_or_none, audit_dict)
    """
    if spot_price <= 0.0 or math.isnan(spot_price) or math.isinf(spot_price):
        return (
            GEXRegime.UNKNOWN,
            0.0,
            MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
            {"error": "invalid_spot_price", "spot_price": spot_price},
        )

    if not strikes:
        return (
            GEXRegime.UNKNOWN,
            0.0,
            MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
            {"error": "empty_strikes_chain"},
        )

    total_gex = 0.0
    valid_strikes_count = 0
    spot_sq = spot_price * spot_price
    lot = params.underlying_lot_size

    for i, strike_item in enumerate(strikes):
        if (
            math.isnan(strike_item.strike_price)
            or math.isinf(strike_item.strike_price)
            or math.isnan(strike_item.call_oi)
            or math.isinf(strike_item.call_oi)
            or math.isnan(strike_item.put_oi)
            or math.isinf(strike_item.put_oi)
            or math.isnan(strike_item.implied_volatility)
            or math.isinf(strike_item.implied_volatility)
            or math.isnan(strike_item.dte_years)
            or math.isinf(strike_item.dte_years)
            or strike_item.strike_price <= 0.0
            or strike_item.call_oi < 0.0
            or strike_item.put_oi < 0.0
        ):
            return (
                GEXRegime.UNKNOWN,
                0.0,
                MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
                {"error": "corrupted_strike_data", "index": i},
            )

        gamma = regularized_gamma(
            spot=spot_price,
            strike=strike_item.strike_price,
            implied_volatility=strike_item.implied_volatility,
            dte_years=strike_item.dte_years,
            params=params,
        )

        net_oi = strike_item.call_oi - strike_item.put_oi
        strike_gex = gamma * spot_sq * net_oi * lot
        total_gex += strike_gex
        valid_strikes_count += 1

    if math.isnan(total_gex) or math.isinf(total_gex):
        return (
            GEXRegime.UNKNOWN,
            0.0,
            MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,
            {"error": "gex_overflow_or_nan"},
        )

    audit = {
        "valid_strikes_count": valid_strikes_count,
        "total_gex": total_gex,
        "lot_size": lot,
        "spot_price": spot_price,
    }

    if total_gex >= params.positive_gex_threshold:
        return GEXRegime.POSITIVE_GAMMA, total_gex, None, audit
    elif total_gex <= params.negative_gex_threshold:
        return GEXRegime.NEGATIVE_GAMMA, total_gex, None, audit
    else:
        return GEXRegime.NEUTRAL_GAMMA, total_gex, None, audit


# ---------------------------------------------------------------------------
# Composite Sentinel Microstructure Engine
# ---------------------------------------------------------------------------

class SentinelMicrostructureEngine:
    """
    Supervisory Microstructure Engine providing fail-closed regime evaluation
    and entry vetoes for TradeBot strategies.
    """

    def __init__(self, params: Optional[MicrostructureParameters] = None) -> None:
        self.params = params or MicrostructureParameters()

    def evaluate(
        self,
        bars: Sequence[MarketBarSnapshot],
        strikes: Sequence[OptionStrikeSnapshot],
        quote: TopOfBookQuote,
        spot_price: float,
    ) -> SentinelMicrostructureDecision:
        """
        Evaluate full microstructure state across CVD absorption, Dealer GEX, and Top-of-Book spread.
        """
        timestamp = quote.timestamp if quote else 0.0

        # Defensive initial checks
        if spot_price <= 0.0 or math.isnan(spot_price) or math.isinf(spot_price):
            return SentinelMicrostructureDecision(
                timestamp=timestamp,
                cvd_state=CVDState.UNKNOWN,
                gex_regime=GEXRegime.UNKNOWN,
                spread_bps=float("nan"),
                is_absorption_vetoed=True,
                is_spread_vetoed=True,
                is_entry_permitted=False,
                veto_reasons=(MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO,),
                cvd_divergence_metric=0.0,
                net_dealer_gex=0.0,
                audit_metadata={"error": "invalid_spot_price", "spot_price": spot_price},
            )

        veto_reasons: list[MicrostructureVetoReason] = []

        # 1. Top-of-Book Spread Evaluation
        spread_bps, is_spread_vetoed, spread_veto_reason = calculate_spread_bps(
            quote=quote,
            params=self.params,
        )
        if spread_veto_reason:
            veto_reasons.append(spread_veto_reason)

        # 2. Cumulative Volume Delta (CVD) Absorption Evaluation
        (
            cvd_state,
            norm_cvd_metric,
            is_absorption_vetoed,
            cvd_veto_reason,
            cvd_audit,
        ) = calculate_cvd_state(
            bars=bars,
            spot_price=spot_price,
            params=self.params,
        )
        if cvd_veto_reason:
            veto_reasons.append(cvd_veto_reason)

        # 3. Regularized Dealer GEX Evaluation
        (
            gex_regime,
            total_gex,
            gex_veto_reason,
            gex_audit,
        ) = calculate_dealer_gex(
            strikes=strikes,
            spot_price=spot_price,
            params=self.params,
        )
        if gex_veto_reason:
            veto_reasons.append(gex_veto_reason)

        # If any feed was corrupt or invalid, fail closed
        feed_corrupted = any(
            r == MicrostructureVetoReason.INVALID_FEED_CORRUPTION_VETO for r in veto_reasons
        )

        # Determine composite entry permission
        is_entry_permitted = (
            not feed_corrupted
            and not is_spread_vetoed
            and not is_absorption_vetoed
        )

        audit_metadata: dict[str, Any] = {
            "cvd_audit": cvd_audit,
            "gex_audit": gex_audit,
            "spread_bps": spread_bps,
            "params": {
                "max_spread_bps": self.params.max_spread_bps,
                "cvd_lookback_bars": self.params.cvd_lookback_bars,
                "positive_gex_threshold": self.params.positive_gex_threshold,
                "negative_gex_threshold": self.params.negative_gex_threshold,
                "lot_size": self.params.underlying_lot_size,
            },
        }

        # Deduplicate veto reasons while preserving order
        unique_reasons: list[MicrostructureVetoReason] = []
        for r in veto_reasons:
            if r not in unique_reasons:
                unique_reasons.append(r)

        return SentinelMicrostructureDecision(
            timestamp=timestamp,
            cvd_state=cvd_state,
            gex_regime=gex_regime,
            spread_bps=spread_bps,
            is_absorption_vetoed=is_absorption_vetoed,
            is_spread_vetoed=is_spread_vetoed,
            is_entry_permitted=is_entry_permitted,
            veto_reasons=tuple(unique_reasons) if unique_reasons else (MicrostructureVetoReason.NONE,),
            cvd_divergence_metric=norm_cvd_metric,
            net_dealer_gex=total_gex,
            audit_metadata=audit_metadata,
        )


def evaluate_microstructure(
    bars: Sequence[MarketBarSnapshot],
    strikes: Sequence[OptionStrikeSnapshot],
    quote: TopOfBookQuote,
    spot_price: float,
    params: Optional[MicrostructureParameters] = None,
) -> SentinelMicrostructureDecision:
    """
    Functional entrypoint for microstructure supervisory evaluation.
    """
    engine = SentinelMicrostructureEngine(params=params)
    return engine.evaluate(
        bars=bars,
        strikes=strikes,
        quote=quote,
        spot_price=spot_price,
    )
