from __future__ import annotations

import json

from core.feed_health_truth import classify_feed_health_truth
from core.feed_recovery_warmup_gate import (
    FEED_RECOVERY_WARMUP_BLOCKER,
    apply_feed_recovery_warmup_to_ranking,
    classify_feed_recovery_warmup,
)
from core.opportunity_scoring import SCORE_ELIGIBLE, OpportunityScoreBreakdown, OpportunityScoreRecord, OpportunityScoreReport

# feed recovery safety regression coverage: recovered feed must warm up before executable ranking resumes.


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


def test_feed_recovery_warmup_decision_is_read_only_and_non_action():
    warmup = classify_feed_recovery_warmup(
        _healthy_feed(),
        previous_feed_ok=False,
        recovered_at_epoch=100.0,
        now_epoch=102.0,
        healthy_sample_count=1,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )

    assert warmup.read_only is True
    assert warmup.is_order_action is False
    assert warmup.append is False
    assert warmup.feed_recovered is True
    assert warmup.warmup_required is True
    assert warmup.warmup_active is True
    assert FEED_RECOVERY_WARMUP_BLOCKER in warmup.blockers
    assert warmup.feed_health_truth["feed_ok"] is True


def test_feed_recovery_warmup_suppresses_ranking_until_elapsed_and_samples_are_satisfied():
    score_report = _report([_score("a", 0.9), _score("b", 0.8)])

    ranking = apply_feed_recovery_warmup_to_ranking(
        score_report,
        _healthy_feed(),
        previous_feed_ok=False,
        recovered_at_epoch=100.0,
        now_epoch=103.0,
        healthy_sample_count=1,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )

    assert ranking.read_only is True
    assert ranking.is_order_action is False
    assert ranking.append is False
    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert ranking.ranks == ()
    assert FEED_RECOVERY_WARMUP_BLOCKER in ranking.blockers
    assert "warmup_elapsed_sec_below_minimum" in ranking.blockers
    assert "healthy_sample_count_below_minimum" in ranking.blockers
    assert ranking.safety_flags == (FEED_RECOVERY_WARMUP_BLOCKER,)
    assert ranking.metadata["feed_recovery_warmup_active"] is True
    assert ranking.metadata["source_score_count"] == 2


def test_feed_recovery_warmup_allows_ranking_after_elapsed_and_samples_are_satisfied():
    score_report = _report([_score("low", 0.5), _score("high", 0.9)])

    ranking = apply_feed_recovery_warmup_to_ranking(
        score_report,
        _healthy_feed(),
        previous_feed_ok=False,
        recovered_at_epoch=100.0,
        now_epoch=106.0,
        healthy_sample_count=2,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )

    assert ranking.rank_count == 2
    assert ranking.executable_count == 2
    assert [rank.strategy_id for rank in ranking.ranks] == ["high", "low"]
    assert FEED_RECOVERY_WARMUP_BLOCKER not in ranking.blockers


def test_feed_recovery_warmup_missing_recovery_timestamp_fails_closed_when_recovered():
    score_report = _report([_score("candidate", 0.9)])

    ranking = apply_feed_recovery_warmup_to_ranking(
        score_report,
        _healthy_feed(),
        previous_feed_ok=False,
        recovered_at_epoch=None,
        now_epoch=106.0,
        healthy_sample_count=3,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert FEED_RECOVERY_WARMUP_BLOCKER in ranking.blockers
    assert "recovered_at_missing" in ranking.blockers


def test_feed_recovery_warmup_unhealthy_feed_fails_closed():
    score_report = _report([_score("candidate", 0.9)])

    ranking = apply_feed_recovery_warmup_to_ranking(
        score_report,
        _unhealthy_feed(),
        previous_feed_ok=False,
        recovered_at_epoch=100.0,
        now_epoch=106.0,
        healthy_sample_count=3,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert FEED_RECOVERY_WARMUP_BLOCKER in ranking.blockers
    assert "websocket_disconnected" in ranking.blockers


def test_feed_recovery_warmup_currently_healthy_without_recovery_context_preserves_ranking_with_warning():
    score_report = _report([_score("low", 0.5), _score("high", 0.9)])

    ranking = apply_feed_recovery_warmup_to_ranking(
        score_report,
        _healthy_feed(),
        previous_feed_ok=None,
        recovered_at_epoch=None,
        now_epoch=106.0,
        healthy_sample_count=0,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )

    assert ranking.rank_count == 2
    assert [rank.strategy_id for rank in ranking.ranks] == ["high", "low"]


def test_feed_recovery_warmup_report_is_json_serializable():
    warmup = classify_feed_recovery_warmup(
        _healthy_feed(),
        previous_feed_ok=False,
        recovered_at_epoch=100.0,
        now_epoch=102.0,
        healthy_sample_count=1,
        min_warmup_sec=5.0,
        min_healthy_samples=2,
    )
    payload = json.loads(warmup.to_json())

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["warmup_active"] is True
    assert payload["metadata"]["gate"] == "feed_recovery_warmup_gate_v1"
