"""Institutional 4-Vector Quantitative Engine.

Implements the 4 Institutional Alpha & Execution Vectors:
Vector 1: Dealer Gamma Exposure (GEX) & Wall Absorption Engine
Vector 2: Micro-Price Order Book Imbalance (Stoikov 2018) Engine
Vector 3: High-Beta Lead-Lag Cross-Index Transmission (NIFTY vs BANKNIFTY) Engine
Vector 4: Passive Queue Routing & Adverse Selection Avoidance (ASAA) Engine

Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np


@dataclass(frozen=True)
class Level2Depth:
    bid_prices: Tuple[float, ...]
    bid_sizes: Tuple[float, ...]
    ask_prices: Tuple[float, ...]
    ask_sizes: Tuple[float, ...]

    def __post_init__(self):
        if len(self.bid_prices) != len(self.bid_sizes):
            raise ValueError("bid_prices and bid_sizes length mismatch")
        if len(self.ask_prices) != len(self.ask_sizes):
            raise ValueError("ask_prices and ask_sizes length mismatch")


class GEXRegimeState(str, Enum):
    POSITIVE_GAMMA = "POSITIVE_GAMMA"   # High dealer long gamma -> Mean reversion expected, breakouts vetoed
    NEGATIVE_GAMMA = "NEGATIVE_GAMMA"   # Dealer short gamma -> Volatility expansion / momentum accelerator
    NEUTRAL_GAMMA = "NEUTRAL_GAMMA"     # Balanced gamma


class MicroPriceSignal(str, Enum):
    BULLISH_PRESSURE = "BULLISH_PRESSURE"
    BEARISH_PRESSURE = "BEARISH_PRESSURE"
    NEUTRAL = "NEUTRAL"


class LeadLagSignal(str, Enum):
    LEAD_EXPANSION = "LEAD_EXPANSION"
    LEAD_EXHAUSTION = "LEAD_EXHAUSTION"
    EQUILIBRIUM = "EQUILIBRIUM"


class PassiveRoutingMode(str, Enum):
    PASSIVE_LIMIT_MAKER = "PASSIVE_LIMIT_MAKER"  # Join inside bid/ask to capture half-spread
    ADAPTIVE_CROSSING = "ADAPTIVE_CROSSING"      # Micro-price confirms urgent momentum, cross allowed
    VETO_ADVERSE_QUEUE = "VETO_ADVERSE_QUEUE"    # Adverse selection risk -> order cancelled/delayed


# ---------------------------------------------------------------------------
# VECTOR 1: Dealer Gamma Exposure (GEX) & Wall Absorption Engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GEXVectorResult:
    net_gex: float
    regime: GEXRegimeState
    is_breakout_permitted: bool
    reversion_probability: float
    audit: Dict[str, Any]


class InstitutionalGEXEngine:
    """Calculates dealer gamma exposure across the full options surface and determines gamma regimes."""

    def __init__(
        self,
        lot_size: int = 25,
        pos_gex_threshold: float = 1_000_000.0,
        neg_gex_threshold: float = -1_000_000.0,
        min_iv: float = 0.05,
        min_dte_years: float = 15.0 / (365.0 * 24.0 * 60.0), # 15 min regularizer
    ):
        self.lot_size = lot_size
        self.pos_gex_threshold = pos_gex_threshold
        self.neg_gex_threshold = neg_gex_threshold
        self.min_iv = min_iv
        self.min_dte_years = min_dte_years

    def calculate_strike_gamma(
        self,
        spot: float,
        strike: float,
        iv: float,
        dte_years: float,
    ) -> float:
        if (
            math.isnan(spot)
            or math.isinf(spot)
            or math.isnan(strike)
            or math.isinf(strike)
            or math.isnan(iv)
            or math.isinf(iv)
            or math.isnan(dte_years)
            or math.isinf(dte_years)
            or spot <= 0
            or strike <= 0
        ):
            return 0.0
        sigma = max(iv, self.min_iv)
        tau = max(dte_years, self.min_dte_years)
        sqrt_tau = math.sqrt(tau)
        denom = spot * sigma * sqrt_tau
        if denom <= 0:
            return 0.0
        try:
            d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * tau) / (sigma * sqrt_tau)
            if abs(d1) > 20.0:
                return 0.0
            phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
            gamma = phi_d1 / denom
            return min(max(gamma, 0.0), 100.0)
        except (ValueError, OverflowError, ZeroDivisionError):
            return 0.0

    def compute_gex(
        self,
        spot: float,
        strikes: Sequence[Tuple[float, float, float, float, float]],  # (strike, call_oi, put_oi, iv, dte_years)
    ) -> GEXVectorResult:
        if spot <= 0 or not strikes:
            return GEXVectorResult(
                net_gex=0.0,
                regime=GEXRegimeState.NEUTRAL_GAMMA,
                is_breakout_permitted=True,
                reversion_probability=0.5,
                audit={"error": "invalid_inputs"},
            )

        total_gex = 0.0
        spot_sq = spot * spot

        for strike, c_oi, p_oi, iv, dte in strikes:
            gamma = self.calculate_strike_gamma(spot, strike, iv, dte)
            strike_gex = gamma * spot_sq * (c_oi - p_oi) * self.lot_size
            total_gex += strike_gex

        if total_gex >= self.pos_gex_threshold:
            regime = GEXRegimeState.POSITIVE_GAMMA
            # In positive gamma, dealer hedging dampens volatility -> breakouts fail, mean reversion high
            is_breakout_permitted = False
            reversion_prob = min(0.5 + (total_gex / (4 * self.pos_gex_threshold)), 0.95)
        elif total_gex <= self.neg_gex_threshold:
            regime = GEXRegimeState.NEGATIVE_GAMMA
            # In negative gamma, dealer hedging accelerates moves -> trend breakouts thrive
            is_breakout_permitted = True
            reversion_prob = max(0.5 - (abs(total_gex) / (4 * abs(self.neg_gex_threshold))), 0.05)
        else:
            regime = GEXRegimeState.NEUTRAL_GAMMA
            is_breakout_permitted = True
            reversion_prob = 0.50

        return GEXVectorResult(
            net_gex=total_gex,
            regime=regime,
            is_breakout_permitted=is_breakout_permitted,
            reversion_probability=reversion_prob,
            audit={"valid_strikes": len(strikes), "spot": spot},
        )


# ---------------------------------------------------------------------------
# VECTOR 2: Micro-Price Order Book Imbalance (Stoikov 2018) Engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MicroPriceResult:
    micro_price: float
    mid_price: float
    spread_pts: float
    imbalance_ratio: float      # I in [-1, +1], I = (Q_b - Q_a) / (Q_b + Q_a)
    expected_direction: MicroPriceSignal
    adverse_selection_drift_pts: float
    audit: Dict[str, Any]


class StoikovMicroPriceEngine:
    """Computes order book micro-price according to Stoikov (2018) formulation:
    
    P_micro = P_mid + ((Q_b - Q_a) / (Q_b + Q_a)) * (Spread / 2)
    Extended for multi-level queue weighting:
    Q_b = sum(w_k * Q_b,k), Q_a = sum(w_k * Q_a,k)
    """

    def __init__(self, depth_decay: float = 0.5, adverse_drift_threshold_bps: float = 0.20):
        self.depth_decay = depth_decay
        self.adverse_drift_threshold_bps = adverse_drift_threshold_bps

    def compute_micro_price(
        self,
        depth: Level2Depth,
    ) -> MicroPriceResult:
        if not depth.bid_prices or not depth.ask_prices:
            return MicroPriceResult(
                micro_price=0.0,
                mid_price=0.0,
                spread_pts=0.0,
                imbalance_ratio=0.0,
                expected_direction=MicroPriceSignal.NEUTRAL,
                adverse_selection_drift_pts=0.0,
                audit={"error": "empty_depth"},
            )

        best_bid = depth.bid_prices[0]
        best_ask = depth.ask_prices[0]

        if best_ask <= best_bid or best_bid <= 0:
            return MicroPriceResult(
                micro_price=best_bid,
                mid_price=best_bid,
                spread_pts=0.0,
                imbalance_ratio=0.0,
                expected_direction=MicroPriceSignal.NEUTRAL,
                adverse_selection_drift_pts=0.0,
                audit={"error": "locked_or_crossed_book"},
            )

        mid_price = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid

        # Multi-level weighted queue depth
        weighted_bid_size = 0.0
        weighted_ask_size = 0.0
        for i, (b_sz, a_sz) in enumerate(zip(depth.bid_sizes, depth.ask_sizes)):
            weight = math.exp(-self.depth_decay * i)
            weighted_bid_size += weight * b_sz
            weighted_ask_size += weight * a_sz

        total_size = weighted_bid_size + weighted_ask_size
        if total_size <= 0:
            imbalance = 0.0
        else:
            imbalance = (weighted_bid_size - weighted_ask_size) / total_size

        micro_price = mid_price + (imbalance * (spread / 2.0))
        adverse_selection_drift = micro_price - mid_price

        drift_bps = (adverse_selection_drift / mid_price) * 10_000.0 if mid_price > 0 else 0.0
        # Invariant threshold: drift > 0.05 bps or imbalance > 0.20 indicates direction
        imbalance_cutoff = 0.20
        if imbalance >= imbalance_cutoff:
            signal = MicroPriceSignal.BULLISH_PRESSURE
        elif imbalance <= -imbalance_cutoff:
            signal = MicroPriceSignal.BEARISH_PRESSURE
        else:
            signal = MicroPriceSignal.NEUTRAL

        return MicroPriceResult(
            micro_price=micro_price,
            mid_price=mid_price,
            spread_pts=spread,
            imbalance_ratio=imbalance,
            expected_direction=signal,
            adverse_selection_drift_pts=adverse_selection_drift,
            audit={
                "weighted_bid_size": weighted_bid_size,
                "weighted_ask_size": weighted_ask_size,
                "drift_bps": drift_bps,
            },
        )


# ---------------------------------------------------------------------------
# VECTOR 3: High-Beta Lead-Lag Cross-Index Transmission Engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LeadLagResult:
    lead_index: str
    lag_index: str
    z_spread: float
    cointegration_confirmed: bool
    signal: LeadLagSignal
    half_life_bars: float
    audit: Dict[str, Any]


class CrossIndexLeadLagEngine:
    """Measures dynamic transmission speed and lead-lag divergence between BANKNIFTY and NIFTY.
    
    BANKNIFTY acts as high-beta leader; NIFTY lags by tau ~ 1-5 bars.
    Transmission model:
    Spread_t = log(S_BANKNIFTY,t) - beta * log(S_NIFTY,t) - alpha
    Z_t = (Spread_t - mean(Spread)) / std(Spread)
    """

    def __init__(
        self,
        lookback_bars: int = 60,
        z_threshold: float = 2.0,
        mean_reversion_target_z: float = 0.5,
    ):
        self.lookback_bars = lookback_bars
        self.z_threshold = z_threshold
        self.mean_reversion_target_z = mean_reversion_target_z

    def compute_lead_lag(
        self,
        leader_series: Sequence[float],   # e.g. BANKNIFTY
        follower_series: Sequence[float], # e.g. NIFTY
        leader_name: str = "BANKNIFTY",
        follower_name: str = "NIFTY",
    ) -> LeadLagResult:
        n = min(len(leader_series), len(follower_series))
        if n < self.lookback_bars or self.lookback_bars < 10:
            return LeadLagResult(
                lead_index=leader_name,
                lag_index=follower_name,
                z_spread=0.0,
                cointegration_confirmed=False,
                signal=LeadLagSignal.EQUILIBRIUM,
                half_life_bars=0.0,
                audit={"error": "insufficient_lookback"},
            )

        lead = np.array(leader_series[-self.lookback_bars:], dtype=float)
        lag = np.array(follower_series[-self.lookback_bars:], dtype=float)

        if np.any(lead <= 0) or np.any(lag <= 0):
            return LeadLagResult(
                lead_index=leader_name,
                lag_index=follower_name,
                z_spread=0.0,
                cointegration_confirmed=False,
                signal=LeadLagSignal.EQUILIBRIUM,
                half_life_bars=0.0,
                audit={"error": "non_positive_prices"},
            )

        log_lead = np.log(lead)
        log_lag = np.log(lag)

        # OLS cointegration regression: log_lead = beta * log_lag + alpha + eps
        cov = np.cov(log_lag, log_lead)
        var_lag = cov[0, 0]
        if var_lag <= 1e-12:
            beta = 1.0
            alpha = np.mean(log_lead) - beta * np.mean(log_lag)
        else:
            beta = cov[0, 1] / var_lag
            alpha = np.mean(log_lead) - beta * np.mean(log_lag)

        residuals = log_lead - (beta * log_lag + alpha)
        res_mean = np.mean(residuals)
        res_std = np.std(residuals)

        current_res = residuals[-1]
        z_spread = (current_res - res_mean) / res_std if res_std > 1e-8 else 0.0

        # ADF unit root test proxy on residuals: Delta eps_t = gamma * eps_{t-1} + u_t
        # Cointegration requires rejecting unit root (gamma < 0, t-stat < critical value -2.86)
        eps_lag = residuals[:-1]
        eps_curr = residuals[1:]
        delta_eps = eps_curr - eps_lag
        
        cointegrated = False
        half_life = 999.0

        if len(eps_lag) > 10 and np.var(eps_lag) > 1e-12:
            gamma = float(np.cov(eps_lag, delta_eps)[0, 1] / np.var(eps_lag))
            res_u = delta_eps - gamma * eps_lag
            s_err = math.sqrt(np.var(res_u) / (len(eps_lag) * np.var(eps_lag))) if np.var(eps_lag) > 0 else 1.0
            t_stat = gamma / s_err if s_err > 0 else 0.0

            # Dickey-Fuller critical threshold at 5% is approx -2.86
            if t_stat < -2.86 and gamma < 0.0:
                cointegrated = True
                phi = 1.0 + gamma
                if 0.0 < phi < 1.0:
                    half_life = -math.log(2.0) / math.log(phi)
                else:
                    # In high-frequency 1m bars, strong mean reversion (gamma <= -1) reflects instantaneous 1-bar rebound
                    half_life = 1.0

        if z_spread >= self.z_threshold:
            # Leader has surged ahead, follower expected to catch up or leader revert
            signal = LeadLagSignal.LEAD_EXPANSION
        elif z_spread <= -self.z_threshold:
            # Leader has plunged relative to follower
            signal = LeadLagSignal.LEAD_EXHAUSTION
        else:
            signal = LeadLagSignal.EQUILIBRIUM

        return LeadLagResult(
            lead_index=leader_name,
            lag_index=follower_name,
            z_spread=float(z_spread),
            cointegration_confirmed=cointegrated,
            signal=signal,
            half_life_bars=float(half_life),
            audit={"beta": float(beta), "res_std": float(res_std)},
        )


@dataclass(frozen=True)
class DerivativeBasisResult:
    instrument_name: str
    basis_pts: float
    basis_z: float
    rolling_mean_basis: float
    rolling_std_basis: float
    signal: LeadLagSignal
    is_statistically_significant: bool
    audit: Dict[str, Any]


class DerivativeBasisLeadLagEngine:
    """Computes derivative basis mean-reversion dislocation between index futures and spot.

    Basis_t = Futures_t - Spot_t
    Z_t = (Basis_t - mean(Basis, lookback)) / std(Basis, lookback)

    When Z_t > z_threshold (futures premium extended), basis mean-reversion implies
    cash spot catching up or futures premium collapsing -> Bullish Spot / Reversion Signal.
    When Z_t < -z_threshold (futures discount extended), basis mean-reversion implies
    discount narrowing -> Bearish Spot / Reversion Signal.

    Safety:
    Fails closed on NaN, Inf, non-positive spot/futures, or insufficient lookback.
    """

    def __init__(
        self,
        lookback_bars: int = 60,
        z_threshold: float = 2.0,
        min_periods: int = 20,
    ):
        self.lookback_bars = lookback_bars
        self.z_threshold = z_threshold
        self.min_periods = min_periods

    def compute_basis_dislocation(
        self,
        futures_series: Sequence[float],
        spot_series: Sequence[float],
        instrument_name: str = "NIFTY",
    ) -> DerivativeBasisResult:
        n = min(len(futures_series), len(spot_series))
        if n < self.min_periods:
            return DerivativeBasisResult(
                instrument_name=instrument_name,
                basis_pts=0.0,
                basis_z=0.0,
                rolling_mean_basis=0.0,
                rolling_std_basis=0.0,
                signal=LeadLagSignal.EQUILIBRIUM,
                is_statistically_significant=False,
                audit={"error": "insufficient_lookback", "n": n},
            )

        fut = np.array(futures_series[-self.lookback_bars:], dtype=float)
        spt = np.array(spot_series[-self.lookback_bars:], dtype=float)

        if np.any(np.isnan(fut)) or np.any(np.isnan(spt)) or np.any(fut <= 0) or np.any(spt <= 0):
            return DerivativeBasisResult(
                instrument_name=instrument_name,
                basis_pts=0.0,
                basis_z=0.0,
                rolling_mean_basis=0.0,
                rolling_std_basis=0.0,
                signal=LeadLagSignal.EQUILIBRIUM,
                is_statistically_significant=False,
                audit={"error": "invalid_inputs_fail_closed"},
            )

        basis_series = fut - spt
        current_basis = float(basis_series[-1])
        mean_basis = float(np.mean(basis_series))
        std_basis = float(np.std(basis_series))

        if std_basis < 1e-6:
            basis_z = 0.0
        else:
            basis_z = (current_basis - mean_basis) / std_basis

        is_sig = abs(basis_z) >= self.z_threshold
        if basis_z >= self.z_threshold:
            signal = LeadLagSignal.LEAD_EXPANSION  # Extended futures premium
        elif basis_z <= -self.z_threshold:
            signal = LeadLagSignal.LEAD_EXHAUSTION  # Extended futures discount
        else:
            signal = LeadLagSignal.EQUILIBRIUM

        return DerivativeBasisResult(
            instrument_name=instrument_name,
            basis_pts=current_basis,
            basis_z=float(basis_z),
            rolling_mean_basis=mean_basis,
            rolling_std_basis=std_basis,
            signal=signal,
            is_statistically_significant=is_sig,
            audit={"lookback_used": len(basis_series)},
        )


# ---------------------------------------------------------------------------
# VECTOR 4: Passive Queue Routing & Adverse Selection Avoidance (ASAA) Engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PassiveRoutingResult:
    recommended_mode: PassiveRoutingMode
    execution_price: float
    expected_savings_pts: float
    adverse_selection_risk: float  # [0.0, 1.0]
    is_safe_to_post: bool
    audit: Dict[str, Any]


class PassiveQueueRoutingEngine:
    """Optimizes order placement to harvest the bid-ask spread while evading toxic adverse selection.
    
    If order book imbalance I is moving aggressively against the quote, resting passive limit orders
    suffer adverse selection mark-to-market decay.
    When I is favorable or neutral, resting at the inside bid/ask captures half the spread:
    Cost_savings = Spread / 2 - Queue_Priority_Risk
    """

    def __init__(
        self,
        adverse_selection_imbalance_cutoff: float = 0.60,
        min_spread_to_post_pts: float = 1.0,
    ):
        self.adverse_selection_imbalance_cutoff = adverse_selection_imbalance_cutoff
        self.min_spread_to_post_pts = min_spread_to_post_pts

    def evaluate_routing(
        self,
        direction: str,  # "BUY" or "SELL" / "CE" or "PE"
        depth: Level2Depth,
        micro_price_res: MicroPriceResult,
    ) -> PassiveRoutingResult:
        if not depth.bid_prices or not depth.ask_prices:
            return PassiveRoutingResult(
                recommended_mode=PassiveRoutingMode.VETO_ADVERSE_QUEUE,
                execution_price=0.0,
                expected_savings_pts=0.0,
                adverse_selection_risk=1.0,
                is_safe_to_post=False,
                audit={"error": "no_depth"},
            )

        best_bid = depth.bid_prices[0]
        best_ask = depth.ask_prices[0]
        spread = best_ask - best_bid
        imbalance = micro_price_res.imbalance_ratio

        is_buy = direction.upper() in ["BUY", "CE"]

        # Adverse selection assessment:
        if is_buy:
            if imbalance < -self.adverse_selection_imbalance_cutoff:
                # Heavy sell pressure dumping into our bid -> Toxic Adverse Selection
                adverse_risk = 0.90
                safe = False
                mode = PassiveRoutingMode.VETO_ADVERSE_QUEUE
                price = best_bid
                savings = 0.0
            elif imbalance > self.adverse_selection_imbalance_cutoff:
                # Breakout momentum surging up, aggressive crossing required
                adverse_risk = 0.40
                safe = True
                mode = PassiveRoutingMode.ADAPTIVE_CROSSING
                price = best_ask
                savings = -spread * 0.1 # Small crossing penalty
            else:
                # Balanced queue: post passive limit maker at best bid
                adverse_risk = 0.15
                safe = True
                mode = PassiveRoutingMode.PASSIVE_LIMIT_MAKER
                price = best_bid
                savings = spread / 2.0
        else:
            # Sell side logic
            if imbalance > self.adverse_selection_imbalance_cutoff:
                # Heavy buy pressure dumping into our ask
                adverse_risk = 0.90
                safe = False
                mode = PassiveRoutingMode.VETO_ADVERSE_QUEUE
                price = best_ask
                savings = 0.0
            elif imbalance < -self.adverse_selection_imbalance_cutoff:
                # Bearish breakdown surging down, aggressive crossing
                adverse_risk = 0.40
                safe = True
                mode = PassiveRoutingMode.ADAPTIVE_CROSSING
                price = best_bid
                savings = -spread * 0.1
            else:
                # Balanced queue: post passive limit maker at best ask
                adverse_risk = 0.15
                safe = True
                mode = PassiveRoutingMode.PASSIVE_LIMIT_MAKER
                price = best_ask
                savings = spread / 2.0

        return PassiveRoutingResult(
            recommended_mode=mode,
            execution_price=price,
            expected_savings_pts=savings,
            adverse_selection_risk=adverse_risk,
            is_safe_to_post=safe,
            audit={"imbalance": imbalance, "spread": spread},
        )
