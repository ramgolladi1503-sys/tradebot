"""No-Trade movement strategy wrapper.

This exposes the no-trade assessment as a read-only StrategyCandidate. It does
not execute, rank, or mutate runtime behavior.
"""

from __future__ import annotations

from typing import Iterable

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.no_trade_engine import assess_no_trade
from strategies.movement._utils import clamp_score

STRATEGY_ID = "no_trade_engine_v1"
MOVEMENT_TYPE = "NO_TRADE_CHOP"


def generate_no_trade_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    candidates: Iterable[StrategyCandidate] | None = None,
) -> tuple[StrategyCandidate, ...]:
    """Emit one NO_TRADE candidate when suppression evidence exists."""

    assessment = assess_no_trade(ctx, regime, candidates)
    if not assessment.no_trade:
        return ()

    return (
        StrategyCandidate(
            schema_version=1,
            strategy_id=STRATEGY_ID,
            movement_type=MOVEMENT_TYPE,
            symbol=ctx.symbol,
            direction="NO_TRADE",
            status="NO_TRADE",
            raw_score=assessment.severity,
            confidence_score=assessment.severity,
            price_structure_score=0.0,
            option_confirmation_score=0.0,
            liquidity_score=0.0,
            freshness_score=0.0,
            volatility_score=clamp_score(
                regime.scores.get("VOLATILITY_EXPANSION", 0.0)
            ),
            regime_alignment_score=clamp_score(
                max(
                    regime.scores.get("CHOP", 0.0),
                    regime.scores.get("INCONCLUSIVE", 0.0),
                )
            ),
            timing_score=0.0,
            trap_risk_score=clamp_score(regime.scores.get("TRAP_RISK", 0.0)),
            confluence_score=assessment.severity,
            entry_trigger="no_trade_environment_detected",
            invalid_if="no_trade_blockers_clear_and_candidate_quality_confirms",
            rank_reason=f"No-trade condition active: {assessment.primary_reason}",
            blockers=assessment.blockers,
            warnings=assessment.warnings,
            confluence_tags=("no_trade", "suppression", assessment.primary_reason),
            suppression_tags=("suppress_weak_candidates", "no_trade_engine"),
            source_signals=(STRATEGY_ID, MOVEMENT_TYPE),
            regime_scores=regime.scores,
            evidence={"assessment": assessment.to_dict()},
            lineage={"source": "no_trade_engine", "strategy_id": STRATEGY_ID},
        ),
    )


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_no_trade_candidates"]
