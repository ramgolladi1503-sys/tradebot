from dataclasses import replace

from core.hard_downgrade_engine import HardDowngradeDecision
from core.movement_contract import StrategyCandidate
from core.opportunity_scoring import ADVISORY_ONLY, SCORE_ELIGIBLE, score_candidate


def _candidate(strategy_id: str, *, entropy_state: str, normalized: float) -> StrategyCandidate:
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type="OPENING_DRIVE",
        symbol="NIFTY",
        direction="BUY_CALL",
        status="VALIDATED_CANDIDATE",
        raw_score=0.8,
        confidence_score=0.8,
        price_structure_score=0.8,
        option_confirmation_score=0.8,
        liquidity_score=0.8,
        freshness_score=0.8,
        volatility_score=0.8,
        regime_alignment_score=0.8,
        timing_score=0.8,
        trap_risk_score=0.0,
        confluence_score=0.8,
        entry_trigger="test",
        invalid_if="test",
        rank_reason="test",
        lineage={"promotion_state": "PROMOTED"},
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8},
        evidence={
            "session_bucket": "MID_SESSION",
            "entropy_state": {
                "current_value": normalized,
                "normalized": normalized,
                "state": entropy_state,
            },
        },
    )


def _clean_decision(strategy_id: str) -> HardDowngradeDecision:
    return HardDowngradeDecision(
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="OPENING_DRIVE",
        original_bucket="EXECUTABLE_CANDIDATE",
        downgraded_bucket="EXECUTABLE_CANDIDATE",
        downgraded=False,
        executable_candidate=True,
        downgrade_reasons=(),
        blockers=(),
        hard_blockers=(),
        warnings=(),
        safety_flags=(),
        evidence_flags=(),
    )


def test_unknown_low_entropy_strategy_cannot_inherit_executable_bucket():
    strategy_id = "unknown_alpha_v1"
    result = score_candidate(
        _candidate(strategy_id, entropy_state="LOW", normalized=0.20),
        _clean_decision(strategy_id),
    )
    assert result.executable_candidate is False
    assert result.bucket == "ADVISORY_CANDIDATE"
    assert result.score_eligibility == ADVISORY_ONLY


def test_unknown_high_entropy_strategy_is_suppressed():
    strategy_id = "unknown_alpha_v1"
    result = score_candidate(
        _candidate(strategy_id, entropy_state="HIGH", normalized=0.90),
        _clean_decision(strategy_id),
    )
    assert result.executable_candidate is False
    assert result.bucket == "SUPPRESSED_CANDIDATE"


def test_generic_scorer_fixture_without_regime_context_retains_legacy_contract():
    strategy_id = "clean"
    candidate = replace(
        _candidate(strategy_id, entropy_state="LOW", normalized=0.20),
        evidence={},
        lineage={"promotion_state": "PROMOTED"},
    )
    result = score_candidate(candidate, _clean_decision(strategy_id))
    assert result.executable_candidate is True
    assert result.bucket == "EXECUTABLE_CANDIDATE"
    assert result.score_eligibility == SCORE_ELIGIBLE


def test_unknown_movement_candidate_without_regime_context_fails_closed():
    strategy_id = "future_movement_v1"
    candidate = replace(
        _candidate(strategy_id, entropy_state="LOW", normalized=0.20),
        evidence={},
        lineage={"source": "movement_strategy", "promotion_state": "PROMOTED"},
    )
    result = score_candidate(candidate, _clean_decision(strategy_id))
    assert result.executable_candidate is False
    assert result.bucket == "ADVISORY_CANDIDATE"
    assert result.score_eligibility == ADVISORY_ONLY
