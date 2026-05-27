from __future__ import annotations

import json

from core.live_truth_top_opportunities_alignment import (
    ALIGNMENT_STATUS_ALIGNED,
    ALIGNMENT_STATUS_BLOCKED,
    ALIGNMENT_STATUS_MISMATCH,
    EXECUTABLE_COUNT_MISMATCH_REASON,
    INVALID_RANKED_REPORT_REASON,
    INVALID_TOP_OPPORTUNITIES_REPORT_REASON,
    NO_MISMATCH_REASON,
    REQUIRED_TOP_EXECUTABLE_TRACE_FIELDS,
    RUNTIME_CANDIDATE_HANDOFF_INCOMPLETE_REASON,
    TOP_EXECUTABLE_MISSING_REASON,
    TOP_EXECUTABLE_TRACE_INCOMPLETE_REASON,
    TOP_OPPORTUNITIES_ALIGNMENT_SOURCE,
    TOP_REPORTABLE_MISMATCH_REASON,
    build_top_opportunities_executable_alignment,
)


def _complete_trace(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": "TB-20260527-001",
        "appeared_at": "2026-05-27T09:15:00Z",
        "symbol": "NIFTY",
        "strike": 23000,
        "option_type": "CE",
        "strategy_family": "breakout",
        "entry": 125.5,
        "execution_entry": 126.0,
        "stop_loss": 112.0,
        "target": 154.0,
        "risk_reward": 2.0,
        "rank_score": 0.91,
        "source_quote_age": 0.8,
        "bid": 125.0,
        "ask": 126.0,
        "ltp": 125.5,
    }
    payload.update(overrides)
    return payload


def test_detects_ranked_executable_but_top_opportunities_zero_executable():
    ranked = {
        "source": "ranked_opportunity_report",
        "ranked_executable_count": 3,
        "top_reportable_executable": True,
    }
    top = {
        "source": "top_opportunities_latest",
        "top_opportunities_executable_count": 0,
        "top_reportable_executable": False,
    }

    payload = build_top_opportunities_executable_alignment(
        ranked,
        top,
        top_executable_trace=_complete_trace(),
        runtime_candidate_handoff=_complete_trace(),
    ).to_payload()

    assert payload["status"] == ALIGNMENT_STATUS_MISMATCH
    assert payload["reason_code"] == EXECUTABLE_COUNT_MISMATCH_REASON
    assert payload["ranked_executable_count"] == 3
    assert payload["top_opportunities_executable_count"] == 0
    assert payload["ranked_top_reportable_executable"] is True
    assert payload["top_opportunities_top_reportable_executable"] is False
    assert payload["mismatch_detected"] is True
    assert payload["aligned"] is False
    assert EXECUTABLE_COUNT_MISMATCH_REASON in payload["reasons"]
    assert TOP_REPORTABLE_MISMATCH_REASON in payload["reasons"]
    assert TOP_EXECUTABLE_MISSING_REASON in payload["reasons"]
    assert payload["top_executable_trace_complete"] is True
    assert payload["runtime_candidate_handoff_complete"] is True


def test_aligned_when_counts_top_reportable_and_trace_fields_match():
    ranked = {
        "source": "ranked_opportunity_report",
        "ranked_executable_count": 2,
        "top_reportable_executable": True,
    }
    top = {
        "source": "top_opportunities_latest",
        "top_opportunities_executable_count": 2,
        "top_reportable_executable": True,
    }

    payload = build_top_opportunities_executable_alignment(
        ranked,
        top,
        top_executable_trace=_complete_trace(),
        runtime_candidate_handoff=_complete_trace(),
    ).to_payload()

    assert payload["status"] == ALIGNMENT_STATUS_ALIGNED
    assert payload["reason_code"] == NO_MISMATCH_REASON
    assert payload["reasons"] == []
    assert payload["aligned"] is True
    assert payload["mismatch_detected"] is False
    assert payload["required_top_executable_trace_fields"] == list(REQUIRED_TOP_EXECUTABLE_TRACE_FIELDS)


