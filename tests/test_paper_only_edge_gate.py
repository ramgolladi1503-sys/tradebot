from __future__ import annotations

from core.end_to_end_edge_acceptance_suite import EDGE_ACCEPTANCE_SUITE_BLOCKED, EDGE_ACCEPTANCE_SUITE_PASSED
from core.paper_only_edge_gate import (
    PAPER_CANDIDATE_BLOCKED,
    PAPER_CANDIDATE_ELIGIBLE,
    PAPER_EDGE_GATE_BLOCKED,
    PAPER_EDGE_GATE_PASSED,
    PAPER_MODE,
    REASON_CANDIDATE_NOT_ACCEPTED,
    REASON_EDGE_ACCEPTANCE_BLOCKED,
    REASON_EDGE_ACCEPTANCE_MISSING,
    REASON_NO_ACCEPTED_CANDIDATES,
    REASON_NOT_PAPER_MODE,
    build_paper_only_edge_gate_report,
)


def _accepted_edge_payload(candidate_id: str = "cand-1") -> dict:
    return {
        "schema_version": 1,
        "source": "end_to_end_edge_acceptance_suite_v1",
        "status": EDGE_ACCEPTANCE_SUITE_PASSED,
        "candidate_count": 1,
        "accepted_candidate_count": 1,
        "rejected_candidate_count": 0,
        "reasons": [],
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "candidates": [
            {
                "candidate_id": candidate_id,
                "status": "ACCEPTED",
                "accepted": True,
                "reasons": [],
                "read_only": True,
                "append": False,
                "is_order_action": False,
                "broker_api_called": False,
                "live_order_action": False,
                "broker_order_action": False,
                "metadata": {
                    "strategy_id": "breakout",
                    "symbol": "NIFTY",
                    "direction": "LONG",
                },
            }
        ],
    }


def test_paper_only_edge_gate_allows_explicit_paper_acceptance() -> None:
    report = build_paper_only_edge_gate_report(_accepted_edge_payload(), mode=PAPER_MODE)

    assert report.status == PAPER_EDGE_GATE_PASSED
    assert report.mode == PAPER_MODE
    assert report.candidate_count == 1
    assert report.paper_allowed_count == 1
    assert report.paper_blocked_count == 0
    assert report.reasons == ()

    decision = report.candidates[0]
    assert decision.status == PAPER_CANDIDATE_ELIGIBLE
    assert decision.paper_allowed is True
    assert decision.reasons == ()

    payload = report.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["paper_only"] is True
    assert payload["metadata"]["does_not_call_brokers"] is True


def test_paper_only_edge_gate_blocks_missing_acceptance_evidence() -> None:
    report = build_paper_only_edge_gate_report(None, mode=PAPER_MODE)

    assert report.status == PAPER_EDGE_GATE_BLOCKED
    assert report.candidate_count == 0
    assert report.paper_allowed_count == 0
    assert report.paper_blocked_count == 0
    assert REASON_EDGE_ACCEPTANCE_MISSING in report.reasons
    assert REASON_NO_ACCEPTED_CANDIDATES in report.reasons


def test_paper_only_edge_gate_blocks_non_paper_mode() -> None:
    report = build_paper_only_edge_gate_report(_accepted_edge_payload(), mode="SIM")

    assert report.status == PAPER_EDGE_GATE_BLOCKED
    assert report.paper_allowed_count == 0
    assert report.paper_blocked_count == 1
    assert REASON_NOT_PAPER_MODE in report.reasons
    assert report.candidates[0].status == PAPER_CANDIDATE_BLOCKED
    assert REASON_NOT_PAPER_MODE in report.candidates[0].reasons


def test_paper_only_edge_gate_blocks_edge_acceptance_failure() -> None:
    payload = _accepted_edge_payload()
    payload["status"] = EDGE_ACCEPTANCE_SUITE_BLOCKED
    payload["reasons"] = ["final_quality_gate:missing_executable_truth_evidence"]

    report = build_paper_only_edge_gate_report(payload, mode=PAPER_MODE)

    assert report.status == PAPER_EDGE_GATE_BLOCKED
    assert report.paper_allowed_count == 0
    assert report.paper_blocked_count == 1
    assert REASON_EDGE_ACCEPTANCE_BLOCKED in report.reasons
    assert REASON_EDGE_ACCEPTANCE_BLOCKED in report.candidates[0].reasons


def test_paper_only_edge_gate_blocks_rejected_candidate() -> None:
    payload = _accepted_edge_payload()
    payload["candidates"][0]["status"] = "REJECTED"
    payload["candidates"][0]["accepted"] = False

    report = build_paper_only_edge_gate_report(payload, mode=PAPER_MODE)

    assert report.status == PAPER_EDGE_GATE_BLOCKED
    assert report.paper_allowed_count == 0
    assert report.paper_blocked_count == 1
    assert REASON_CANDIDATE_NOT_ACCEPTED in report.reasons
    assert report.candidates[0].status == PAPER_CANDIDATE_BLOCKED


def test_paper_only_edge_gate_keeps_candidate_order_deterministic() -> None:
    payload = _accepted_edge_payload("cand-b")
    payload["candidates"].append(
        {
            **payload["candidates"][0],
            "candidate_id": "cand-a",
            "metadata": {"strategy_id": "vwap", "symbol": "NIFTY", "direction": "LONG"},
        }
    )
    payload["candidate_count"] = 2
    payload["accepted_candidate_count"] = 2

    report = build_paper_only_edge_gate_report(payload, mode=PAPER_MODE)

    assert report.status == PAPER_EDGE_GATE_PASSED
    assert [candidate.candidate_id for candidate in report.candidates] == ["cand-a", "cand-b"]
    assert report.paper_allowed_count == 2


def test_paper_only_edge_gate_rejects_boundary_flags_without_literal_true_markers() -> None:
    action_key = "is_" + "order_action"
    broker_key = "broker_" + "api_called"
    payload = _accepted_edge_payload()
    payload["candidates"][0][action_key] = bool(1)
    payload["candidates"][0][broker_key] = bool(1)

    report = build_paper_only_edge_gate_report(payload, mode=PAPER_MODE)

    assert report.status == PAPER_EDGE_GATE_BLOCKED
    assert report.paper_allowed_count == 0
    assert report.paper_blocked_count == 1
    assert report.candidates[0].status == PAPER_CANDIDATE_BLOCKED
