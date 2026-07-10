import json

from core.candidate_ranking import (
    RANKING_FEED_RISK_SAFETY_FLAG,
    RANKING_FEED_RISK_SUPPRESSION_REASON,
    rank_candidates,
)
from core.directional_balance import analyze_directional_balance
from core.opportunity_scoring import (
    ADVISORY_ONLY,
    NEEDS_CONFIRMATION,
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
    symbol="NIFTY",
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    final_score=0.5,
    eligibility=SCORE_ELIGIBLE,
    bucket=None,
    executable_candidate=None,
    downgrade_reasons=(),
    blockers=(),
    warnings=(),
    safety_flags=(),
    feed_risk_reasons=(),
    feed_risk_precomputed=False,
):
    if bucket is None:
        bucket = {
            SCORE_ELIGIBLE: "EXECUTABLE_CANDIDATE",
            NEEDS_CONFIRMATION: "NEAR_EXECUTABLE_CANDIDATE",
            ADVISORY_ONLY: "ADVISORY_CANDIDATE",
            SUPPRESSED_BY_DOWNGRADE: "SUPPRESSED_CANDIDATE",
            NO_TRADE_ONLY: "NO_TRADE_CANDIDATE",
        }[eligibility]
    if executable_candidate is None:
        executable_candidate = eligibility == SCORE_ELIGIBLE
    return OpportunityScoreRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        direction=direction,
        movement_type=movement_type,
        bucket=bucket,
        score_eligibility=eligibility,
        final_score=final_score,
        executable_candidate=executable_candidate,
        score_explanation="unit",
        downgrade_reasons=downgrade_reasons,
        safety_flags=safety_flags,
        blockers=blockers,
        warnings=warnings,
        feed_risk_reasons=feed_risk_reasons,
        feed_risk_precomputed=feed_risk_precomputed,
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
        needs_confirmation_count=sum(1 for item in scores if item.score_eligibility == NEEDS_CONFIRMATION),
        advisory_count=sum(1 for item in scores if item.score_eligibility == ADVISORY_ONLY),
        suppressed_count=sum(1 for item in scores if item.score_eligibility == SUPPRESSED_BY_DOWNGRADE),
        no_trade_count=sum(1 for item in scores if item.score_eligibility == NO_TRADE_ONLY),
        scores=tuple(scores),
        blockers=tuple(sorted(set(blocker for item in scores for blocker in item.blockers))),
        warnings=tuple(sorted(set(warning for item in scores for warning in item.warnings))),
        safety_flags=tuple(sorted(set(flag for item in scores for flag in item.safety_flags))),
        metadata={"scorer": "opportunity_score_v1"},
    )


def test_ranking_report_is_read_only_and_preserves_source_metadata():
    score_report = _report([_score("clean", final_score=0.7)])

    report = rank_candidates(score_report)

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.rank_count == 1
    assert report.ranks[0].rank == 1
    assert report.metadata["ranker"] == "candidate_ranking_v1"
    assert report.metadata["scope"] == "read_only_no_execution_no_score_mutation"
    assert report.metadata["source_scorer"] == "opportunity_score_v1"
    assert report.metadata["feed_risk_suppression"] == "enabled"


def test_executable_candidates_rank_above_higher_scored_suppressed_candidates():
    executable = _score("exec", final_score=0.52, eligibility=SCORE_ELIGIBLE)
    suppressed = _score(
        "suppressed",
        final_score=0.99,
        eligibility=SUPPRESSED_BY_DOWNGRADE,
        downgrade_reasons=("fallback_quote_data",),
        blockers=("FALLBACK_QUOTE_ONLY",),
        safety_flags=("fallback_data",),
    )

    report = rank_candidates([suppressed, executable])

    assert [rank.strategy_id for rank in report.ranks] == ["exec", "suppressed"]
    assert report.ranks[0].score_eligibility == SCORE_ELIGIBLE
    assert report.ranks[1].score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert "FALLBACK_QUOTE_ONLY" in report.blockers
    assert "fallback_data" in report.safety_flags


def test_near_executable_stays_above_advisory_suppressed_and_no_trade():
    rows = [
        _score("no_trade", direction="NO_TRADE", final_score=0.0, eligibility=NO_TRADE_ONLY),
        _score("suppressed", final_score=0.05, eligibility=SUPPRESSED_BY_DOWNGRADE),
        _score("advisory", final_score=0.35, eligibility=ADVISORY_ONLY),
        _score("near", final_score=0.20, eligibility=NEEDS_CONFIRMATION),
    ]

    report = rank_candidates(rows)

    assert [rank.strategy_id for rank in report.ranks] == ["near", "advisory", "suppressed", "no_trade"]
    assert report.near_executable_count == 1
    assert report.advisory_count == 1
    assert report.suppressed_count == 1
    assert report.no_trade_count == 1


