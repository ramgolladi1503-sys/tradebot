import pytest
from core.movement_contract import StrategyCandidate, StrategyContext
from core.hard_downgrade_engine import HardDowngradeDecision
from core.opportunity_scoring import score_candidate, SCORE_ELIGIBLE, ADVISORY_ONLY, SUPPRESSED_BY_DOWNGRADE

def test_orb_high_entropy_generation():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="ORB",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "OPEN_DISCOVERY", "entropy_state": {"current_value": 0.9, "normalized": 0.8, "state": "HIGH"}},
    )
    decision = HardDowngradeDecision(
        strategy_id="ORB",
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
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is True
    assert result.score_eligibility == SCORE_ELIGIBLE

def test_mean_reversion_high_entropy_blocked():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="MEAN_REVERSION",
        movement_type="MEAN_REVERSION_EXTENSION",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "MIDDAY_CHOP", "entropy_state": {"current_value": 0.9, "normalized": 0.8, "state": "HIGH"}},
    )
    decision = HardDowngradeDecision(
        strategy_id="MEAN_REVERSION",
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="MEAN_REVERSION_EXTENSION",
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
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is False
    assert result.score_eligibility == ADVISORY_ONLY
    assert result.bucket == "ADVISORY_CANDIDATE"

def test_short_premium_high_entropy_blocked():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="SHORT_PREMIUM",
        movement_type="MEAN_REVERSION_EXTENSION",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "MIDDAY_CHOP", "entropy_state": {"current_value": 0.9, "normalized": 0.8, "state": "HIGH"}},
    )
    decision = HardDowngradeDecision(
        strategy_id="SHORT_PREMIUM",
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="MEAN_REVERSION_EXTENSION",
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
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is False
    assert result.score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert result.bucket == "SUPPRESSED_CANDIDATE"

def test_orb_fallback_advisory_quote_not_executable():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="ORB",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "OPEN_DISCOVERY", "entropy_state": {"current_value": 0.9, "normalized": 0.8, "state": "HIGH"}},
    )
    decision = HardDowngradeDecision(
        strategy_id="ORB",
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="OPENING_DRIVE",
        original_bucket="EXECUTABLE_CANDIDATE",
        downgraded_bucket="ADVISORY_CANDIDATE",
        downgraded=True,
        executable_candidate=False,
        downgrade_reasons=("fallback_quote",),
        blockers=(),
        hard_blockers=(),
        warnings=(),
        safety_flags=(),
        evidence_flags=(),
    )
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is False
    assert result.bucket == "ADVISORY_CANDIDATE"
    assert result.score_eligibility == ADVISORY_ONLY

def test_orb_stale_quote_not_executable():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="ORB",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "OPEN_DISCOVERY", "entropy_state": {"current_value": 0.9, "normalized": 0.8, "state": "HIGH"}},
    )
    decision = HardDowngradeDecision(
        strategy_id="ORB",
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="OPENING_DRIVE",
        original_bucket="EXECUTABLE_CANDIDATE",
        downgraded_bucket="NO_TRADE_CANDIDATE",
        downgraded=True,
        executable_candidate=False,
        downgrade_reasons=("stale_quote",),
        blockers=("stale_quote",),
        hard_blockers=("stale_quote",),
        warnings=(),
        safety_flags=(),
        evidence_flags=(),
    )
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is False
    assert result.final_score == 0.0
    assert "stale_quote" in result.downgrade_reasons

