from __future__ import annotations

from core.final_executable_quality_gate import (
    EXECUTABLE_TRUTH_BLOCKED_REASON,
    EXECUTABLE_TRUTH_MISSING_REASON,
    EXECUTABLE_TRUTH_UNKNOWN_REASON,
    FINAL_EXECUTABLE_QUALITY_BLOCKED,
    FINAL_EXECUTABLE_QUALITY_PASSED,
    MISSING_GATE_EVIDENCE_REASON,
    NO_EXECUTABLE_RANK_REASON,
    NO_TRADE_REQUIRED_REASON,
    RANKING_SAFETY_BLOCK_REASON,
    build_final_executable_quality_report,
)

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


def _clear_no_trade() -> dict[str, object]:
    return {
        "status": "TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE",
        "no_trade_required": False,
        "primary_reason": "no_no_trade_blockers",
        "blockers": [],
    }


def _blocked_no_trade() -> dict[str, object]:
    return {
        "status": "NO_TRADE_REQUIRED",
        "no_trade_required": True,
        "primary_reason": "feed_hold_active",
        "blockers": ["feed_hold_active"],
    }


def _ranking_with_executable() -> dict[str, object]:
    return {
        "rank_count": 1,
        "executable_count": 1,
        "near_executable_count": 0,
        "blockers": [],
        "safety_flags": [],
        "ranks": [
            {
                "rank": 1,
                "candidate_id": "cand-1",
                "strategy_id": "breakout_v1",
                "symbol": "NIFTY",
                "direction": "BUY",
                "movement_type": "breakout",
                "final_score": 0.91,
                "bucket": "EXECUTABLE_CANDIDATE",
                "score_eligibility": "SCORE_ELIGIBLE",
                "executable_candidate": True,
                "blockers": [],
                "safety_flags": [],
                "downgrade_reasons": [],
            }
        ],
    }


def _ranking_without_executable() -> dict[str, object]:
    return {
        "rank_count": 1,
        "executable_count": 0,
        "near_executable_count": 1,
        "blockers": [],
        "safety_flags": [],
        "ranks": [
            {
                "rank": 1,
                "candidate_id": "cand-2",
                "strategy_id": "vwap_v1",
                "symbol": "BANKNIFTY",
                "direction": "BUY",
                "movement_type": "pullback",
                "final_score": 0.72,
                "bucket": "NEAR_EXECUTABLE_CANDIDATE",
                "score_eligibility": "NEEDS_CONFIRMATION",
                "executable_candidate": False,
                "blockers": [],
                "safety_flags": [],
                "downgrade_reasons": [],
            }
        ],
    }


def _ranking_with_unsafe_executable() -> dict[str, object]:
    ranking = _ranking_with_executable()
    rank = ranking["ranks"][0]
    rank["safety_flags"] = ["wide_spread"]
    return ranking


def _allowed_truth() -> dict[str, object]:
    return {
        "candidate_id": "cand-1",
        "strategy_id": "breakout_v1",
        "symbol": "NIFTY",
        "direction": "BUY",
        "movement_type": "breakout",
        "execution_allowed": True,
        "reason_code": "ok",
        "reasons": [],
    }


def _blocked_truth() -> dict[str, object]:
    truth = _allowed_truth()
    truth.update(
        {
            "execution_allowed": False,
            "reason_code": "stale_option_ltp",
            "reasons": ["stale_option_ltp"],
        }
    )
    return truth


def test_final_quality_gate_fails_closed_without_required_evidence():
    report = build_final_executable_quality_report()
    payload = report.to_payload()

    assert payload["status"] == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert payload["executable_quality_passed"] is False
    assert payload["primary_reason"] == MISSING_GATE_EVIDENCE_REASON
    assert payload[_ACTION_KEY] is False
    assert payload[_BROKER_KEY] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_final_quality_gate_blocks_when_no_trade_oracle_blocks():
    report = build_final_executable_quality_report(
        no_trade=_blocked_no_trade(),
        ranking=_ranking_with_executable(),
        executable_truths=[_allowed_truth()],
    )

    assert report.status == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert report.primary_reason == NO_TRADE_REQUIRED_REASON
    assert [blocker.reason_code for blocker in report.blockers] == [NO_TRADE_REQUIRED_REASON]


def test_final_quality_gate_blocks_when_ranking_has_no_executable_candidate():
    report = build_final_executable_quality_report(
        no_trade=_clear_no_trade(),
        ranking=_ranking_without_executable(),
        executable_truths=[_allowed_truth()],
    )

    assert report.status == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert report.primary_reason == NO_EXECUTABLE_RANK_REASON


def test_final_quality_gate_blocks_when_selected_rank_has_safety_evidence():
    report = build_final_executable_quality_report(
        no_trade=_clear_no_trade(),
        ranking=_ranking_with_unsafe_executable(),
        executable_truths=[_allowed_truth()],
    )

    assert report.status == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert report.primary_reason == RANKING_SAFETY_BLOCK_REASON
    assert report.blockers[0].evidence["rank_blockers"] == ["wide_spread"]


def test_final_quality_gate_requires_executable_truth():
    report = build_final_executable_quality_report(
        no_trade=_clear_no_trade(),
        ranking=_ranking_with_executable(),
        executable_truths=[],
    )

    assert report.status == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert report.primary_reason == EXECUTABLE_TRUTH_MISSING_REASON


def test_final_quality_gate_blocks_when_truth_for_selected_candidate_is_blocked():
    report = build_final_executable_quality_report(
        no_trade=_clear_no_trade(),
        ranking=_ranking_with_executable(),
        executable_truths=[_blocked_truth()],
    )

    assert report.status == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert report.primary_reason == EXECUTABLE_TRUTH_BLOCKED_REASON
    assert report.blockers[0].evidence["reasons"] == ["stale_option_ltp"]


def test_final_quality_gate_blocks_when_truth_cannot_match_selected_candidate():
    truth = _allowed_truth()
    truth["candidate_id"] = "different-candidate"

    report = build_final_executable_quality_report(
        no_trade=_clear_no_trade(),
        ranking=_ranking_with_executable(),
        executable_truths=[truth, _allowed_truth() | {"candidate_id": "other"}],
    )

    assert report.status == FINAL_EXECUTABLE_QUALITY_BLOCKED
    assert report.primary_reason == EXECUTABLE_TRUTH_UNKNOWN_REASON


def test_final_quality_gate_passes_only_with_clear_no_trade_ranking_and_truth():
    report = build_final_executable_quality_report(
        no_trade=_clear_no_trade(),
        ranking=_ranking_with_executable(),
        executable_truths=[_allowed_truth()],
        now_epoch=1772202600.0,
    )
    payload = report.to_payload()

    assert payload["status"] == FINAL_EXECUTABLE_QUALITY_PASSED
    assert payload["executable_quality_passed"] is True
    assert payload["primary_reason"] == "ok"
    assert payload["selected_candidate"]["candidate_id"] == "cand-1"
    assert payload["blockers"] == []
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload[_ACTION_KEY] is False
    assert payload[_BROKER_KEY] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
