import pytest
from core.opportunity_scoring import score_candidate
from core.hard_downgrade_engine import HardDowngradeDecision
from core.movement_contract import StrategyCandidate

def make_dummy_candidate(promotion_state="ADVISORY_ONLY"):
    return StrategyCandidate(
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
        lineage={"promotion_state": promotion_state}
    )

def make_dummy_decision(bucket="EXECUTABLE_CANDIDATE"):
    return HardDowngradeDecision(
        strategy_id="test_v1",
        symbol="AAPL",
        direction="BUY_CALL",
        movement_type="TREND_PULLBACK",
        original_bucket="EXECUTABLE_CANDIDATE",
        downgraded=(bucket != "EXECUTABLE_CANDIDATE"),
        downgraded_bucket=bucket,
        downgrade_reasons=(),
        hard_blockers=(),
        safety_flags=(),
        blockers=(),
        evidence_flags=(),
        warnings=(),
        executable_candidate=(bucket == "EXECUTABLE_CANDIDATE"),
    )

def test_promotion_state_disabled():
    candidate = make_dummy_candidate("DISABLED")
    decision = make_dummy_decision("EXECUTABLE_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "NO_TRADE_CANDIDATE"
    assert score.score_eligibility == "NO_TRADE_ONLY"
    assert score.final_score == 0.0

def test_promotion_state_negative_evidence():
    candidate = make_dummy_candidate("NEGATIVE_EVIDENCE")
    decision = make_dummy_decision("EXECUTABLE_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "NO_TRADE_CANDIDATE"
    assert score.score_eligibility == "NO_TRADE_ONLY"
    assert score.final_score == 0.0

def test_promotion_state_advisory_only():
    candidate = make_dummy_candidate("ADVISORY_ONLY")
    decision = make_dummy_decision("EXECUTABLE_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "ADVISORY_CANDIDATE"
    assert score.score_eligibility == "ADVISORY_ONLY"
    assert score.executable_candidate is False

def test_promotion_state_experimental():
    candidate = make_dummy_candidate("EXPERIMENTAL")
    decision = make_dummy_decision("EXECUTABLE_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "ADVISORY_CANDIDATE"
    assert score.score_eligibility == "ADVISORY_ONLY"
    assert score.executable_candidate is False

def test_promotion_state_unknown():
    candidate = make_dummy_candidate("UNKNOWN")
    decision = make_dummy_decision("EXECUTABLE_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "ADVISORY_CANDIDATE"
    assert score.score_eligibility == "ADVISORY_ONLY"
    assert score.executable_candidate is False

def test_promotion_state_paper_executable():
    candidate = make_dummy_candidate("PAPER_EXECUTABLE")
    decision = make_dummy_decision("EXECUTABLE_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "EXECUTABLE_CANDIDATE"
    assert "paper_executable_only" in score.safety_flags

def test_promotion_state_promoted_preserves_downgrade():
    candidate = make_dummy_candidate("PROMOTED")
    decision = make_dummy_decision("ADVISORY_CANDIDATE")
    score = score_candidate(candidate, decision)
    assert score.bucket == "ADVISORY_CANDIDATE"
