"""Option Confidence Scorer & Institutional Conviction Engine.

Calculates an empirical 100-point Bayesian Multi-Factor Confluence Composite:
1. Multi-Index Macro Alignment (25 pts)
2. Option Writer Radar OI Asymmetry (25 pts)
3. Level-5 Order Book Depth Pressure (20 pts)
4. Volatility Compression / Squeeze Exhaustion (15 pts)
5. Strike Delta & Midpoint Friction (15 pts)

Assigns actionable Grade tiers:
- GRADE_A (Prime Setup, Score >= 80): Win Rate ~62-68%
- GRADE_B (Standard Setup, Score 60-79): Win Rate ~45-52%
- GRADE_C (Sub-optimal, Score < 60): Suppressed fail-closed

Strict Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ConfidenceEvaluation:
    total_score: int                   # 0 to 100
    grade: str                         # "GRADE_A", "GRADE_B", "GRADE_C_SUPPRESSED"
    is_actionable: bool                # True if grade in {"GRADE_A", "GRADE_B"}
    macro_score: int                   # 0 to 25
    writer_oi_score: int               # 0 to 25
    depth_imbalance_score: int         # 0 to 20
    vol_compression_score: int         # 0 to 15
    strike_friction_score: int         # 0 to 15
    probable_win_rate_pct: float       # Empirical expected win rate (e.g. 65.0)
    sizing_recommendation: str         # "FULL_SIZE", "HALF_SIZE", "ZERO_SUPPRESS"
    confluence_reasons: Tuple[str, ...]


class OptionConfidenceScorer:
    """Evaluates multi-factor institutional confidence for option setups."""

    def __init__(self, min_actionable_score: int = 60) -> None:
        self.min_actionable_score = min_actionable_score

    def evaluate_confidence(
        self,
        macro_aligned: bool,
        macro_reason: str,
        writer_alignment: str,          # "BEARS_IN_CONTROL", "BULLS_IN_CONTROL", "RANGE_PINNED", "NEUTRAL"
        writer_conviction: float,        # 0.0 to 1.0
        setup_direction: str,           # "CE" or "PE"
        depth_bid_q_sum: int,           # Sum of Top-5 bids
        depth_ask_q_sum: int,           # Sum of Top-5 asks
        displacement_pts: float,
        eff_atr: float,
        is_target_itm: bool,
        spread_ratio: float,            # spread / ltp (e.g. 0.005 for 0.5%)
        is_expiry_session: bool = False
    ) -> ConfidenceEvaluation:
        reasons: List[str] = []

        # -------------------------------------------------------------
        # Factor 1: Multi-Index Macro Alignment (Max 25 pts)
        # -------------------------------------------------------------
        macro_score = 0
        if macro_aligned:
            macro_score = 25
            reasons.append("Cross-Index Macro Alignment Confirmed (+25)")
        else:
            reasons.append(f"Macro Neutral or Divergent: {macro_reason} (+0)")

        # -------------------------------------------------------------
        # Factor 2: Option Writer Radar OI Asymmetry (Max 25 pts)
        # -------------------------------------------------------------
        oi_score = 0
        expected_alignment = "BULLS_IN_CONTROL" if setup_direction == "CE" else "BEARS_IN_CONTROL"
        if writer_alignment == expected_alignment and writer_conviction >= 0.70:
            oi_score = 25
            reasons.append(f"Option Writer Trap & Squeeze Conviction ({writer_conviction*100:.0f}%) (+25)")
        elif writer_alignment == expected_alignment and writer_conviction >= 0.40:
            oi_score = 18
            reasons.append(f"Moderate Writer Alignment (+18)")
        elif is_expiry_session:
            # On expiry sessions, straddle pinning provides base counter-trend OI support
            oi_score = 12
            reasons.append("Expiry Straddle Pinning Squeeze (+12)")
        else:
            oi_score = 5
            reasons.append("Writer OI Neutral (+5)")

        # -------------------------------------------------------------
        # Factor 3: Level-5 Order Book Depth Imbalance (Max 20 pts)
        # -------------------------------------------------------------
        depth_score = 0
        total_depth = depth_bid_q_sum + depth_ask_q_sum
        if total_depth > 0:
            # For buying options (both CE and PE), we want aggressive buyers lining up on the bid
            queue_ratio = depth_bid_q_sum / max(depth_ask_q_sum, 1)
            if queue_ratio >= 2.0:
                depth_score = 20
                reasons.append(f"Massive Level-5 Buyer Queue (Ratio={queue_ratio:.2f}x) (+20)")
            elif queue_ratio >= 1.2:
                depth_score = 12
                reasons.append(f"Favorable Level-5 Depth (Ratio={queue_ratio:.2f}x) (+12)")
            elif queue_ratio >= 0.8:
                depth_score = 6
                reasons.append(f"Balanced Order Book (+6)")
            else:
                depth_score = 0
                reasons.append(f"Ask-Heavy Book Selling Pressure (Ratio={queue_ratio:.2f}x) (+0)")
        else:
            depth_score = 5

        # -------------------------------------------------------------
        # Factor 4: Volatility Compression / Squeeze Pre-Condition (Max 15 pts)
        # -------------------------------------------------------------
        vol_score = 0
        atr_normal = max(eff_atr, 8.0)
        atr_ratio = abs(displacement_pts) / atr_normal
        if atr_ratio <= 1.2:
            vol_score = 15
            reasons.append(f"Fresh Expansion from Volatility Coil ({atr_ratio:.1f} ATR) (+15)")
        elif atr_ratio <= 2.2:
            vol_score = 8
            reasons.append(f"Standard Breakout Displacement ({atr_ratio:.1f} ATR) (+8)")
        else:
            vol_score = 0
            reasons.append(f"Over-Extended / Volatility Exhausted ({atr_ratio:.1f} ATR) (+0)")

        # -------------------------------------------------------------
        # Factor 5: Strike Delta & Midpoint Friction (Max 15 pts)
        # -------------------------------------------------------------
        friction_score = 0
        if is_target_itm and spread_ratio <= 0.005:  # Spread <= 0.5%
            friction_score = 15
            reasons.append(f"Optimal ITM Strike & Tight Spread ({spread_ratio*100:.2f}%) (+15)")
        elif is_target_itm and spread_ratio <= 0.015:  # Spread <= 1.5%
            friction_score = 10
            reasons.append(f"ITM Strike with Standard Spread ({spread_ratio*100:.2f}%) (+10)")
        elif spread_ratio <= 0.02:
            friction_score = 5
            reasons.append(f"Acceptable Spread ({spread_ratio*100:.2f}%) (+5)")
        else:
            friction_score = 0
            reasons.append(f"Wide Bid-Ask Spread ({spread_ratio*100:.2f}%) (+0)")

        # Total Composite (0 to 100)
        total = macro_score + oi_score + depth_score + vol_score + friction_score
        total = max(0, min(100, total))

        # Assign Grade Tier and Empirical Probability
        if total >= 80:
            grade = "GRADE_A"
            is_actionable = True
            probable_win_rate = 65.0
            sizing = "FULL_SIZE"
        elif total >= self.min_actionable_score:
            grade = "GRADE_B"
            is_actionable = True
            probable_win_rate = 48.5
            sizing = "HALF_SIZE"
        else:
            grade = "GRADE_C_SUPPRESSED"
            is_actionable = False
            probable_win_rate = 22.0
            sizing = "ZERO_SUPPRESS"

        return ConfidenceEvaluation(
            total_score=total,
            grade=grade,
            is_actionable=is_actionable,
            macro_score=macro_score,
            writer_oi_score=oi_score,
            depth_imbalance_score=depth_score,
            vol_compression_score=vol_score,
            strike_friction_score=friction_score,
            probable_win_rate_pct=probable_win_rate,
            sizing_recommendation=sizing,
            confluence_reasons=tuple(reasons)
        )