def test_unknown_strategy_high_entropy_blocked():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="UNKNOWN_ALPHA",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "OPEN_DISCOVERY", "entropy_state": {"current_value": 0.9, "normalized": 0.8, "state": "HIGH"}},
    )
    decision = HardDowngradeDecision(
        strategy_id="UNKNOWN_ALPHA",
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
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is False
    assert result.bucket == "SUPPRESSED_CANDIDATE"

def test_missing_unknown_entropy_fail_safe():
    candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="ORB",
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
        entry_trigger="orb",
        invalid_if="no",
        rank_reason="test",
        blockers=(),
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=(),
        regime_scores={"TREND_UP": 0.8, "VOLATILITY_EXPANSION": 0.8},
        evidence={"volume_z": 2.5, "session_bucket": "OPEN_DISCOVERY"},
    )
    decision = HardDowngradeDecision(
        strategy_id="ORB",
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
    result = score_candidate(candidate, decision)
    assert result.executable_candidate is False
    assert result.bucket == "ADVISORY_CANDIDATE"

def test_mixed_ranking():
    from core.ranking_orchestrator import rank_candidates
    candidates = [
        # 1. Executable ORB
        score_candidate(
            StrategyCandidate(schema_version=1, strategy_id="ORB", movement_type="OPENING_DRIVE", symbol="NIFTY", direction="BUY_CALL", status="VALIDATED_CANDIDATE", raw_score=0.8, confidence_score=0.8, price_structure_score=0.8, option_confirmation_score=0.8, liquidity_score=0.8, freshness_score=0.8, volatility_score=0.8, regime_alignment_score=0.8, timing_score=0.8, trap_risk_score=0.0, confluence_score=0.8, entry_trigger="orb", invalid_if="no", rank_reason="test", blockers=(), warnings=(), confluence_tags=(), suppression_tags=(), source_signals=(), regime_scores={"VOLATILITY_EXPANSION": 0.8}, evidence={"session_bucket": "OPEN_DISCOVERY", "entropy_state": {"state": "HIGH"}}),
            HardDowngradeDecision("ORB", "NIFTY", "BUY_CALL", "OPENING_DRIVE", "EXECUTABLE_CANDIDATE", "EXECUTABLE_CANDIDATE", False, True, (), (), (), (), (), ())
        ),
        # 2. Fallback ORB
        score_candidate(
            StrategyCandidate(schema_version=1, strategy_id="ORB", movement_type="OPENING_DRIVE", symbol="NIFTY", direction="BUY_CALL", status="VALIDATED_CANDIDATE", raw_score=0.8, confidence_score=0.8, price_structure_score=0.8, option_confirmation_score=0.8, liquidity_score=0.8, freshness_score=0.8, volatility_score=0.8, regime_alignment_score=0.8, timing_score=0.8, trap_risk_score=0.0, confluence_score=0.8, entry_trigger="orb", invalid_if="no", rank_reason="test", blockers=(), warnings=(), confluence_tags=(), suppression_tags=(), source_signals=(), regime_scores={"VOLATILITY_EXPANSION": 0.8}, evidence={"session_bucket": "OPEN_DISCOVERY", "entropy_state": {"state": "HIGH"}}),
            HardDowngradeDecision("ORB", "NIFTY", "BUY_CALL", "OPENING_DRIVE", "EXECUTABLE_CANDIDATE", "ADVISORY_CANDIDATE", True, False, ("fallback_quote",), (), (), (), (), ())
        ),
        # 3. Blocked Mean Reversion
        score_candidate(
            StrategyCandidate(schema_version=1, strategy_id="MEAN_REVERSION", movement_type="MEAN_REVERSION_EXTENSION", symbol="NIFTY", direction="BUY_CALL", status="VALIDATED_CANDIDATE", raw_score=0.8, confidence_score=0.8, price_structure_score=0.8, option_confirmation_score=0.8, liquidity_score=0.8, freshness_score=0.8, volatility_score=0.8, regime_alignment_score=0.8, timing_score=0.8, trap_risk_score=0.0, confluence_score=0.8, entry_trigger="orb", invalid_if="no", rank_reason="test", blockers=(), warnings=(), confluence_tags=(), suppression_tags=(), source_signals=(), regime_scores={}, evidence={"session_bucket": "MIDDAY_CHOP", "entropy_state": {"state": "HIGH"}}),
            HardDowngradeDecision("MEAN_REVERSION", "NIFTY", "BUY_CALL", "MEAN_REVERSION_EXTENSION", "EXECUTABLE_CANDIDATE", "EXECUTABLE_CANDIDATE", False, True, (), (), (), (), (), ())
        ),
    ]
    ranked = rank_candidates(candidates)
    
    # Expose only the fully valid executable ORB candidate
    exec_cands = [r for r in ranked.ranks if r.executable_candidate]
    exec_cands_len = len(exec_cands)
    assert exec_cands_len == 1
    assert exec_cands[0].strategy_id == "ORB"
    assert exec_cands[0].executable_candidate is True
    
    ranks_len = len(ranked.ranks)
    assert ranks_len == 3