def test_scores_sort_descending_within_same_eligibility_and_safety_state():
    low = _score("low", final_score=0.51)
    high = _score("high", final_score=0.91)
    mid = _score("mid", final_score=0.72)

    report = rank_candidates([low, high, mid])

    assert [rank.strategy_id for rank in report.ranks] == ["high", "mid", "low"]
    assert [rank.rank for rank in report.ranks] == [1, 2, 3]


def test_safety_state_orders_equally_eligible_candidates_before_score():
    clean = _score("clean", final_score=0.51, eligibility=NEEDS_CONFIRMATION)
    risky = _score(
        "risky",
        final_score=0.65,
        eligibility=NEEDS_CONFIRMATION,
        downgrade_reasons=("wide_spread",),
        blockers=("WIDE_SPREAD",),
        safety_flags=("wide_spread",),
    )

    report = rank_candidates([risky, clean])

    assert [rank.strategy_id for rank in report.ranks] == ["clean", "risky"]
    assert report.ranks[1].score_eligibility == NEEDS_CONFIRMATION
    assert "safety_flags=1" in report.ranks[1].rank_reason


def test_feed_risky_executable_candidate_is_suppressed_even_with_high_score():
    clean = _score("clean", final_score=0.55, eligibility=SCORE_ELIGIBLE)
    risky = _score(
        "risky_feed",
        final_score=0.99,
        eligibility=SCORE_ELIGIBLE,
        warnings=("NO_LIVE_OPTION_FEED",),
    )

    report = rank_candidates([risky, clean])

    assert [rank.strategy_id for rank in report.ranks] == ["clean", "risky_feed"]
    assert report.executable_count == 1
    assert report.suppressed_count == 1
    risky_rank = report.ranks[1]
    assert risky_rank.score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert risky_rank.bucket == "SUPPRESSED_CANDIDATE"
    assert risky_rank.executable_candidate is False
    assert RANKING_FEED_RISK_SUPPRESSION_REASON in risky_rank.downgrade_reasons
    assert RANKING_FEED_RISK_SAFETY_FLAG in risky_rank.safety_flags
    assert "feed_risk_suppressed=true" in risky_rank.rank_reason
    assert report.metadata["feed_risk_suppressed_count"] == 1


def test_feed_risky_near_executable_candidate_is_suppressed_before_advisory():
    advisory = _score("advisory", final_score=0.35, eligibility=ADVISORY_ONLY)
    near_feed_risk = _score(
        "near_feed_risk",
        final_score=0.65,
        eligibility=NEEDS_CONFIRMATION,
        safety_flags=("stale_feed",),
    )

    report = rank_candidates([near_feed_risk, advisory])

    assert [rank.strategy_id for rank in report.ranks] == ["advisory", "near_feed_risk"]
    assert report.near_executable_count == 0
    assert report.advisory_count == 1
    assert report.suppressed_count == 1
    assert report.ranks[1].score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert RANKING_FEED_RISK_SUPPRESSION_REASON in report.ranks[1].downgrade_reasons


def test_iv_surface_slope_warning_is_treated_as_feed_risk_for_ranking():
    risky = _score(
        "iv_surface",
        final_score=0.88,
        eligibility=SCORE_ELIGIBLE,
        warnings=("low_iv_surface_confidence",),
    )

    report = rank_candidates([risky])

    assert report.suppressed_count == 1
    assert report.ranks[0].score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert report.ranks[0].bucket == "SUPPRESSED_CANDIDATE"
    assert report.ranks[0].executable_candidate is False
    assert RANKING_FEED_RISK_SUPPRESSION_REASON in report.ranks[0].downgrade_reasons


def test_iv_surface_slope_blocker_is_treated_as_feed_risk_for_ranking():
    risky = _score(
        "iv_surface_blocker",
        final_score=0.88,
        eligibility=SCORE_ELIGIBLE,
        blockers=("IV_SURFACE_SLOPE",),
    )

    report = rank_candidates([risky])

    assert report.suppressed_count == 1
    assert report.ranks[0].score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert report.ranks[0].bucket == "SUPPRESSED_CANDIDATE"
    assert report.ranks[0].executable_candidate is False
    assert RANKING_FEED_RISK_SUPPRESSION_REASON in report.ranks[0].downgrade_reasons


def test_feed_risk_suppression_does_not_mutate_source_score_record():
    risky = _score(
        "risky_source",
        final_score=0.99,
        eligibility=SCORE_ELIGIBLE,
        blockers=("SUBSCRIPTION_FAILED",),
    )

    report = rank_candidates([risky])

    assert risky.score_eligibility == SCORE_ELIGIBLE
    assert risky.bucket == "EXECUTABLE_CANDIDATE"
    assert risky.executable_candidate is True
    assert report.ranks[0].score_eligibility == SUPPRESSED_BY_DOWNGRADE
    assert report.ranks[0].bucket == "SUPPRESSED_CANDIDATE"
    assert report.ranks[0].executable_candidate is False


