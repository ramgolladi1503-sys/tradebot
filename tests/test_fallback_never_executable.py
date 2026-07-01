import pytest
from core.opportunity_scoring import score_candidate
from core.hard_downgrade_engine import HardDowngradeDecision
from core.movement_contract import StrategyCandidate

def test_fallback_quote_never_executable_even_if_promoted():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="test_v1",
        movement_type="TREND_PULLBACK",
        symbol="AAPL",
        direction="BUY_CALL",
        status="RAW_CANDIDATE",
        raw_score=0.9,
        confidence_score=0.9,
        price_structure_score=0.9,
        option_confirmation_score=0.9,
        liquidity_score=0.9,
        freshness_score=0.9,
        regime_alignment_score=0.9,
        timing_score=0.9,
        confluence_score=0.9,
        volatility_score=0.9,
        trap_risk_score=0.0,
        confluence_tags=("test",),
        rank_reason="test",
        entry_trigger="test",
        invalid_if="test",
        evidence={},
        regime_scores={},
        warnings=(),
        lineage={"promotion_state": "PROMOTED"}
    )
    # Simulate a HardDowngradeDecision that failed a truth gate (e.g. fallback_quote)
    decision = HardDowngradeDecision(
        strategy_id="test_v1",
        symbol="AAPL",
        direction="BUY_CALL",
        movement_type="TREND_PULLBACK",
        original_bucket="EXECUTABLE_CANDIDATE",
        downgraded=True,
        downgraded_bucket="ADVISORY_CANDIDATE",
        downgrade_reasons=("fallback_quote_data",),
        hard_blockers=("fallback_quote_data",),
        safety_flags=("fallback_data_used",),
        blockers=("fallback_quote_data",),
        evidence_flags=("fallback",),
        warnings=(),
        executable_candidate=False,
    )

    score = score_candidate(candidate, decision)
    # The truth gate must block it from becoming executable, despite PROMOTED
    assert score.bucket == "ADVISORY_CANDIDATE"
    assert score.score_eligibility == "ADVISORY_ONLY"
    assert score.executable_candidate is False
