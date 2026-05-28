from __future__ import annotations

from core.final_edge_readiness_report import (
    FINAL_EDGE_CANDIDATE_BLOCKED,
    FINAL_EDGE_CANDIDATE_READY,
    FINAL_EDGE_READINESS_BLOCKED,
    FINAL_EDGE_READINESS_PASSED,
    REASON_CANDIDATE_NOT_REVIEW_ALLOWED,
    REASON_NO_REVIEW_ALLOWED_CANDIDATES,
    REASON_THROTTLE_BLOCKED,
    REASON_THROTTLE_MISSING,
    build_final_edge_readiness_report,
)
from core.live_pilot_risk_throttle import (
    LIVE_PILOT_CANDIDATE_BLOCKED,
    LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE,
    LIVE_PILOT_THROTTLE_BLOCKED,
    LIVE_PILOT_THROTTLE_PASSED,
)


def _throttle_candidate(
    candidate_id: str = "cand-1",
    *,
    strategy_id: str = "breakout",
    symbol: str = "NIFTY",
    review_allowed: bool = True,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "status": LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE if review_allowed else LIVE_PILOT_CANDIDATE_BLOCKED,
        "review_allowed": review_allowed,
        "reasons": [] if review_allowed else ["CANDIDATE_NOT_REVIEW_ALLOWED"],
        "paper_gate_status": "PAPER_EDGE_GATE_PASSED",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "metadata": {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "direction": "LONG",
        },
    }


def _throttle_payload(*candidates: dict, status: str = LIVE_PILOT_THROTTLE_PASSED) -> dict:
    values = list(candidates) or [_throttle_candidate()]
    allowed = sum(1 for candidate in values if candidate.get("review_allowed") is True)
    return {
        "schema_version": 1,
        "source": "live_pilot_risk_throttle_v1",
        "status": status,
        "candidate_count": len(values),
        "review_allowed_count": allowed,
        "review_blocked_count": len(values) - allowed,
        "reasons": [] if status == LIVE_PILOT_THROTTLE_PASSED else ["PAPER_GATE_BLOCKED"],
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "candidates": values,
    }


def test_final_edge_readiness_report_passes_clean_throttle_candidate() -> None:
    report = build_final_edge_readiness_report(_throttle_payload())

    assert report.status == FINAL_EDGE_READINESS_PASSED
    assert report.candidate_count == 1
    assert report.ready_candidate_count == 1
    assert report.blocked_candidate_count == 0
    assert report.reasons == ()

    decision = report.candidates[0]
    assert decision.status == FINAL_EDGE_CANDIDATE_READY
    assert decision.ready is True
    assert decision.reasons == ()

    payload = report.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["final_edge_report"] is True
    assert payload["metadata"]["does_not_call_brokers"] is True


def test_final_edge_readiness_report_blocks_absent_throttle() -> None:
    report = build_final_edge_readiness_report(None)

    assert report.status == FINAL_EDGE_READINESS_BLOCKED
    assert report.candidate_count == 0
    assert report.ready_candidate_count == 0
    assert REASON_THROTTLE_MISSING in report.reasons
    assert REASON_NO_REVIEW_ALLOWED_CANDIDATES in report.reasons


def test_final_edge_readiness_report_blocks_throttle_failure() -> None:
    report = build_final_edge_readiness_report(_throttle_payload(status=LIVE_PILOT_THROTTLE_BLOCKED))

    assert report.status == FINAL_EDGE_READINESS_BLOCKED
    assert report.ready_candidate_count == 0
    assert report.blocked_candidate_count == 1
    assert REASON_THROTTLE_BLOCKED in report.reasons
    assert REASON_THROTTLE_BLOCKED in report.candidates[0].reasons


def test_final_edge_readiness_report_blocks_non_review_candidate() -> None:
    report = build_final_edge_readiness_report(_throttle_payload(_throttle_candidate(review_allowed=False)))

    assert report.status == FINAL_EDGE_READINESS_BLOCKED
    assert report.ready_candidate_count == 0
    assert report.blocked_candidate_count == 1
    assert REASON_CANDIDATE_NOT_REVIEW_ALLOWED in report.reasons
    assert report.candidates[0].status == FINAL_EDGE_CANDIDATE_BLOCKED


def test_final_edge_readiness_report_keeps_candidate_order_deterministic() -> None:
    payload = _throttle_payload(
        _throttle_candidate("cand-b", strategy_id="vwap", symbol="BANKNIFTY"),
        _throttle_candidate("cand-a", strategy_id="breakout", symbol="NIFTY"),
    )

    report = build_final_edge_readiness_report(payload)

    assert report.status == FINAL_EDGE_READINESS_PASSED
    assert [candidate.candidate_id for candidate in report.candidates] == ["cand-a", "cand-b"]
    assert report.ready_candidate_count == 2
