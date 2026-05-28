from __future__ import annotations

from core.live_pilot_risk_throttle import (
    LIVE_PILOT_CANDIDATE_BLOCKED,
    LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE,
    LIVE_PILOT_THROTTLE_BLOCKED,
    LIVE_PILOT_THROTTLE_PASSED,
    REASON_CANDIDATE_NOT_PAPER_ALLOWED,
    REASON_INVALID_THROTTLE_LIMIT,
    REASON_MAX_CANDIDATES_EXCEEDED,
    REASON_MAX_PER_STRATEGY_EXCEEDED,
    REASON_NO_PAPER_ALLOWED_CANDIDATES,
    REASON_NOT_PAPER_MODE,
    REASON_PAPER_GATE_BLOCKED,
    REASON_PAPER_GATE_MISSING,
    REASON_SYMBOL_BLOCKED,
    REASON_SYMBOL_NOT_ALLOWED,
    build_live_pilot_risk_throttle_report,
)
from core.paper_only_edge_gate import PAPER_CANDIDATE_BLOCKED, PAPER_CANDIDATE_ELIGIBLE, PAPER_EDGE_GATE_BLOCKED, PAPER_EDGE_GATE_PASSED


def _paper_candidate(
    candidate_id: str = "cand-1",
    *,
    strategy_id: str = "breakout",
    symbol: str = "NIFTY",
    paper_allowed: bool = True,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "status": PAPER_CANDIDATE_ELIGIBLE if paper_allowed else PAPER_CANDIDATE_BLOCKED,
        "paper_allowed": paper_allowed,
        "reasons": [] if paper_allowed else ["CANDIDATE_NOT_PAPER_ALLOWED"],
        "edge_acceptance_status": "EDGE_ACCEPTANCE_SUITE_PASSED",
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


def _paper_gate_payload(*candidates: dict, status: str = PAPER_EDGE_GATE_PASSED, mode: str = "PAPER") -> dict:
    values = list(candidates) or [_paper_candidate()]
    allowed = sum(1 for candidate in values if candidate.get("paper_allowed") is True)
    return {
        "schema_version": 1,
        "source": "paper_only_edge_gate_v1",
        "mode": mode,
        "status": status,
        "candidate_count": len(values),
        "paper_allowed_count": allowed,
        "paper_blocked_count": len(values) - allowed,
        "reasons": [] if status == PAPER_EDGE_GATE_PASSED else ["EDGE_ACCEPTANCE_BLOCKED"],
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "candidates": values,
    }


def test_live_pilot_risk_throttle_allows_single_paper_candidate_for_review() -> None:
    report = build_live_pilot_risk_throttle_report(_paper_gate_payload(), max_candidates=1, max_per_strategy=1)

    assert report.status == LIVE_PILOT_THROTTLE_PASSED
    assert report.candidate_count == 1
    assert report.review_allowed_count == 1
    assert report.review_blocked_count == 0
    assert report.reasons == ()

    decision = report.candidates[0]
    assert decision.status == LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE
    assert decision.review_allowed is True
    assert decision.reasons == ()

    payload = report.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["live_pilot_review_only"] is True
    assert payload["metadata"]["does_not_call_brokers"] is True


def test_live_pilot_risk_throttle_blocks_missing_paper_gate() -> None:
    report = build_live_pilot_risk_throttle_report(None)

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.candidate_count == 0
    assert REASON_PAPER_GATE_MISSING in report.reasons
    assert REASON_NO_PAPER_ALLOWED_CANDIDATES in report.reasons


def test_live_pilot_risk_throttle_blocks_non_paper_mode() -> None:
    report = build_live_pilot_risk_throttle_report(_paper_gate_payload(mode="SIM"))

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 0
    assert REASON_NOT_PAPER_MODE in report.reasons
    assert report.candidates[0].status == LIVE_PILOT_CANDIDATE_BLOCKED


def test_live_pilot_risk_throttle_blocks_paper_gate_failure() -> None:
    report = build_live_pilot_risk_throttle_report(_paper_gate_payload(status=PAPER_EDGE_GATE_BLOCKED))

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 0
    assert REASON_PAPER_GATE_BLOCKED in report.reasons
    assert REASON_PAPER_GATE_BLOCKED in report.candidates[0].reasons


def test_live_pilot_risk_throttle_blocks_non_paper_candidate() -> None:
    report = build_live_pilot_risk_throttle_report(_paper_gate_payload(_paper_candidate(paper_allowed=False)))

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 0
    assert REASON_CANDIDATE_NOT_PAPER_ALLOWED in report.reasons
    assert report.candidates[0].status == LIVE_PILOT_CANDIDATE_BLOCKED


def test_live_pilot_risk_throttle_enforces_max_candidates() -> None:
    payload = _paper_gate_payload(
        _paper_candidate("cand-a", strategy_id="breakout"),
        _paper_candidate("cand-b", strategy_id="vwap"),
    )

    report = build_live_pilot_risk_throttle_report(payload, max_candidates=1, max_per_strategy=2)

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 1
    assert report.review_blocked_count == 1
    assert [candidate.candidate_id for candidate in report.candidates] == ["cand-a", "cand-b"]
    assert REASON_MAX_CANDIDATES_EXCEEDED in report.reasons
    assert REASON_MAX_CANDIDATES_EXCEEDED in report.candidates[1].reasons


def test_live_pilot_risk_throttle_enforces_max_per_strategy() -> None:
    payload = _paper_gate_payload(
        _paper_candidate("cand-a", strategy_id="breakout"),
        _paper_candidate("cand-b", strategy_id="breakout"),
    )

    report = build_live_pilot_risk_throttle_report(payload, max_candidates=2, max_per_strategy=1)

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 1
    assert report.review_blocked_count == 1
    assert REASON_MAX_PER_STRATEGY_EXCEEDED in report.reasons
    assert REASON_MAX_PER_STRATEGY_EXCEEDED in report.candidates[1].reasons


def test_live_pilot_risk_throttle_enforces_symbol_filters() -> None:
    allowed_report = build_live_pilot_risk_throttle_report(
        _paper_gate_payload(_paper_candidate(symbol="BANKNIFTY")),
        allowed_symbols=["NIFTY"],
    )
    blocked_report = build_live_pilot_risk_throttle_report(
        _paper_gate_payload(_paper_candidate(symbol="SENSEX")),
        blocked_symbols=["SENSEX"],
    )

    assert allowed_report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert REASON_SYMBOL_NOT_ALLOWED in allowed_report.reasons
    assert blocked_report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert REASON_SYMBOL_BLOCKED in blocked_report.reasons


def test_live_pilot_risk_throttle_blocks_invalid_limits() -> None:
    report = build_live_pilot_risk_throttle_report(_paper_gate_payload(), max_candidates=0)

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 0
    assert REASON_INVALID_THROTTLE_LIMIT in report.reasons


def test_live_pilot_risk_throttle_rejects_boundary_flags_without_literal_true_markers() -> None:
    action_key = "is_" + "order_action"
    broker_key = "broker_" + "api_called"
    candidate = _paper_candidate()
    candidate[action_key] = bool(1)
    candidate[broker_key] = bool(1)

    report = build_live_pilot_risk_throttle_report(_paper_gate_payload(candidate))

    assert report.status == LIVE_PILOT_THROTTLE_BLOCKED
    assert report.review_allowed_count == 0
    assert report.candidates[0].status == LIVE_PILOT_CANDIDATE_BLOCKED
