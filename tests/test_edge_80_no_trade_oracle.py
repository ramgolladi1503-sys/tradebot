"""EDGE-80 NoTradeOracle tests."""

from __future__ import annotations

from core.candidate_ranking import CandidateRankingReport
from core.feed_health_truth import classify_feed_health_truth
from core.live_indicator_readiness import build_live_indicator_readiness_report
from core.market_close_feed_state import MARKET_CLOSED, classify_market_close_feed_state
from core.no_trade_oracle import (
    EXECUTABLE_TRUTH_BLOCKED_REASON,
    FEED_HEALTH_BLOCKED_REASON,
    FEED_HOLD_ACTIVE_REASON,
    INDICATOR_READINESS_BLOCKED_REASON,
    MARKET_FEED_STATE_BLOCKED_REASON,
    MISSING_EVIDENCE_REASON,
    NO_EXECUTABLE_RANKS_REASON,
    NO_SCORED_CANDIDATES_REASON,
    NO_SCORE_ELIGIBLE_CANDIDATES_REASON,
    NO_TRADE_REQUIRED,
    TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE,
    build_no_trade_oracle_report,
)
from core.opportunity_scoring import OpportunityScoreReport


def test_missing_evidence_fails_closed_without_side_effect_markers():
    report = build_no_trade_oracle_report(now_epoch=1_000.0)
    payload = report.to_payload()

    assert report.status == NO_TRADE_REQUIRED
    assert report.no_trade_required is True
    assert report.primary_reason == MISSING_EVIDENCE_REASON
    assert MISSING_EVIDENCE_REASON in report.blockers
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_unhealthy_feed_truth_and_feed_hold_are_explained():
    feed_health = classify_feed_health_truth(
        {
            "feed_ok": False,
            "ws_connected": False,
            "last_tick_age_sec": 9.0,
        },
        max_ltp_age_sec=2.5,
    )

    report = build_no_trade_oracle_report(feed_health=feed_health, now_epoch=1_000.0)

    assert report.status == NO_TRADE_REQUIRED
    assert report.primary_reason == FEED_HEALTH_BLOCKED_REASON
    assert FEED_HEALTH_BLOCKED_REASON in report.blockers
    assert FEED_HOLD_ACTIVE_REASON in report.blockers
    assert "feed_health_truth" in report.evidence_sources
    assert "feed_hold_gate" in report.evidence_sources


def test_market_closed_precedes_other_no_trade_reasons():
    market_state = classify_market_close_feed_state(
        {
            "market_state": "CLOSED",
            "ws_connected": True,
            "ltp_age_sec": 99.0,
            "option_feed_age_sec": 99.0,
            "cycle_latency_sec": 99.0,
        },
        now_epoch=1_000.0,
    )
    indicator_report = build_live_indicator_readiness_report((), now_epoch=1_000.0)

    report = build_no_trade_oracle_report(
        market_close_feed_state=market_state,
        indicator_readiness=indicator_report,
        now_epoch=1_000.0,
    )
    payload = report.to_payload()

    assert report.status == NO_TRADE_REQUIRED
    assert report.primary_reason == MARKET_FEED_STATE_BLOCKED_REASON
    assert payload["reasons"][0]["evidence"]["state"] == MARKET_CLOSED
    assert INDICATOR_READINESS_BLOCKED_REASON in report.blockers


def test_indicator_readiness_blocks_live_price_without_ready_indicators():
    indicator_report = build_live_indicator_readiness_report(
        (
            {
                "symbol": "NIFTY",
                "ohlc_bars_count": 0,
                "vwap": None,
                "rsi": None,
                "ema": None,
                "atr": None,
            },
        ),
        now_epoch=1_000.0,
    )

    report = build_no_trade_oracle_report(indicator_readiness=indicator_report, now_epoch=1_000.0)
    reason = next(item for item in report.reasons if item.reason_code == INDICATOR_READINESS_BLOCKED_REASON)

    assert report.no_trade_required is True
    assert reason.evidence["blocked_count"] == 1
    assert reason.evidence["blocked_decisions"][0]["symbol"] == "NIFTY"
    assert reason.evidence["blocked_decisions"][0]["indicator_missing_inputs"] == ["vwap", "rsi", "ema", "atr"]


