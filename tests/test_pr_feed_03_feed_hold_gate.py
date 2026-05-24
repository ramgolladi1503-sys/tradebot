from __future__ import annotations

import json

from core.feed_health_truth import classify_feed_health_truth
from core.feed_hold_gate import FEED_HOLD_BLOCKER, apply_feed_hold_to_ranking, classify_feed_hold
from core.opportunity_scoring import SCORE_ELIGIBLE, OpportunityScoreBreakdown, OpportunityScoreRecord, OpportunityScoreReport

# stale_feed safety regression coverage: unsafe feed truth cannot produce executable rankings.


def _breakdown(final_score: float = 0.7) -> OpportunityScoreBreakdown:
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


def _score(strategy_id: str = "s1", final_score: float = 0.7) -> OpportunityScoreRecord:
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


def _report(scores: list[OpportunityScoreRecord]) -> OpportunityScoreReport:
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
        metadata={"scorer": "opportunity_score_v1"},
    )


def _healthy_feed():
    return classify_feed_health_truth(
        {
            "feed_ok": True,
            "effective_ws_connected": True,
            "runtime_state": "RUNNING",
            "state_machine": {"state": "LIVE"},
            "last_tick_age_sec": 0.4,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "option_last_tick_age_by_symbol": {"NIFTY": 0.2},
        },
        symbols=("NIFTY",),
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )


def _unhealthy_feed():
    return classify_feed_health_truth(
        {
            "feed_ok": True,
            "effective_ws_connected": False,
            "runtime_state": "RUNNING",
            "state_machine": {"state": "DOWN"},
            "last_tick_age_sec": 0.4,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {"NIFTY": "SUBSCRIPTION_FAILED"},
            "option_last_tick_age_by_symbol": {"NIFTY": 0.2},
        },
        symbols=("NIFTY",),
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )


def test_stale_feed_hold_decision_is_read_only_and_non_action():
    hold = classify_feed_hold(_unhealthy_feed())

    assert hold.read_only is True
    assert hold.is_order_action is False
    assert hold.append is False
    assert hold.hold_active is True
    assert FEED_HOLD_BLOCKER in hold.blockers
    assert hold.feed_health_truth["feed_ok"] is False


def test_stale_feed_unhealthy_feed_truth_suppresses_all_executable_ranks():
    score_report = _report([_score("a", 0.9), _score("b", 0.8)])

    ranking = apply_feed_hold_to_ranking(score_report, _unhealthy_feed())

    assert ranking.read_only is True
    assert ranking.is_order_action is False
    assert ranking.append is False
    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert ranking.ranks == ()
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert ranking.safety_flags == (FEED_HOLD_BLOCKER,)
    assert ranking.metadata["feed_hold_active"] is True
    assert ranking.metadata["source_score_count"] == 2


def test_stale_feed_healthy_feed_truth_preserves_normal_ranking_order():
    score_report = _report([_score("low", 0.5), _score("high", 0.9)])

    ranking = apply_feed_hold_to_ranking(score_report, _healthy_feed())

    assert ranking.rank_count == 2
    assert ranking.executable_count == 2
    assert [rank.strategy_id for rank in ranking.ranks] == ["high", "low"]
    assert FEED_HOLD_BLOCKER not in ranking.blockers


def test_stale_feed_invalid_feed_truth_fails_closed():
    score_report = _report([_score("candidate", 0.9)])

    ranking = apply_feed_hold_to_ranking(score_report, None)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "invalid_payload" in ranking.blockers


def test_stale_feed_hold_report_is_json_serializable():
    hold = classify_feed_hold(_unhealthy_feed())
    payload = json.loads(hold.to_json())

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["hold_active"] is True
    assert payload["metadata"]["gate"] == "feed_hold_gate_v1"
