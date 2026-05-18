from core.candidate_classifier import classify_candidates
from core.hard_downgrade_engine import HardDowngradeDecision, apply_hard_downgrades
from core.movement_contract import StrategyCandidate
from core.opportunity_scoring import (
    ADVISORY_ONLY,
    NEEDS_CONFIRMATION,
    NO_TRADE_ONLY,
    SCORE_ELIGIBLE,
    SUPPRESSED_BY_DOWNGRADE,
    score_candidate,
    score_opportunities,
)


def _candidate(
    strategy_id="s1",
    *,
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    status="VALIDATED_CANDIDATE",
    blockers=(),
    warnings=(),
    trap_risk_score=0.1,
    price_structure_score=0.8,
    option_confirmation_score=0.8,
    liquidity_score=0.8,
    freshness_score=0.8,
    regime_alignment_score=0.8,
    timing_score=0.6,
    confluence_score=0.6,
    volatility_score=0.5,
):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol="NIFTY",
        direction=direction,
        status=status,
        raw_score=0.75,
        confidence_score=0.75,
        price_structure_score=price_structure_score,
        option_confirmation_score=option_confirmation_score,
        liquidity_score=liquidity_score,
        freshness_score=freshness_score,
        volatility_score=volatility_score,
        regime_alignment_score=regime_alignment_score,
        timing_score=timing_score,
        trap_risk_score=trap_risk_score,
        confluence_score=confluence_score,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
        warnings=warnings,
    )


def _score(candidates, **downgrade_kwargs):
    classification_report = classify_candidates(candidates)
    downgrade_report = apply_hard_downgrades(classification_report, **downgrade_kwargs)
    return score_opportunities(candidates, downgrade_report)


def _advisory_decision(candidate: StrategyCandidate) -> HardDowngradeDecision:
    return HardDowngradeDecision(
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        movement_type=candidate.movement_type,
        original_bucket="ADVISORY_CANDIDATE",
        downgraded_bucket="ADVISORY_CANDIDATE",
        downgraded=False,
        executable_candidate=False,
        downgrade_reasons=("informational_or_soft_blocked_candidate",),
        blockers=(),
        hard_blockers=(),
        warnings=("context_only",),
        safety_flags=(),
        evidence_flags=(),
    )


def test_clean_candidate_gets_score_eligible_explainable_score():
    candidate = _candidate("clean")
    report = _score([candidate])

    record = report.scores[0]
    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.score_eligible_count == 1
    assert record.score_eligibility == SCORE_ELIGIBLE
    assert record.executable_candidate is True
    assert 0.0 < record.final_score <= 1.0
    assert record.breakdown.component_scores["price_structure"] == 0.8
    assert record.breakdown.component_weights["option_confirmation"] > 0.0
    assert "base=" in record.score_explanation
    assert report.metadata["scope"] == "read_only_no_execution_no_ranking"


def test_fallback_blocked_candidate_is_suppressed_and_score_capped():
    candidate = _candidate(
        "fallback",
        status="BLOCKED_CANDIDATE",
        blockers=("FALLBACK_QUOTE_ONLY",),
        warnings=("fallback_used",),
        price_structure_score=1.0,
        option_confirmation_score=1.0,
        liquidity_score=1.0,
        freshness_score=1.0,
        regime_alignment_score=1.0,
    )

    report = _score([candidate])
    record = report.scores[0]

    assert record.score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert record.executable_candidate is False
    assert record.final_score <= 0.05
    assert "fallback_quote_data" in record.downgrade_reasons
    assert "fallback_data" in record.safety_flags
    assert report.suppressed_count == 1


def test_no_trade_candidate_gets_zero_score():
    candidate = _candidate(
        "no_trade",
        direction="NO_TRADE",
        movement_type="NO_TRADE_CHOP",
        status="NO_TRADE",
        blockers=("NO_TRADE_CHOP",),
    )

    report = _score([candidate])
    record = report.scores[0]

    assert record.score_eligibility == NO_TRADE_ONLY
    assert record.final_score == 0.0
    assert record.executable_candidate is False
    assert report.no_trade_count == 1


def test_raw_candidate_scores_as_needs_confirmation_with_cap():
    candidate = _candidate("raw", status="RAW_CANDIDATE")

    report = _score([candidate])
    record = report.scores[0]

    assert record.score_eligibility == NEEDS_CONFIRMATION
    assert record.executable_candidate is False
    assert record.final_score <= 0.65
    assert report.needs_confirmation_count == 1


def test_advisory_candidate_scores_as_advisory_only():
    candidate = _candidate("advisory", status="RAW_CANDIDATE", warnings=("context_only",))
    report = score_opportunities([candidate], [_advisory_decision(candidate)])

    record = report.scores[0]
    assert record.score_eligibility == ADVISORY_ONLY
    assert record.final_score <= 0.35
    assert record.executable_candidate is False


def test_global_no_trade_suppresses_all_directional_scores():
    candidate = _candidate("clean")
    report = _score([candidate], no_trade_active=True, no_trade_reason="NO_TRADE_CHOP")
    record = report.scores[0]

    assert record.score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert record.final_score <= 0.05
    assert "global_no_trade_active" in record.downgrade_reasons
    assert report.score_eligible_count == 0
    assert report.suppressed_count == 1


def test_trap_risk_penalty_reduces_score():
    low_trap = _candidate("low", trap_risk_score=0.0)
    high_trap = _candidate("high", trap_risk_score=1.0)

    low_report = _score([low_trap])
    high_report = _score([high_trap])

    assert high_report.scores[0].breakdown.trap_risk_penalty > low_report.scores[0].breakdown.trap_risk_penalty
    assert high_report.scores[0].final_score < low_report.scores[0].final_score


def test_score_opportunities_requires_matching_downgrade_decision():
    candidate = _candidate("missing")
    classification_report = classify_candidates([_candidate("other")])
    downgrade_report = apply_hard_downgrades(classification_report)

    try:
        score_opportunities([candidate], downgrade_report)
    except ValueError as exc:
        assert "missing_downgrade_decision" in str(exc)
    else:
        raise AssertionError("scoring accepted missing downgrade decision")


def test_score_candidate_rejects_mismatched_decision():
    candidate = _candidate("a")
    downgrade_report = apply_hard_downgrades(classify_candidates([_candidate("b")]))

    try:
        score_candidate(candidate, downgrade_report.decisions[0])
    except ValueError as exc:
        assert "candidate_and_downgrade_strategy_id_mismatch" in str(exc)
    else:
        raise AssertionError("scoring accepted mismatched decision")


def test_score_report_is_json_serializable():
    report = _score([_candidate("clean")])
    payload = report.to_json()

    assert "opportunity_score_v1" in payload
    assert "component_scores" in payload
