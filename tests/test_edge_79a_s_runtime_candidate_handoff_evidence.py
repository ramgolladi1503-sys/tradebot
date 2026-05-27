from __future__ import annotations

import json

from core.runtime_candidate_handoff import (
    RUNTIME_CANDIDATE_HANDOFF_SOURCE,
    build_runtime_candidate_handoff_payload,
    write_runtime_candidate_handoff_evidence,
)


def test_handoff_payload_detects_executable_lost_before_phase2():
    payload = build_runtime_candidate_handoff_payload(
        symbol="SENSEX",
        trade_builder_raw_count=18,
        post_scan_survivor_count=9,
        post_soft_reject_count=9,
        post_real_filter_count=9,
        post_executable_filter_count=8,
        ranked_total_count=9,
        ranked_executable_count=8,
        top_reportable_executable={
            "trade_id": "SENSEX-2026-05-27-76100-CE-breakout-1779869031",
            "reportable_executable": True,
            "execution_allowed": True,
        },
        cycle_ranked_candidates_count_before_append=0,
        cycle_ranked_candidates_count_after_append=0,
        phase2_input_count=0,
        top_opportunities_payload={
            "source_candidate_count": 0,
            "top_executable_count": 0,
            "phase2_state": "NO_TRADE",
            "selector_outcome": "NO_EXECUTABLE_OPPORTUNITY",
        },
        generated_epoch=1_000.0,
    )

    assert payload["schema_version"] == 1
    assert payload["source"] == RUNTIME_CANDIDATE_HANDOFF_SOURCE
    assert payload["symbol"] == "SENSEX"
    assert payload["trade_builder_raw_count"] == 18
    assert payload["post_scan_survivor_count"] == 9
    assert payload["post_executable_filter_count"] == 8
    assert payload["ranked_total_count"] == 9
    assert payload["ranked_executable_count"] == 8
    assert payload["top_reportable_executable"] is True
    assert payload["top_reportable_executable_trade_id"] == "SENSEX-2026-05-27-76100-CE-breakout-1779869031"
    assert payload["phase2_input_count"] == 0
    assert payload["top_opportunities_source_candidate_count"] == 0
    assert payload["top_opportunities_executable_count"] == 0
    assert payload["handoff_mismatch"] is True
    assert payload["mismatch_reason"] == "trade_builder_reportable_executable_candidates_not_visible_to_phase2_or_top_opportunities"


def test_handoff_payload_has_read_only_non_action_flags():
    payload = build_runtime_candidate_handoff_payload(
        symbol="NIFTY",
        ranked_executable_count=1,
        phase2_input_count=0,
        generated_epoch=1_000.0,
    )

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["metadata"]["does_not_change_gate_decision"] is True
    assert payload["metadata"]["does_not_change_candidate_state"] is True
    assert payload["metadata"]["does_not_run_phase2"] is True
    assert payload["metadata"]["does_not_call_broker"] is True


def test_handoff_payload_marks_no_mismatch_when_phase2_and_top_opportunities_received_candidates():
    payload = build_runtime_candidate_handoff_payload(
        symbol="SENSEX",
        ranked_executable_count=2,
        top_reportable_executable={"trade_id": "SENSEX-OK"},
        phase2_input_count=2,
        top_opportunities_payload={
            "source_candidate_count": 2,
            "top_executable_count": 1,
            "phase2_state": "ENTER",
            "selector_outcome": "EXECUTE_TOP",
        },
        generated_epoch=1_000.0,
    )

    assert payload["handoff_mismatch"] is False
    assert payload["mismatch_reason"] == ""
    assert payload["top_opportunities_phase2_state"] == "ENTER"
    assert payload["top_opportunities_selector_outcome"] == "EXECUTE_TOP"


def test_handoff_writer_creates_latest_json(tmp_path):
    target = tmp_path / "runtime_candidate_handoff_latest.json"

    out = write_runtime_candidate_handoff_evidence(
        path=target,
        symbol="SENSEX",
        ranked_executable_count=1,
        phase2_input_count=0,
        top_opportunities_payload={"source_candidate_count": 0, "top_executable_count": 0},
        generated_epoch=1_000.0,
    )

    assert out == target
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["symbol"] == "SENSEX"
    assert saved["handoff_mismatch"] is True
    assert saved["read_only"] is True
    assert saved["broker_order_action"] is False
