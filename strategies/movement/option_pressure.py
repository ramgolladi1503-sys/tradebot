"""Option Pressure Confirmation movement strategy.

This wrapper exposes the option confirmation layer as read-only movement
candidates. It does not promote anything to executable status, rank candidates,
or alter runtime behavior.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.option_confirmation import assess_option_pressure
from core.strategy_parameter_profiles import resolve_required_profile_parameters
from strategies.movement._utils import block_on_required_fields, clamp_score

STRATEGY_ID = "option_pressure_confirmation_v1"
MOVEMENT_TYPE = "OPTION_PRESSURE_CONFIRMATION"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_PRESSURE_SCORE": 0.45,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_option_pressure_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Emit advisory option-pressure candidates for the dominant side."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_pressure_score = float(params["MIN_PRESSURE_SCORE"])
    required_quote_fields = (
        ("option_ce_ltp", ctx.option_ce_ltp, "positive"),
        ("ce_premium_change", ctx.ce_premium_change, "finite"),
        ("ce_spread_pct", ctx.ce_spread_pct, "non_negative"),
        ("ce_depth", ctx.ce_depth, "non_negative"),
        ("option_pe_ltp", ctx.option_pe_ltp, "positive"),
        ("pe_premium_change", ctx.pe_premium_change, "finite"),
        ("pe_spread_pct", ctx.pe_spread_pct, "non_negative"),
        ("pe_depth", ctx.pe_depth, "non_negative"),
        ("option_ltp_age_sec", ctx.option_ltp_age_sec, "non_negative"),
    )

    assessment = assess_option_pressure(ctx)
    if assessment.dominant_direction == "NEUTRAL":
        block_on_required_fields(
            STRATEGY_ID,
            reason="missing_required_option_quote_evidence",
            field_specs=required_quote_fields,
        )
        return ()

    if assessment.dominant_direction == "BUY_CALL":
        score = assessment.bullish_score
        side = assessment.ce
        opposite_score = assessment.bearish_score
    else:
        score = assessment.bearish_score
        side = assessment.pe
        opposite_score = assessment.bullish_score

    if score < min_pressure_score:
        block_on_required_fields(
            STRATEGY_ID,
            reason="missing_required_option_quote_evidence",
            field_specs=required_quote_fields,
        )
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
            confidence_score=clamp_score(
                score * (1.0 - clamp_score(regime.scores.get("TRAP_RISK", 0.0)) * 0.20)
            ),
            price_structure_score=clamp_score(
                max(
                    regime.scores.get("TREND_UP", 0.0),
                    regime.scores.get("TREND_DOWN", 0.0),
                    regime.scores.get("VOLATILITY_EXPANSION", 0.0),
                )
            ),
            option_confirmation_score=score,
            liquidity_score=side.liquidity_score,
            freshness_score=side.freshness_score,
            volatility_score=clamp_score(
                regime.scores.get("VOLATILITY_EXPANSION", 0.0)
            ),
            regime_alignment_score=clamp_score(
                max(
                    regime.scores.get("TREND_UP", 0.0),
                    regime.scores.get("TREND_DOWN", 0.0),
                )
            ),
            timing_score=0.5,
            trap_risk_score=clamp_score(regime.scores.get("TRAP_RISK", 0.0)),
            confluence_score=score,
            entry_trigger="dominant_option_pressure_confirmation",
            invalid_if="option_pressure_loses_dominance_or_quote_quality_degrades",
            rank_reason="option side pressure is dominant and quote quality is visible",
            blockers=blockers,
            warnings=assessment.warnings,
            confluence_tags=(
                "option_pressure",
                "premium_confirmation",
                "quote_quality",
            ),
            suppression_tags=("confirmation_layer_not_execution_signal",),
            source_signals=(STRATEGY_ID, MOVEMENT_TYPE),
            regime_scores=regime.scores,
            evidence=evidence,
            lineage={
                "source": "option_confirmation",
                "strategy_id": STRATEGY_ID,
                "strategy_version": "v1",
                "params_used": params,
                "params_hash": profile.parameter_hash,
                "promotion_state": "ADVISORY_ONLY",
            },
        ),
    )


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_option_pressure_candidates"]
