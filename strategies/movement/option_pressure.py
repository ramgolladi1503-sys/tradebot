"""Option Pressure Confirmation movement strategy.

This wrapper exposes the option confirmation layer as read-only movement
candidates. It does not promote anything to executable status, rank candidates,
or alter runtime behavior.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.option_confirmation import assess_option_pressure
from strategies.movement._utils import clamp_score

STRATEGY_ID = "option_pressure_confirmation_v1"
MOVEMENT_TYPE = "OPTION_PRESSURE_CONFIRMATION"
MIN_PRESSURE_SCORE = 0.45


def generate_option_pressure_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Emit advisory option-pressure candidates for the dominant side."""

    assessment = assess_option_pressure(ctx)
    if assessment.dominant_direction == "NEUTRAL":
        return ()

    if assessment.dominant_direction == "BUY_CALL":
        score = assessment.bullish_score
        side = assessment.ce
        opposite_score = assessment.bearish_score
    else:
        score = assessment.bearish_score
        side = assessment.pe
        opposite_score = assessment.bullish_score

    if score < MIN_PRESSURE_SCORE:
        return ()

    blockers = tuple(sorted(set(side.blockers)))
    status = "BLOCKED_CANDIDATE" if blockers else "VALIDATED_CANDIDATE"
    evidence = {
        "assessment": assessment.to_dict(),
        "dominant_direction": assessment.dominant_direction,
        "pressure_score": score,
        "opposite_score": opposite_score,
        "dominance_delta": assessment.dominance_delta,
        "regime_primary": regime.primary_regime,
    }
    return (
        StrategyCandidate(
            schema_version=1,
            strategy_id=STRATEGY_ID,
            movement_type=MOVEMENT_TYPE,
            symbol=ctx.symbol,
            direction=assessment.dominant_direction,
            status=status,
            raw_score=score,
            confidence_score=clamp_score(score * (1.0 - clamp_score(regime.scores.get("TRAP_RISK", 0.0)) * 0.20)),
            price_structure_score=clamp_score(max(regime.scores.get("TREND_UP", 0.0), regime.scores.get("TREND_DOWN", 0.0), regime.scores.get("VOLATILITY_EXPANSION", 0.0))),
            option_confirmation_score=score,
            liquidity_score=side.liquidity_score,
            freshness_score=side.freshness_score,
            volatility_score=clamp_score(regime.scores.get("VOLATILITY_EXPANSION", 0.0)),
            regime_alignment_score=clamp_score(max(regime.scores.get("TREND_UP", 0.0), regime.scores.get("TREND_DOWN", 0.0))),
            timing_score=0.5,
            trap_risk_score=clamp_score(regime.scores.get("TRAP_RISK", 0.0)),
            confluence_score=score,
            entry_trigger="dominant_option_pressure_confirmation",
            invalid_if="option_pressure_loses_dominance_or_quote_quality_degrades",
            rank_reason="option side pressure is dominant and quote quality is visible",
            blockers=blockers,
            warnings=assessment.warnings,
            confluence_tags=("option_pressure", "premium_confirmation", "quote_quality"),
            suppression_tags=("confirmation_layer_not_execution_signal",),
            source_signals=(STRATEGY_ID, MOVEMENT_TYPE),
            regime_scores=regime.scores,
            evidence=evidence,
            lineage={"source": "option_confirmation", "strategy_id": STRATEGY_ID},
        ),
    )


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_option_pressure_candidates"]