def test_derives_counts_from_candidate_lists_when_counts_are_absent():
    ranked = {
        "ranked_candidates": [
            {"candidate_id": "a", "is_executable": True},
            {"candidate_id": "b", "is_executable": False},
            {"candidate_id": "c", "status": "EXECUTABLE"},
        ]
    }
    top = {
        "top_opportunities": [
            _complete_trace(candidate_id="a", reportable_executable=True),
            _complete_trace(candidate_id="c", status="REPORTABLE_EXECUTABLE"),
        ],
        "runtime_candidate_handoff_latest": _complete_trace(),
    }

    payload = build_top_opportunities_executable_alignment(ranked, top).to_payload()

    assert payload["status"] == ALIGNMENT_STATUS_ALIGNED
    assert payload["ranked_executable_count"] == 2
    assert payload["top_opportunities_executable_count"] == 2
    assert payload["ranked_top_reportable_executable"] is True
    assert payload["top_opportunities_top_reportable_executable"] is True
    assert payload["top_executable_trace_complete"] is True
    assert payload["runtime_candidate_handoff_complete"] is True


def test_detects_incomplete_top_executable_trace_and_handoff_fields():
    payload = build_top_opportunities_executable_alignment(
        {"ranked_executable_count": 1, "top_reportable_executable": True},
        {"top_opportunities_executable_count": 1, "top_reportable_executable": True},
        top_executable_trace={
            "trade_id": "TB-1",
            "symbol": "NIFTY",
            "entry": 100.0,
        },
        runtime_candidate_handoff={
            "trade_id": "TB-1",
            "symbol": "NIFTY",
            "entry": 100.0,
            "execution_entry": 100.5,
            "stop_loss": 90.0,
        },
    ).to_payload()

    assert payload["status"] == ALIGNMENT_STATUS_MISMATCH
    assert TOP_EXECUTABLE_TRACE_INCOMPLETE_REASON in payload["reasons"]
    assert RUNTIME_CANDIDATE_HANDOFF_INCOMPLETE_REASON in payload["reasons"]
    assert payload["top_executable_trace_complete"] is False
    assert payload["runtime_candidate_handoff_complete"] is False
    assert "appeared_at" in payload["missing_top_executable_trace_fields"]
    assert "risk_reward" in payload["missing_top_executable_trace_fields"]
    assert "target" in payload["missing_runtime_candidate_handoff_fields"]
    assert "bid" in payload["missing_runtime_candidate_handoff_fields"]
    assert "ask" in payload["missing_runtime_candidate_handoff_fields"]
    assert "ltp" in payload["missing_runtime_candidate_handoff_fields"]


def test_no_trace_required_when_no_executable_truth_exists():
    payload = build_top_opportunities_executable_alignment(
        {"ranked_executable_count": 0, "top_reportable_executable": False},
        {"top_opportunities_executable_count": 0, "top_reportable_executable": False},
    ).to_payload()

    assert payload["status"] == ALIGNMENT_STATUS_ALIGNED
    assert payload["metadata"]["trace_required"] is False
    assert payload["top_executable_trace_complete"] is True
    assert payload["runtime_candidate_handoff_complete"] is True


def test_blocks_invalid_ranked_or_top_opportunity_reports():
    payload = build_top_opportunities_executable_alignment({}, {}).to_payload()

    assert payload["status"] == ALIGNMENT_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_RANKED_REPORT_REASON
    assert INVALID_RANKED_REPORT_REASON in payload["reasons"]
    assert INVALID_TOP_OPPORTUNITIES_REPORT_REASON in payload["reasons"]
    assert payload["ranked_report_valid"] is False
    assert payload["top_opportunities_report_valid"] is False


def test_payload_is_json_serializable_and_non_action():
    payload = build_top_opportunities_executable_alignment(
        {"ranked_executable_count": 1, "top_reportable_executable": True},
        {"top_opportunities_executable_count": 1, "top_reportable_executable": True},
        top_executable_trace=_complete_trace(),
        runtime_candidate_handoff=_complete_trace(),
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert json.loads(encoded)["source"] == TOP_OPPORTUNITIES_ALIGNMENT_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["evidence_only_no_runtime_change"] is True