def test_scoring_with_zero_scores_and_no_eligible_scores_blocks_promotion():
    empty_scoring = OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=0,
        score_eligible_count=0,
        needs_confirmation_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        scores=(),
        blockers=(),
        warnings=(),
        safety_flags=(),
    )
    advisory_scoring_payload = {
        "score_count": 2,
        "score_eligible_count": 0,
        "advisory_count": 1,
        "suppressed_count": 1,
        "no_trade_count": 0,
        "blockers": ["weak_option_confirmation"],
        "safety_flags": ["fallback_data"],
    }

    empty_report = build_no_trade_oracle_report(scoring=empty_scoring, now_epoch=1_000.0)
    advisory_report = build_no_trade_oracle_report(scoring=advisory_scoring_payload, now_epoch=1_000.0)

    assert empty_report.primary_reason == NO_SCORED_CANDIDATES_REASON
    assert NO_SCORE_ELIGIBLE_CANDIDATES_REASON in advisory_report.blockers


def test_ranking_with_no_executable_ranks_blocks_promotion():
    ranking = CandidateRankingReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        rank_count=3,
        executable_count=0,
        near_executable_count=1,
        advisory_count=1,
        suppressed_count=1,
        no_trade_count=0,
        ranks=(),
        blockers=("feed_health_hold",),
        warnings=(),
        safety_flags=("ranking_feed_risk",),
        directional_imbalance_flags=(),
    )

    report = build_no_trade_oracle_report(ranking=ranking, now_epoch=1_000.0)
    reason = next(item for item in report.reasons if item.reason_code == NO_EXECUTABLE_RANKS_REASON)

    assert report.status == NO_TRADE_REQUIRED
    assert reason.evidence["rank_count"] == 3
    assert reason.evidence["near_executable_count"] == 1
    assert reason.evidence["safety_flags"] == ["ranking_feed_risk"]


def test_executable_truth_blocks_when_all_supplied_candidates_are_blocked():
    report = build_no_trade_oracle_report(
        executable_truths=(
            {"execution_allowed": False, "reason_code": "fallback_driven_data", "reasons": ["fallback_driven_data"]},
            {"execution_allowed": False, "reason_code": "stale_option_ltp", "reasons": ["stale_option_ltp"]},
        ),
        now_epoch=1_000.0,
    )
    reason = next(item for item in report.reasons if item.reason_code == EXECUTABLE_TRUTH_BLOCKED_REASON)

    assert report.no_trade_required is True
    assert reason.evidence["blocked_count"] == 2
    assert reason.evidence["allowed_count"] == 0
    assert reason.evidence["blocked_reasons"] == ["fallback_driven_data", "stale_option_ltp"]


def test_clean_supplied_evidence_allows_trade_without_runtime_action():
    feed_health = classify_feed_health_truth({"feed_ok": True, "ws_connected": True}, max_ltp_age_sec=2.5)
    market_state = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 0.5,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.1,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
    )
    indicators = build_live_indicator_readiness_report(
        (
            {
                "symbol": "NIFTY",
                "ohlc_bars_count": 60,
                "indicator_last_update_epoch": 990.0,
                "vwap": 100.0,
                "rsi": 55.0,
                "ema": 101.0,
                "atr": 12.0,
            },
        ),
        now_epoch=1_000.0,
    )
    scoring = {"score_count": 1, "score_eligible_count": 1}
    ranking = {"rank_count": 1, "executable_count": 1}

    report = build_no_trade_oracle_report(
        feed_health=feed_health,
        market_close_feed_state=market_state,
        indicator_readiness=indicators,
        scoring=scoring,
        ranking=ranking,
        executable_truths=({"execution_allowed": True, "reason_code": "ok", "reasons": []},),
        now_epoch=1_000.0,
    )
    payload = report.to_payload()

    assert report.status == TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE
    assert report.no_trade_required is False
    assert report.primary_reason == "no_no_trade_blockers"
    assert payload["reason_count"] == 0
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
