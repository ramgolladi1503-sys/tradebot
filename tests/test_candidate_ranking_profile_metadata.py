from core.candidate_ranking import rank_candidates
from core.opportunity_scoring import (
    COMPONENT_WEIGHTS,
    SCORE_ELIGIBLE,
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)


PROFILE_WEIGHTS = {
    "confluence": 0.09,
    "freshness": 0.13,
    "liquidity": 0.12,
    "option_confirmation": 0.16,
    "price_structure": 0.22,
    "regime_alignment": 0.18,
    "timing": 0.06,
    "volatility": 0.04,
}


def _breakdown(final_score=0.5):
    return OpportunityScoreBreakdown(
        component_scores={},
        component_weights=PROFILE_WEIGHTS,
        weighted_component_scores={},
        base_score=final_score,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=final_score,
    )


def _score(strategy_id, final_score):
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="COMPRESSION_BREAKOUT",
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility=SCORE_ELIGIBLE,
        final_score=final_score,
        executable_candidate=True,
        score_explanation="unit",
        downgrade_reasons=(),
        safety_flags=(),
        blockers=(),
        warnings=(),
        breakdown=_breakdown(final_score),
    )


def _profile_score_report(scores):
    return OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=len(scores),
        score_eligible_count=len(scores),
        needs_confirmation_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        scores=tuple(scores),
        blockers=(),
        warnings=(),
        safety_flags=(),
        metadata={
            "scorer": "opportunity_score_v1",
            "component_weights": PROFILE_WEIGHTS,
            "base_component_weights": COMPONENT_WEIGHTS,
            "scoring_profile_applied": True,
            "scoring_profile_name": "TREND_UP",
        },
    )


def test_ranking_propagates_profile_scoring_metadata_without_sort_cutover():
    low = _score("low", 0.40)
    high = _score("high", 0.90)
    report = rank_candidates(_profile_score_report([low, high]))

    assert [rank.strategy_id for rank in report.ranks] == ["high", "low"]
    assert report.metadata["ranking_sort_score_source"] == "opportunity_final_score"
    assert report.metadata["profile_sort_cutover_enabled"] is False
    assert report.metadata["source_scorer"] == "opportunity_score_v1"
    assert report.metadata["source_scoring_profile_applied"] is True
    assert report.metadata["source_scoring_profile_name"] == "TREND_UP"
    assert report.metadata["source_component_weights"] == PROFILE_WEIGHTS
    assert report.metadata["source_base_component_weights"] == COMPONENT_WEIGHTS


def test_ranking_metadata_defaults_when_scores_are_plain_iterable():
    report = rank_candidates([_score("plain", 0.70)])

    assert report.metadata["source_scorer"] is None
    assert report.metadata["source_scoring_profile_applied"] is False
    assert report.metadata["source_scoring_profile_name"] is None
    assert report.metadata["source_component_weights"] == {}
    assert report.metadata["source_base_component_weights"] == {}
    assert report.metadata["profile_sort_cutover_enabled"] is False
