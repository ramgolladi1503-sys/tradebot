"""
Sentinel Scale-Invariant Structural Market Gates.

Provides pure, scale-invariant, deterministic supervisory market structure gating
for TradeBot strategies without raw point-level curve-fitting:
1. Opening Shock Compression Ratio (Omega_15 = OR_15 / ATR_20(T-1))
2. Prior-Day Boundary Auction State (Acceptance vs. Failed Auction Trap)
3. Normalized Gamma Strike Wall Proximity (d_norm with Wall Vulnerability Ratio WVR)

Strict Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
runtime_wiring_modified = False
fail_closed_mode = True
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StructuralGatingAction(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT_BREAKOUT_ONLY = "RESTRICT_BREAKOUT_ONLY"
    RESTRICT_MEAN_REVERSION_ONLY = "RESTRICT_MEAN_REVERSION_ONLY"
    BLOCK_ALL_ENTRIES = "BLOCK_ALL_ENTRIES"


class OpeningShockRegime(str, Enum):
    COMPRESSED_COIL = "COMPRESSED_COIL"
    NORMAL_EQUILIBRIUM = "NORMAL_EQUILIBRIUM"
    EXHAUSTION_SHOCK = "EXHAUSTION_SHOCK"
    UNKNOWN = "UNKNOWN"


class AuctionBoundaryState(str, Enum):
    IN_VALUE_AUCTION = "IN_VALUE_AUCTION"
    TESTING_BOUNDARY = "TESTING_BOUNDARY"
    AUCTION_ACCEPTANCE = "AUCTION_ACCEPTANCE"
    FAILED_AUCTION_TRAP = "FAILED_AUCTION_TRAP"
    UNKNOWN = "UNKNOWN"


class GammaWallState(str, Enum):
    UNCONSTRAINED_FLOW = "UNCONSTRAINED_FLOW"
    APPROACHING_WALL = "APPROACHING_WALL"
    PIN_RISK_BARRIER = "PIN_RISK_BARRIER"
    WALL_BREAKTHROUGH_VULNERABLE = "WALL_BREAKTHROUGH_VULNERABLE"
    UNKNOWN = "UNKNOWN"


class WallType(str, Enum):
    CALL_WALL = "CALL_WALL"
    PUT_WALL = "PUT_WALL"


# ---------------------------------------------------------------------------
# Input Snapshots (Frozen Dataclasses)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpeningShockInput:
    opening_range_high: float
    opening_range_low: float
    daily_atr_20: float
    historical_bars_available: int = 20


@dataclass(frozen=True)
class AuctionBoundaryInput:
    spot_price: float
    prior_day_high: float
    prior_day_low: float
    daily_atr_20: float
    excursion_bar_volume: float
    excursion_bar_delta_volume: float
    consecutive_outside_closes: int
    returned_inside_within_n_bars: bool


@dataclass(frozen=True)
class GammaWallInput:
    spot_price: float
    wall_strike: float
    wall_type: WallType
    implied_volatility: float
    dte_days: float
    wall_total_oi: float
    wall_unwind_oi: float = 0.0
    wall_decay_oi: float = 0.0


# ---------------------------------------------------------------------------
# Decision Outputs (Frozen Dataclasses with Safety Invariants)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpeningShockDecision:
    regime: OpeningShockRegime
    omega_15: float
    action: StructuralGatingAction
    is_valid: bool
    diagnostic: str
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


@dataclass(frozen=True)
class AuctionBoundaryDecision:
    state: AuctionBoundaryState
    normalized_penetration: float
    rejection_ratio: float
    action: StructuralGatingAction
    is_valid: bool
    diagnostic: str
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


@dataclass(frozen=True)
class GammaWallDecision:
    state: GammaWallState
    normalized_distance: float
    wall_vulnerability_ratio: float
    action: StructuralGatingAction
    is_valid: bool
    diagnostic: str
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


@dataclass(frozen=True)
class SentinelCompositeStructuralDecision:
    action: StructuralGatingAction
    opening_shock: OpeningShockDecision
    auction_boundary: AuctionBoundaryDecision
    gamma_wall: GammaWallDecision
    active_constraints: tuple[str, ...]
    is_valid: bool
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


# ---------------------------------------------------------------------------
# Evaluator Class: SentinelStructuralGates
# ---------------------------------------------------------------------------

class SentinelStructuralGates:
    """
    Pure stateless evaluator implementing scale-invariant structural market gates.
    """

    @staticmethod
    def evaluate_opening_shock(input_data: OpeningShockInput) -> OpeningShockDecision:
        """
        Evaluates Opening Shock Compression Ratio: Omega_15 = OR_15 / ATR_20(T-1).
        Scale Invariant: (k * OR_15) / (k * ATR_20) == Omega_15.
        """
        # Fail-closed validation
        if (
            input_data.historical_bars_available < 20
            or input_data.daily_atr_20 <= 1e-6
            or input_data.opening_range_high < input_data.opening_range_low
        ):
            return OpeningShockDecision(
                regime=OpeningShockRegime.UNKNOWN,
                omega_15=0.0,
                action=StructuralGatingAction.BLOCK_ALL_ENTRIES,
                is_valid=False,
                diagnostic="Invalid or insufficient historical ATR/range inputs (fail-closed)",
            )

        opening_range = input_data.opening_range_high - input_data.opening_range_low
        omega_15 = opening_range / input_data.daily_atr_20

        # Dimensionless scale-free thresholds
        if omega_15 < 0.25:
            regime = OpeningShockRegime.COMPRESSED_COIL
            action = StructuralGatingAction.RESTRICT_MEAN_REVERSION_ONLY
            diag = "Compressed coil regime; energy compression authorizes breakout expansion"
        elif omega_15 <= 0.55:
            regime = OpeningShockRegime.NORMAL_EQUILIBRIUM
            action = StructuralGatingAction.ALLOW
            diag = "Normal equilibrium regime; standard auction discovery authorized"
        else:
            regime = OpeningShockRegime.EXHAUSTION_SHOCK
            action = StructuralGatingAction.RESTRICT_BREAKOUT_ONLY
            diag = "Exhaustion shock regime; high range exhaustion restricts breakout chasing"

        return OpeningShockDecision(
            regime=regime,
            omega_15=omega_15,
            action=action,
            is_valid=True,
            diagnostic=diag,
        )

    @staticmethod
    def evaluate_auction_boundary(input_data: AuctionBoundaryInput) -> AuctionBoundaryDecision:
        """
        Evaluates Prior-Day Boundary Auction State (Acceptance vs Failed Auction Trap).
        Scale Invariant: Delta_boundary / ATR_20 is dimensionless.
        """
        # Fail-closed validation
        if (
            input_data.prior_day_high <= input_data.prior_day_low
            or input_data.daily_atr_20 <= 1e-6
            or input_data.spot_price <= 0.0
            or input_data.excursion_bar_volume < 0.0
        ):
            return AuctionBoundaryDecision(
                state=AuctionBoundaryState.UNKNOWN,
                normalized_penetration=0.0,
                rejection_ratio=0.0,
                action=StructuralGatingAction.BLOCK_ALL_ENTRIES,
                is_valid=False,
                diagnostic="Invalid boundary, spot, or volume inputs (fail-closed)",
            )

        spot = input_data.spot_price
        pdh = input_data.prior_day_high
        pdl = input_data.prior_day_low
        atr = input_data.daily_atr_20

        # Calculate volume delta rejection ratio
        if input_data.excursion_bar_volume > 0.0:
            raw_delta_ratio = input_data.excursion_bar_delta_volume / input_data.excursion_bar_volume
        else:
            raw_delta_ratio = 0.0

        # Case 1: Within Value Area
        if pdl <= spot <= pdh:
            return AuctionBoundaryDecision(
                state=AuctionBoundaryState.IN_VALUE_AUCTION,
                normalized_penetration=0.0,
                rejection_ratio=0.0,
                action=StructuralGatingAction.ALLOW,
                is_valid=True,
                diagnostic="Price rotating within prior-day value area",
            )

        # Case 2: Above Prior Day High
        if spot > pdh:
            penetration = (spot - pdh) / atr
            rejection_ratio = raw_delta_ratio  # Positive delta supports breakout; negative indicates divergence

            if input_data.returned_inside_within_n_bars or (
                rejection_ratio < 0.0 and input_data.consecutive_outside_closes < 2
            ):
                return AuctionBoundaryDecision(
                    state=AuctionBoundaryState.FAILED_AUCTION_TRAP,
                    normalized_penetration=penetration,
                    rejection_ratio=rejection_ratio,
                    action=StructuralGatingAction.RESTRICT_BREAKOUT_ONLY,
                    is_valid=True,
                    diagnostic="Failed auction trap above PDH with negative delta absorption; breakout vetoed",
                )
            elif input_data.consecutive_outside_closes >= 2 and rejection_ratio >= 0.20:
                return AuctionBoundaryDecision(
                    state=AuctionBoundaryState.AUCTION_ACCEPTANCE,
                    normalized_penetration=penetration,
                    rejection_ratio=rejection_ratio,
                    action=StructuralGatingAction.ALLOW,
                    is_valid=True,
                    diagnostic="Auction acceptance above PDH confirmed by sustained closes and positive delta",
                )
            else:
                return AuctionBoundaryDecision(
                    state=AuctionBoundaryState.TESTING_BOUNDARY,
                    normalized_penetration=penetration,
                    rejection_ratio=rejection_ratio,
                    action=StructuralGatingAction.RESTRICT_BREAKOUT_ONLY,
                    is_valid=True,
                    diagnostic="Testing boundary above PDH pending acceptance confirmation",
                )

        # Case 3: Below Prior Day Low
        penetration = (pdl - spot) / atr
        rejection_ratio = -raw_delta_ratio  # Negative delta volume supports breakdown; positive delta indicates rejection

        if input_data.returned_inside_within_n_bars or (
            rejection_ratio < 0.0 and input_data.consecutive_outside_closes < 2
        ):
            return AuctionBoundaryDecision(
                state=AuctionBoundaryState.FAILED_AUCTION_TRAP,
                normalized_penetration=penetration,
                rejection_ratio=rejection_ratio,
                action=StructuralGatingAction.RESTRICT_BREAKOUT_ONLY,
                is_valid=True,
                diagnostic="Failed auction trap below PDL with positive delta absorption; breakdown vetoed",
            )
        elif input_data.consecutive_outside_closes >= 2 and rejection_ratio >= 0.20:
            return AuctionBoundaryDecision(
                state=AuctionBoundaryState.AUCTION_ACCEPTANCE,
                normalized_penetration=penetration,
                rejection_ratio=rejection_ratio,
                action=StructuralGatingAction.ALLOW,
                is_valid=True,
                diagnostic="Auction acceptance below PDL confirmed by sustained closes and aggressive selling",
            )
        else:
            return AuctionBoundaryDecision(
                state=AuctionBoundaryState.TESTING_BOUNDARY,
                normalized_penetration=penetration,
                rejection_ratio=rejection_ratio,
                action=StructuralGatingAction.RESTRICT_BREAKOUT_ONLY,
                is_valid=True,
                diagnostic="Testing boundary below PDL pending acceptance confirmation",
            )

    @staticmethod
    def evaluate_gamma_wall(input_data: GammaWallInput) -> GammaWallDecision:
        """
        Evaluates Normalized Gamma Strike Wall Proximity and Wall Vulnerability Ratio.
        d_norm = |spot - wall_strike| / (spot * iv * sqrt(tau))
        WVR = (unwind_oi + decay_oi) / total_oi
        """
        # Fail-closed validation
        if (
            input_data.spot_price <= 0.0
            or input_data.wall_strike <= 0.0
            or input_data.implied_volatility <= 1e-6
            or input_data.wall_total_oi <= 0.0
        ):
            return GammaWallDecision(
                state=GammaWallState.UNKNOWN,
                normalized_distance=0.0,
                wall_vulnerability_ratio=0.0,
                action=StructuralGatingAction.BLOCK_ALL_ENTRIES,
                is_valid=False,
                diagnostic="Invalid spot, strike, IV, or zero OI inputs (fail-closed)",
            )

        # Floor DTE to avoid zero division on intraday expiry
        tau_days = max(input_data.dte_days, 0.5)
        tau = tau_days / 365.0

        diffusion_scale = input_data.spot_price * input_data.implied_volatility * math.sqrt(tau)
        if diffusion_scale <= 1e-6:
            return GammaWallDecision(
                state=GammaWallState.UNKNOWN,
                normalized_distance=0.0,
                wall_vulnerability_ratio=0.0,
                action=StructuralGatingAction.BLOCK_ALL_ENTRIES,
                is_valid=False,
                diagnostic="Diffusion scale collapsed to zero (fail-closed)",
            )

        d_norm = abs(input_data.spot_price - input_data.wall_strike) / diffusion_scale

        unwind_total = max(input_data.wall_unwind_oi + input_data.wall_decay_oi, 0.0)
        wvr = min(max(unwind_total / input_data.wall_total_oi, 0.0), 1.0)

        # Dimensionless regime classification
        if d_norm >= 0.70:
            state = GammaWallState.UNCONSTRAINED_FLOW
            action = StructuralGatingAction.ALLOW
            diag = "Spot comfortably distant from dominant gamma wall; unconstrained flow"
        elif d_norm < 0.35 and wvr < 0.25:
            state = GammaWallState.PIN_RISK_BARRIER
            action = StructuralGatingAction.RESTRICT_BREAKOUT_ONLY
            diag = "Spot in immediate vicinity of fortified gamma wall; pin risk barrier restricts breakout"
        elif d_norm < 0.35 and wvr >= 0.50:
            state = GammaWallState.WALL_BREAKTHROUGH_VULNERABLE
            action = StructuralGatingAction.ALLOW
            diag = "Gamma wall exhibits heavy unwinding; breakthrough/squeeze vulnerable"
        else:
            state = GammaWallState.APPROACHING_WALL
            action = StructuralGatingAction.ALLOW
            diag = "Spot approaching gamma wall within normal absorption tolerance"

        return GammaWallDecision(
            state=state,
            normalized_distance=d_norm,
            wall_vulnerability_ratio=wvr,
            action=action,
            is_valid=True,
            diagnostic=diag,
        )

    @classmethod
    def evaluate_composite(
        cls,
        shock_decision: OpeningShockDecision,
        auction_decision: AuctionBoundaryDecision,
        gamma_decision: GammaWallDecision,
    ) -> SentinelCompositeStructuralDecision:
        """
        Combines individual structural decisions into a composite supervisory verdict.
        Any invalid input or hard block forces BLOCK_ALL_ENTRIES.
        """
        is_valid = shock_decision.is_valid and auction_decision.is_valid and gamma_decision.is_valid
        constraints: list[str] = []

        if not is_valid:
            return SentinelCompositeStructuralDecision(
                action=StructuralGatingAction.BLOCK_ALL_ENTRIES,
                opening_shock=shock_decision,
                auction_boundary=auction_decision,
                gamma_wall=gamma_decision,
                active_constraints=("INVALID_INPUTS_BLOCK_ALL",),
                is_valid=False,
            )

        # Check for hard block
        if (
            shock_decision.action == StructuralGatingAction.BLOCK_ALL_ENTRIES
            or auction_decision.action == StructuralGatingAction.BLOCK_ALL_ENTRIES
            or gamma_decision.action == StructuralGatingAction.BLOCK_ALL_ENTRIES
        ):
            return SentinelCompositeStructuralDecision(
                action=StructuralGatingAction.BLOCK_ALL_ENTRIES,
                opening_shock=shock_decision,
                auction_boundary=auction_decision,
                gamma_wall=gamma_decision,
                active_constraints=("CRITICAL_GATE_BLOCK_ALL",),
                is_valid=True,
            )

        # Collect specific restrictions
        if shock_decision.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY:
            constraints.append("SHOCK_EXHAUSTION_BLOCKS_BREAKOUT")
        elif shock_decision.action == StructuralGatingAction.RESTRICT_MEAN_REVERSION_ONLY:
            constraints.append("SHOCK_COMPRESSION_BLOCKS_MEAN_REVERSION")

        if auction_decision.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY:
            constraints.append("FAILED_AUCTION_TRAP_BLOCKS_BREAKOUT")

        if gamma_decision.action == StructuralGatingAction.RESTRICT_BREAKOUT_ONLY:
            constraints.append("GAMMA_PIN_BARRIER_BLOCKS_BREAKOUT")

        # Composite action determination
        if constraints:
            if "SHOCK_EXHAUSTION_BLOCKS_BREAKOUT" in constraints or "FAILED_AUCTION_TRAP_BLOCKS_BREAKOUT" in constraints or "GAMMA_PIN_BARRIER_BLOCKS_BREAKOUT" in constraints:
                composite_action = StructuralGatingAction.RESTRICT_BREAKOUT_ONLY
            else:
                composite_action = StructuralGatingAction.RESTRICT_MEAN_REVERSION_ONLY
        else:
            composite_action = StructuralGatingAction.ALLOW

        return SentinelCompositeStructuralDecision(
            action=composite_action,
            opening_shock=shock_decision,
            auction_boundary=auction_decision,
            gamma_wall=gamma_decision,
            active_constraints=tuple(constraints),
            is_valid=True,
        )
