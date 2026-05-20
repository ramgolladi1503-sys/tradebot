from __future__ import annotations

from core.review_queue import _final_emit_truth_event


def test_final_emit_abort_never_reports_executable_queue_only():
    label, payload = _final_emit_truth_event(
        {
            "trade_id": "t1",
            "symbol": "NIFTY",
            "execution_entry": 125.7,
            "execution_entry_status": "executable",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "candidate_status": "advisory_only",
            "execution_allowed": False,
            "final_emit_block_reason": "medium_global_conf",
        }
    )

    assert label == "FINAL_EMIT_ABORTED"
    assert payload["reportable_executable"] is False
    assert payload["final_emit_state"] == "aborted"
    assert payload["permission"] == "QUEUE_ONLY"


def test_final_emit_queue_only_is_non_executable_even_if_entry_status_is_legacy_executable():
    label, payload = _final_emit_truth_event(
        {
            "trade_id": "t2",
            "symbol": "NIFTY",
            "execution_entry": 217.1,
            "execution_entry_status": "executable",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "candidate_status": "advisory_only",
            "execution_allowed": False,
        }
    )

    assert label == "FINAL_EMIT_QUEUE_ONLY"
    assert payload["reportable_executable"] is False
    assert payload["final_emit_state"] == "queue_only"


def test_final_emit_block_is_non_executable():
    label, payload = _final_emit_truth_event(
        {
            "trade_id": "t3",
            "symbol": "BANKNIFTY",
            "execution_entry": None,
            "execution_entry_status": "blocked",
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "execution_status": "blocked",
            "candidate_status": "blocked",
            "execution_allowed": False,
        }
    )

    assert label == "FINAL_EMIT_BLOCKED"
    assert payload["reportable_executable"] is False
    assert payload["final_emit_state"] == "blocked"


def test_review_queue_source_does_not_emit_legacy_final_emit_line():
    source = open("core/review_queue.py", "r", encoding="utf-8").read()

    assert '"FINAL EMIT:"' not in source
    assert "FINAL_EMIT_QUEUE_ONLY" in source
    assert "FINAL_EMIT_ABORTED" in source
    assert "FINAL_EMIT_EXECUTABLE" in source
