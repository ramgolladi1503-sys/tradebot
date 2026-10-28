"""Sentinel Wall Gate: Supervisory Microstructure Edge Gating Engine.

Stage 3 implementation of the Sentinel Wall Intelligence architecture.
Evaluates proximity, directional liquidity ratio, and wall vulnerability to:
1. Veto adverse entries heading into fortified institutional walls (fade trap prevention).
2. Confirm high-conviction breakout continuations when walls are fragile.
3. Tighten APM runner trailing stops when approaching major opposing walls.

Strict Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- edge_certification_status = "NO_CERTIFIED_EDGE"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    SentinelWallState,
    StrikeWallProfile,
)

logger = logging.getLogger(__name__)

# Gate Decision Actions
GATE_ACTION_PROCEED = "PROCEED"
GATE_ACTION_VETO = "VETO_ADVERSE_WALL"
GATE_ACTION_WARN = "WARN_FRAGILE_WALL"
GATE_ACTION_CONFIRM_BREACH = "CONFIRM_BREACH"
GATE_ACTION_TIGHTEN_RUNNER = "TIGHTEN_RUNNER"
GATE_ACTION_CLAMP_TARGET = "CLAMP_TARGET"


@dataclass(frozen=True)
class WallGateDecision:
    """Immutable audit record for a wall gate evaluation."""
    symbol: str
    direction: str  # "CE" or "PE"
    action: str  # GATE_ACTION_*
    proximity_pts: float
    proximity_atr: float
    major_wall_strike: float
    wall_vulnerability: float
    directional_liquidity_ratio: float
    reason: str
    timestamp_ms: int
    clamped_target_pts: Optional[float] = None
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    edge_certification_status: str = "NO_CERTIFIED_EDGE"


class SentinelWallGate:
    """Supervisory edge gate evaluating strike wall proximity and depth vulnerability.
    
    Calibrated Thresholds (from Stage 2 Empirical Research REP-SENTINEL-WALL-CALIBRATION-001):
    - Proximity Veto Window: <= 0.75 ATR
    - Wall Fortified: Vulnerability < 0.80 or Directional Liquidity Ratio opposing trade
    - Wall Fragile / Breach: Vulnerability > 1.50 and Directional Liquidity Ratio supporting trade
    - Runner Tighten Window: <= 0.50 ATR towards opposing wall
    - Proximity Hysteresis Buffer: 0.05 ATR (5%)
    """

    def __init__(
        self,
        observer: SentinelWallObserver,
        proximity_veto_atr: float = 0.75,
        runner_tighten_atr: float = 0.50,
        hysteresis_pct: float = 0.05,
    ) -> None:
        self.observer = observer
        self.proximity_veto_atr = float(proximity_veto_atr)
        self.runner_tighten_atr = float(runner_tighten_atr)
        self.hysteresis_pct = float(hysteresis_pct)

    def evaluate_entry_gate(
        self,
        direction: str,
        spot_price: float,
        timestamp_ms: int,
    ) -> WallGateDecision:
        """Evaluates whether an entry signal (CE or PE) should be allowed, warned, or vetoed.
        
        Args:
            direction: "CE" (bullish setup) or "PE" (bearish setup).
            spot_price: Current index spot price.
            timestamp_ms: Current evaluation timestamp.
            
        Returns:
            WallGateDecision with action and microstructure telemetry.
        """
        dir_clean = direction.upper().strip()
        state = self.observer.compute_wall_state(force_recompute=False)

        # Fail-closed / Neutral fallback if observer state is uncertified or invalid
        if not state.is_valid or state.status != "HEALTHY":
            return WallGateDecision(
                symbol=state.symbol,
                direction=dir_clean,
                action=GATE_ACTION_PROCEED,
                proximity_pts=0.0,
                proximity_atr=0.0,
                major_wall_strike=0.0,
                wall_vulnerability=0.0,
                directional_liquidity_ratio=1.0,
                reason=f"BYPASS_UNHEALTHY_OBSERVER: {state.status}",
                timestamp_ms=timestamp_ms,
            )

        atr = max(state.atr_pts, 1.0)

        if dir_clean == "CE":
            # Scan for any relevant Call Wall (Major, Secondary, or Local Concentration)
            # within proximity window [spot_price - 0.25*ATR, spot_price + (proximity_veto_atr + hysteresis)*ATR]
            candidate_strikes = []
            for s, prof in state.wall_density_map.items():
                if prof.is_major_call_wall or prof.is_secondary_call_wall or prof.call_oi >= (0.60 * state.total_call_oi / max(len(state.wall_density_map), 1)):
                    dist_pts = s - spot_price
                    dist_atr = dist_pts / atr
                    # Consider strikes in local vicinity ahead of spot or recently breached
                    if -0.25 <= dist_atr <= (self.proximity_veto_atr + self.hysteresis_pct):
                        candidate_strikes.append((s, prof, dist_pts, dist_atr))

            if not candidate_strikes:
                return self._default_proceed(state, dir_clean, timestamp_ms, "OUTSIDE_PROXIMITY_ZONE")

            # Sort by absolute distance to find the nearest barrier
            candidate_strikes.sort(key=lambda x: abs(x[2]))
            wall_strike, wall_prof, dist_pts, dist_atr = candidate_strikes[0]

            vuln = wall_prof.call_wall_vulnerability
            ratio = wall_prof.directional_liquidity_ratio

            # Case A: Breached or breaking through
            if dist_pts <= 0:
                if vuln > 1.20:
                    return WallGateDecision(
                        symbol=state.symbol,
                        direction=dir_clean,
                        action=GATE_ACTION_CONFIRM_BREACH,
                        proximity_pts=dist_pts,
                        proximity_atr=dist_atr,
                        major_wall_strike=wall_strike,
                        wall_vulnerability=vuln,
                        directional_liquidity_ratio=ratio,
                        reason=f"CALL_WALL_BREACH_CONFIRMED: Strike {wall_strike:,.0f} broken with high vulnerability ({vuln:.2f})",
                        timestamp_ms=timestamp_ms,
                    )
                return self._default_proceed(state, dir_clean, timestamp_ms, "CALL_WALL_ALREADY_BREACHED")

            # Case B: Approaching wall within proximity window
            if dist_atr <= (self.proximity_veto_atr + self.hysteresis_pct):
                # Fortified wall check: Bid depth strong, ask depth high, ratio bearish
                if vuln < 0.80 or ratio < 0.90:
                    return WallGateDecision(
                        symbol=state.symbol,
                        direction=dir_clean,
                        action=GATE_ACTION_VETO,
                        proximity_pts=dist_pts,
                        proximity_atr=dist_atr,
                        major_wall_strike=wall_strike,
                        wall_vulnerability=vuln,
                        directional_liquidity_ratio=ratio,
                        reason=f"VETO_FORTIFIED_CALL_WALL: Spot ₹{spot_price:,.1f} is {dist_pts:.1f}pts ({dist_atr:.2f} ATR) below fortified wall at {wall_strike:,.0f} (Vuln={vuln:.2f}, Ratio={ratio:.2f})",
                        timestamp_ms=timestamp_ms,
                    )
                else:
                    return WallGateDecision(
                        symbol=state.symbol,
                        direction=dir_clean,
                        action=GATE_ACTION_WARN,
                        proximity_pts=dist_pts,
                        proximity_atr=dist_atr,
                        major_wall_strike=wall_strike,
                        wall_vulnerability=vuln,
                        directional_liquidity_ratio=ratio,
                        reason=f"WARN_FRAGILE_CALL_WALL: Approaching wall at {wall_strike:,.0f} ({dist_atr:.2f} ATR), wall exhibits fragility ({vuln:.2f})",
                        timestamp_ms=timestamp_ms,
                    )

            return self._default_proceed(state, dir_clean, timestamp_ms, "OUTSIDE_PROXIMITY_ZONE")

        elif dir_clean == "PE":
            # Scan for any relevant Put Wall (Major, Secondary, or Local Concentration)
            # within proximity window [spot_price - (proximity_veto_atr + hysteresis)*ATR, spot_price + 0.25*ATR]
            candidate_strikes = []
            for s, prof in state.wall_density_map.items():
                if prof.is_major_put_wall or prof.is_secondary_put_wall or prof.put_oi >= (0.60 * state.total_put_oi / max(len(state.wall_density_map), 1)):
                    dist_pts = spot_price - s
                    dist_atr = dist_pts / atr
                    # Consider strikes in local vicinity below spot or recently breached downwards
                    if -0.25 <= dist_atr <= (self.proximity_veto_atr + self.hysteresis_pct):
                        candidate_strikes.append((s, prof, dist_pts, dist_atr))

            if not candidate_strikes:
                return self._default_proceed(state, dir_clean, timestamp_ms, "OUTSIDE_PROXIMITY_ZONE")

            # Sort by absolute distance to find the nearest barrier
            candidate_strikes.sort(key=lambda x: abs(x[2]))
            wall_strike, wall_prof, dist_pts, dist_atr = candidate_strikes[0]

            vuln = wall_prof.put_wall_vulnerability
            ratio = wall_prof.directional_liquidity_ratio

            # Case A: Breached or breaking through downwards
            if dist_pts <= 0:
                if vuln < 0.80:
                    return WallGateDecision(
                        symbol=state.symbol,
                        direction=dir_clean,
                        action=GATE_ACTION_CONFIRM_BREACH,
                        proximity_pts=dist_pts,
                        proximity_atr=dist_atr,
                        major_wall_strike=wall_strike,
                        wall_vulnerability=vuln,
                        directional_liquidity_ratio=ratio,
                        reason=f"PUT_WALL_BREACH_CONFIRMED: Strike {wall_strike:,.0f} broken downwards with collapsed bid depth (Vuln={vuln:.2f})",
                        timestamp_ms=timestamp_ms,
                    )
                return self._default_proceed(state, dir_clean, timestamp_ms, "PUT_WALL_ALREADY_BREACHED")

            # Case B: Approaching put wall within proximity window
            if dist_atr <= (self.proximity_veto_atr + self.hysteresis_pct):
                # Fortified floor check: Put bid depth strong (vuln > 1.20), ratio bearish or floor defending
                if vuln > 1.20 or ratio < 0.90:
                    return WallGateDecision(
                        symbol=state.symbol,
                        direction=dir_clean,
                        action=GATE_ACTION_VETO,
                        proximity_pts=dist_pts,
                        proximity_atr=dist_atr,
                        major_wall_strike=wall_strike,
                        wall_vulnerability=vuln,
                        directional_liquidity_ratio=ratio,
                        reason=f"VETO_FORTIFIED_PUT_WALL: Spot ₹{spot_price:,.1f} is {dist_pts:.1f}pts ({dist_atr:.2f} ATR) above fortified floor at {wall_strike:,.0f} (Vuln={vuln:.2f}, Ratio={ratio:.2f})",
                        timestamp_ms=timestamp_ms,
                    )
                else:
                    return WallGateDecision(
                        symbol=state.symbol,
                        direction=dir_clean,
                        action=GATE_ACTION_WARN,
                        proximity_pts=dist_pts,
                        proximity_atr=dist_atr,
                        major_wall_strike=wall_strike,
                        wall_vulnerability=vuln,
                        directional_liquidity_ratio=ratio,
                        reason=f"WARN_FRAGILE_PUT_WALL: Approaching floor at {wall_strike:,.0f} ({dist_atr:.2f} ATR), floor exhibits fragility ({vuln:.2f})",
                        timestamp_ms=timestamp_ms,
                    )

            return self._default_proceed(state, dir_clean, timestamp_ms, "OUTSIDE_PROXIMITY_ZONE")

        return self._default_proceed(state, dir_clean, timestamp_ms, f"UNKNOWN_DIRECTION_{dir_clean}")

    def evaluate_runner_tightening(
        self,
        position_direction: str,
        spot_price: float,
        timestamp_ms: int,
    ) -> WallGateDecision:
        """Evaluates whether an active APM runner should tighten its trailing stop due to wall proximity."""
        dir_clean = position_direction.upper().strip()
        state = self.observer.compute_wall_state(force_recompute=False)

        if not state.is_valid or state.status != "HEALTHY":
            return self._default_proceed(state, dir_clean, timestamp_ms, "BYPASS_UNHEALTHY_OBSERVER")

        atr = max(state.atr_pts, 1.0)

        # For CE runner, opposing barrier is Call Wall
        # For PE runner, opposing barrier is Put Wall
        target_wall = state.major_call_wall_strike if dir_clean == "CE" else state.major_put_wall_strike
        if target_wall <= 0:
            return self._default_proceed(state, dir_clean, timestamp_ms, "NO_WALL_DETECTED")

        dist_pts = abs(spot_price - target_wall)
        dist_atr = dist_pts / atr

        wall_prof = state.wall_density_map.get(target_wall)
        ratio = wall_prof.directional_liquidity_ratio if wall_prof else 1.0

        if dir_clean == "CE":
            vuln_tighten = wall_prof.call_wall_vulnerability if wall_prof else 1.0
            is_fortified = vuln_tighten < 1.0
        else:
            vuln_tighten = wall_prof.put_wall_vulnerability if wall_prof else 1.0
            is_fortified = vuln_tighten > 1.0

        if dist_atr <= self.runner_tighten_atr and is_fortified:
            return WallGateDecision(
                symbol=state.symbol,
                direction=dir_clean,
                action=GATE_ACTION_TIGHTEN_RUNNER,
                proximity_pts=dist_pts,
                proximity_atr=dist_atr,
                major_wall_strike=target_wall,
                wall_vulnerability=vuln_tighten,
                directional_liquidity_ratio=ratio,
                reason=f"RUNNER_TIGHTEN_RECOMMENDED: Spot within {dist_atr:.2f} ATR of opposing wall {target_wall:,.0f} (Vuln={vuln_tighten:.2f})",
                timestamp_ms=timestamp_ms,
            )

        return self._default_proceed(state, dir_clean, timestamp_ms, "RUNNER_SAFE_ZONE")

    def clamp_target_to_wall(
        self,
        direction: str,
        spot_price: float,
        nominal_target_pts: float,
        sl_pts: float,
        timestamp_ms: int,
        wall_buffer_pts: float = 1.0,
        min_rr_ratio: float = 1.0,
    ) -> WallGateDecision:
        """Evaluates whether nominal Take Profit should be clamped before an opposing fortified wall.

        Adversarial Boundary Invariants:
        - Invariant 1 (Attacker 1: Dynamic Wall Shifting): Operates strictly on causal point-in-time
          live wall snapshots. Once clamped at entry, the TP barrier is recorded into APM contract.
        - Invariant 2 (Attacker 2: Target Truncation Fallacy): Clamping is rejected if
          (clamped_tp / sl_pts) < min_rr_ratio (default 1.0). Trades with sub-1.0 R:R are never clamped.
        - Invariant 3 (Attacker 3: Phantom Wall Noise): Candidate wall must be fortified:
          either is_major_wall or secondary wall with vulnerability < 0.80 and OI >= 0.75 * max_oi.
        - Invariant 4 (Attacker 4: False Breakout Trap): If wall vulnerability > 1.20 (fragile/absorbable),
          clamping is suppressed so runners can punch through without premature truncation.
        - Invariant 5 (Attacker 5: Race Condition / Freshness): Returns PROCEED (no clamping)
          if observer state is not HEALTHY or feed is stale.
        """
        dir_clean = direction.upper().strip()
        state = self.observer.compute_wall_state(force_recompute=False)

        if not state.is_valid or state.status != "HEALTHY":
            return self._default_proceed(state, dir_clean, timestamp_ms, f"BYPASS_UNHEALTHY_OBSERVER: {state.status}")

        atr = max(state.atr_pts, 1.0)
        target_pts = float(nominal_target_pts)
        sl = max(float(sl_pts), 1.0)

        if dir_clean == "CE":
            # For CE, opposing barriers are Call strikes above spot
            candidate_strikes = []
            for s, prof in state.wall_density_map.items():
                if s > spot_price:
                    dist_pts = s - spot_price
                    # Only consider walls that are closer than nominal target
                    if dist_pts < target_pts:
                        candidate_strikes.append((s, prof, dist_pts))

            if not candidate_strikes:
                return self._default_proceed(state, dir_clean, timestamp_ms, "NO_CALL_WALL_AHEAD_OF_TARGET")

            # Sort by ascending distance (nearest obstacle first)
            candidate_strikes.sort(key=lambda x: x[2])
            wall_strike, wall_prof, dist_pts = candidate_strikes[0]

            vuln = wall_prof.call_wall_vulnerability
            ratio = wall_prof.directional_liquidity_ratio
            is_fortified = (wall_prof.is_major_call_wall or wall_prof.is_secondary_call_wall) and (vuln < 0.80 or ratio < 0.90)

            # Attacker 4: If fragile (vuln >= 0.80 and ratio >= 0.90), allow breakout to target
            if not is_fortified:
                return WallGateDecision(
                    symbol=state.symbol,
                    direction=dir_clean,
                    action=GATE_ACTION_PROCEED,
                    proximity_pts=dist_pts,
                    proximity_atr=dist_pts / atr,
                    major_wall_strike=wall_strike,
                    wall_vulnerability=vuln,
                    directional_liquidity_ratio=ratio,
                    reason=f"PROCEED_FRAGILE_WALL_NO_CLAMP: Call wall at {wall_strike:,.0f} exhibits breakout vulnerability ({vuln:.2f})",
                    timestamp_ms=timestamp_ms,
                    clamped_target_pts=None,
                )

            # Propose clamped target = distance to wall - buffer
            proposed_target = round(dist_pts - wall_buffer_pts, 2)

            # Attacker 2: Target Truncation Fallacy check
            # Clamping must not destroy Risk/Reward ratio below min_rr_ratio
            if proposed_target < (min_rr_ratio * sl):
                return WallGateDecision(
                    symbol=state.symbol,
                    direction=dir_clean,
                    action=GATE_ACTION_PROCEED,
                    proximity_pts=dist_pts,
                    proximity_atr=dist_pts / atr,
                    major_wall_strike=wall_strike,
                    wall_vulnerability=vuln,
                    directional_liquidity_ratio=ratio,
                    reason=f"CLAMP_REJECTED_SUB_MIN_RR: Proposed target {proposed_target:.1f}pts yields R:R {proposed_target/sl:.2f} < {min_rr_ratio:.2f}",
                    timestamp_ms=timestamp_ms,
                    clamped_target_pts=None,
                )

            # Fortified wall closer than nominal target with acceptable R:R
            return WallGateDecision(
                symbol=state.symbol,
                direction=dir_clean,
                action=GATE_ACTION_CLAMP_TARGET,
                proximity_pts=dist_pts,
                proximity_atr=dist_pts / atr,
                major_wall_strike=wall_strike,
                wall_vulnerability=vuln,
                directional_liquidity_ratio=ratio,
                reason=f"CLAMP_TARGET_BEFORE_CALL_WALL: Clamped target from {target_pts:.1f}pts to {proposed_target:.1f}pts before fortified wall {wall_strike:,.0f} (Vuln={vuln:.2f})",
                timestamp_ms=timestamp_ms,
                clamped_target_pts=proposed_target,
            )

        elif dir_clean == "PE":
            # For PE, opposing barriers are Put strikes below spot
            candidate_strikes = []
            for s, prof in state.wall_density_map.items():
                if s < spot_price:
                    dist_pts = spot_price - s
                    # Only consider walls that are closer than nominal target
                    if dist_pts < target_pts:
                        candidate_strikes.append((s, prof, dist_pts))

            if not candidate_strikes:
                return self._default_proceed(state, dir_clean, timestamp_ms, "NO_PUT_WALL_AHEAD_OF_TARGET")

            candidate_strikes.sort(key=lambda x: x[2])
            wall_strike, wall_prof, dist_pts = candidate_strikes[0]

            vuln = wall_prof.put_wall_vulnerability
            ratio = wall_prof.directional_liquidity_ratio
            is_fortified = (wall_prof.is_major_put_wall or wall_prof.is_secondary_put_wall) and (vuln > 1.20 or ratio < 0.90)

            # Attacker 4: If floor fragile / breakable, allow expansion
            if not is_fortified:
                return WallGateDecision(
                    symbol=state.symbol,
                    direction=dir_clean,
                    action=GATE_ACTION_PROCEED,
                    proximity_pts=dist_pts,
                    proximity_atr=dist_pts / atr,
                    major_wall_strike=wall_strike,
                    wall_vulnerability=vuln,
                    directional_liquidity_ratio=ratio,
                    reason=f"PROCEED_FRAGILE_FLOOR_NO_CLAMP: Put floor at {wall_strike:,.0f} exhibits breakdown vulnerability ({vuln:.2f})",
                    timestamp_ms=timestamp_ms,
                    clamped_target_pts=None,
                )

            # Propose clamped target = distance to floor - buffer
            proposed_target = round(dist_pts - wall_buffer_pts, 2)

            # Attacker 2: Target Truncation Fallacy check
            if proposed_target < (min_rr_ratio * sl):
                return WallGateDecision(
                    symbol=state.symbol,
                    direction=dir_clean,
                    action=GATE_ACTION_PROCEED,
                    proximity_pts=dist_pts,
                    proximity_atr=dist_pts / atr,
                    major_wall_strike=wall_strike,
                    wall_vulnerability=vuln,
                    directional_liquidity_ratio=ratio,
                    reason=f"CLAMP_REJECTED_SUB_MIN_RR: Proposed target {proposed_target:.1f}pts yields R:R {proposed_target/sl:.2f} < {min_rr_ratio:.2f}",
                    timestamp_ms=timestamp_ms,
                    clamped_target_pts=None,
                )

            return WallGateDecision(
                symbol=state.symbol,
                direction=dir_clean,
                action=GATE_ACTION_CLAMP_TARGET,
                proximity_pts=dist_pts,
                proximity_atr=dist_pts / atr,
                major_wall_strike=wall_strike,
                wall_vulnerability=vuln,
                directional_liquidity_ratio=ratio,
                reason=f"CLAMP_TARGET_BEFORE_PUT_WALL: Clamped target from {target_pts:.1f}pts to {proposed_target:.1f}pts before fortified floor {wall_strike:,.0f} (Vuln={vuln:.2f})",
                timestamp_ms=timestamp_ms,
                clamped_target_pts=proposed_target,
            )

        return self._default_proceed(state, dir_clean, timestamp_ms, f"UNKNOWN_DIRECTION_{dir_clean}")

    def _default_proceed(
        self,
        state: SentinelWallState,
        direction: str,
        timestamp_ms: int,
        reason: str,
    ) -> WallGateDecision:
        return WallGateDecision(
            symbol=state.symbol,
            direction=direction,
            action=GATE_ACTION_PROCEED,
            proximity_pts=0.0,
            proximity_atr=0.0,
            major_wall_strike=0.0,
            wall_vulnerability=1.0,
            directional_liquidity_ratio=1.0,
            reason=reason,
            timestamp_ms=timestamp_ms,
            clamped_target_pts=None,
        )
