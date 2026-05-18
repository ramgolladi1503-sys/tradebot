from core.directional_balance import analyze_directional_balance, direction_family
from core.opportunity_scoring import (
    NO_TRADE_ONLY,
    SCORE_ELIGIBLE,
    SUPPRESSED_BY_DOWNGRADE,
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)


def _breakdown(final_score=0.5):
    return OpportunityScoreBreakdown(
        component_scores={},
        component_weights={},
        weighted_component_scores={},
        base_score=final_score,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=final_score,
    )


def _score(
    strategy_id="s1",
    *,
    direction="BUY_CALL",
    final_score=0.5,
    eligibility=SCORE_ELIGIBLE,
    blockers=(),
    warnings=(),
    safety_flags=(),
):
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction=direction,
        movement_type="COMPRESSION_BREAKOUT",
        bucket="EXECUTABLE_CANDIDATE" if eligibility == SCORE_ELIGIBLE else "SUPPRESSED_CANDIDATE",
        score_eligibility=eligibility,
        final_score=final_score,
        executable_candidate=eligibility == SCORE_ELIGIBLE,
        score_explanation="unit",
        downgrade_reasons=(),
        safety_flags=safety_flags,
        blockers=blockers,
        warnings=warnings,
        breakdown=_breakdown(final_score),
    )


def _report(scores):
    return OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=len(scores),
        score_eligible_count=sum(1 for item in scores if item.score_eligibility == SCORE_ELIGIBLE),
        needs_confirmation_count=0,
        advisory_count=0,
        suppressed_count=sum(1 for item in scores if item.score_eligibility == SUPPRESSED_BY_DOWNGRADE),
        no_trade_count=sum(1 for item in scores if item.score_eligibility == NO_TRADE_ONLY),
        scores=tuple(scores),
        blockers=tuple(sorted(set(blocker for item in scores for blocker in item.blockers))),
        warnings=tuple(sorted(set(warning for item in scores for warning in item.warnings))),
        safety_flags=tuple(sorted(set(flag for item in scores for flag in item.safety_flags))),
        metadata={"scorer": "opportunity_score_v1"},
    )


def test_direction_family_maps_call_and_put_aliases():
    assert direction_family("BUY_CALL") == "BULLISH"
    assert direction_family("CE") == "BULLISH"
    assert direction_family("BUY_PUT") == "BEARISH"
    assert direction_family("PE") == "BEARISH"
    assert direction_family("NO_TRADE") == "NO_TRADE"
    assert direction_family("UNKNOWN") == "OTHER"


def test_balanced_directional_coverage_report_is_read_only():
    report = analyze_directional_balance([
        _score("call", direction="BUY_CALL", final_score=0.7),
        _score("put", direction="BUY_PUT", final_score=0.6),
    ])

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.coverage_state == "BALANCED_DIRECTIONAL_COVERAGE"
    assert report.bullish_count == 1
    assert report.bearish_count == 1
    assert report.imbalance_flags == ()
    assert report.recommendations == ("directional_coverage_ok_for_next_read_only_ranking_step",)
    assert report.metadata["scope"] == "read_only_no_execution_no_ranking"


def test_bullish_only_coverage_flags_missing_bearish_side():
    report = analyze_directional_balance([
        _score("call_a", direction="BUY_CALL", final_score=0.7),
        _score("call_b", direction="CE", final_score=0.5),
    ])

    assert report.coverage_state == "BULLISH_ONLY_COVERAGE"
    assert "missing_bearish_candidate_coverage" in report.imbalance_flags
    assert "no_score_eligible_bearish_candidates" in report.imbalance_flags
    assert "review_put_strategy_generation_and_option_confirmation_paths" in report.recommendations