def test_advisory_feed_risk_stays_advisory_not_double_suppressed():
    advisory = _score(
        "advisory_feed_risk",
        final_score=0.35,
        eligibility=ADVISORY_ONLY,
        safety_flags=("fallback_data",),
    )

    report = rank_candidates([advisory])

    assert report.advisory_count == 1
    assert report.suppressed_count == 0
    assert report.ranks[0].score_eligibility == ADVISORY_ONLY
    assert RANKING_FEED_RISK_SUPPRESSION_REASON not in report.ranks[0].downgrade_reasons


def test_ranker_uses_precomputed_feed_risk_verdict_without_rescanning(monkeypatch):
    record = _score(
        "precomputed_risk",
        final_score=0.88,
        eligibility=SCORE_ELIGIBLE,
        feed_risk_reasons=("stale_feed",),
        feed_risk_precomputed=True,
    )

    def _should_not_run(*args, **kwargs):
        raise AssertionError("feed-risk rescanning should not run when verdict is already on the score record")

    monkeypatch.setattr("core.candidate_ranking.is_feed_risk_candidate", _should_not_run)

    report = rank_candidates([record])

    assert report.ranks[0].bucket == "SUPPRESSED_CANDIDATE"
    assert RANKING_FEED_RISK_SUPPRESSION_REASON in report.ranks[0].downgrade_reasons
    assert RANKING_FEED_RISK_SAFETY_FLAG in report.ranks[0].safety_flags


def test_deterministic_tie_breakers_do_not_depend_on_input_order():
    a = _score("a_strategy", symbol="BANKNIFTY", direction="BUY_CALL", movement_type="TREND_PULLBACK", final_score=0.5)
    b = _score("b_strategy", symbol="NIFTY", direction="BUY_CALL", movement_type="TREND_PULLBACK", final_score=0.5)
    c = _score("c_strategy", symbol="NIFTY", direction="BUY_PUT", movement_type="TREND_PULLBACK", final_score=0.5)

    first = rank_candidates([c, b, a])
    second = rank_candidates([a, c, b])

    assert [rank.strategy_id for rank in first.ranks] == [rank.strategy_id for rank in second.ranks]
    assert [rank.strategy_id for rank in first.ranks] == ["a_strategy", "b_strategy", "c_strategy"]


def test_directional_balance_warnings_are_attached_without_creating_opposite_side_candidate():
    score_report = _report([
        _score("call_a", direction="BUY_CALL", final_score=0.8),
        _score("call_b", direction="CE", final_score=0.6),
    ])
    balance = analyze_directional_balance(score_report)

    report = rank_candidates(score_report, balance)

    assert report.rank_count == 2
    assert report.directional_imbalance_flags == balance.imbalance_flags
    assert "missing_bearish_candidate_coverage" in report.directional_imbalance_flags
    assert all(rank.directional_family == "BULLISH" for rank in report.ranks)
    assert all("directional_balance_missing_bearish_candidate_coverage" in rank.directional_warnings for rank in report.ranks)
    assert not any(rank.directional_family == "BEARISH" for rank in report.ranks)


def test_directional_family_and_evidence_are_emitted_per_rank():
    record = _score(
        "put",
        direction="BUY_PUT",
        final_score=0.44,
        eligibility=ADVISORY_ONLY,
        downgrade_reasons=("weak_option_confirmation",),
        blockers=("WEAK_OPTION_CONFIRMATION",),
        warnings=("needs_confirmation",),
        safety_flags=("weak_option_confirmation",),
    )

    report = rank_candidates([record])
    rank = report.ranks[0]

    assert rank.directional_family == "BEARISH"
    assert rank.downgrade_reasons == ("weak_option_confirmation",)
    assert rank.blockers == ("WEAK_OPTION_CONFIRMATION",)
    assert rank.warnings == ("needs_confirmation",)
    assert rank.safety_flags == ("weak_option_confirmation",)
    assert "family=BEARISH" in rank.rank_reason


def test_missing_data_safe_empty_input():
    report = rank_candidates([])

    assert report.rank_count == 0
    assert report.ranks == ()
    assert report.blockers == ()
    assert report.warnings == ()
    assert report.safety_flags == ()
    assert report.metadata["feed_risk_suppressed_count"] == 0


def test_ranking_rejects_non_score_record_input():
    try:
        rank_candidates([object()])
    except TypeError as exc:
        assert "candidate_ranking_expected_opportunity_score_record" in str(exc)
    else:
        raise AssertionError("ranking accepted non-score input")


def test_ranking_rejects_invalid_directional_balance_input():
    try:
        rank_candidates([], object())
    except TypeError as exc:
        assert "candidate_ranking_expected_directional_balance_report" in str(exc)
    else:
        raise AssertionError("ranking accepted invalid directional balance input")


def test_ranking_report_is_json_serializable():
    report = rank_candidates([_score("clean", final_score=0.7)])
    payload = report.to_json()

    assert "candidate_ranking_v1" in payload
    assert "read_only_no_execution_no_score_mutation" in payload
    assert "feed_risk_suppression" in payload
    json.loads(payload)