def test_bearish_only_coverage_flags_missing_bullish_side():
    report = analyze_directional_balance([
        _score("put_a", direction="BUY_PUT", final_score=0.7),
        _score("put_b", direction="PE", final_score=0.5),
    ])

    assert report.coverage_state == "BEARISH_ONLY_COVERAGE"
    assert "missing_bullish_candidate_coverage" in report.imbalance_flags
    assert "no_score_eligible_bullish_candidates" in report.imbalance_flags
    assert "review_call_strategy_generation_and_option_confirmation_paths" in report.recommendations


def test_side_fully_suppressed_is_visible_before_ranking():
    report = analyze_directional_balance([
        _score("call", direction="BUY_CALL", final_score=0.7),
        _score(
            "put",
            direction="BUY_PUT",
            final_score=0.0,
            eligibility=SUPPRESSED_BY_DOWNGRADE,
            blockers=("FALLBACK_QUOTE_ONLY",),
            safety_flags=("fallback_data",),
        ),
    ])

    assert report.coverage_state == "BALANCED_DIRECTIONAL_COVERAGE"
    assert "bearish_side_fully_suppressed" in report.imbalance_flags
    assert "inspect_put_side_blockers_before_ranking" in report.recommendations
    assert "FALLBACK_QUOTE_ONLY" in report.blockers
    assert "fallback_data" in report.safety_flags


def test_score_concentration_flags_lopsided_directional_score_distribution():
    report = analyze_directional_balance([
        _score("call", direction="BUY_CALL", final_score=0.9),
        _score("put", direction="BUY_PUT", final_score=0.1),
    ])

    assert "bullish_score_concentration" in report.imbalance_flags
    assert "review_directional_score_concentration_before_final_ranking" in report.recommendations


def test_no_directional_coverage_is_detected():
    report = analyze_directional_balance([
        _score("nt", direction="NO_TRADE", final_score=0.0, eligibility=NO_TRADE_ONLY),
    ])

    assert report.coverage_state == "NO_DIRECTIONAL_COVERAGE"
    assert "missing_directional_candidate_coverage" in report.imbalance_flags
    assert "inspect_candidate_generation_before_scoring_or_ranking" in report.recommendations
    assert report.no_trade_count == 1


def test_other_only_coverage_is_detected():
    report = analyze_directional_balance([
        _score("x", direction="SIDEWAYS", final_score=0.2),
    ])

    assert report.coverage_state == "MIXED_WITH_OTHER_COVERAGE"
    assert report.other_count == 1
    assert "missing_directional_candidate_coverage" in report.imbalance_flags


def test_accepts_opportunity_score_report_and_keeps_source_scorer_metadata():
    source = _report([
        _score("call", direction="BUY_CALL", final_score=0.7),
        _score("put", direction="BUY_PUT", final_score=0.6),
    ])

    report = analyze_directional_balance(source)

    assert report.metadata["source_scorer"] == "opportunity_score_v1"
    assert report.score_count == 2


def test_family_summary_tracks_top_strategy_and_counts():
    report = analyze_directional_balance([
        _score("call_low", direction="BUY_CALL", final_score=0.2),
        _score("call_high", direction="BUY_CALL", final_score=0.8),
    ])

    bullish = next(summary for summary in report.family_summaries if summary.family == "BULLISH")
    assert bullish.score_count == 2
    assert bullish.top_strategy_id == "call_high"
    assert bullish.max_final_score == 0.8
    assert bullish.total_final_score == 1.0


def test_directional_balance_rejects_non_score_record_input():
    try:
        analyze_directional_balance([object()])
    except TypeError as exc:
        assert "directional_balance_expected_opportunity_score_record" in str(exc)
    else:
        raise AssertionError("directional balance accepted non-score input")


def test_directional_balance_report_is_json_serializable():
    report = analyze_directional_balance([
        _score("call", direction="BUY_CALL", final_score=0.7),
        _score("put", direction="BUY_PUT", final_score=0.6),
    ])

    payload = report.to_json()

    assert "directional_balance_v1" in payload
    assert "BALANCED_DIRECTIONAL_COVERAGE" in payload
