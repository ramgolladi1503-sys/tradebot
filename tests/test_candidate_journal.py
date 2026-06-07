from __future__ import annotations

from pathlib import Path

import core.candidate_journal as candidate_journal
import core.review_queue as review_queue


def _base_row() -> dict:
    return {
        "candidate_id": "candidate-001",
        "trade_id": "trade-001",
        "symbol": "BANKNIFTY",
        "index": "BANKNIFTY",
        "strike": 49300,
        "expiry": "2026-06-11",
        "option_type": "CE",
        "strategy_family": "breakout",
        "strategy_id": "breakout_1",
        "regime": "LIVE",
        "side": "BUY",
        "direction": "LONG",
        "entry": 123.45,
        "entry_price": 123.45,
        "execution_entry": 123.45,
        "execution_entry_status": "executable",
        "display_entry": 123.45,
        "display_entry_status": "displayable",
        "stop_loss": 120.0,
        "target": 129.0,
        "target_price": 129.0,
        "rank_score": 91.2,
        "raw_rank_score": 88.1,
        "confidence": 0.74,
        "confidence_raw": 0.81,
        "confidence_final": 0.74,
        "opportunity_score": 77.7,
        "quote_age_sec": 1.4,
        "spread_pct": 0.23,
        "bid": 123.0,
        "ask": 124.0,
        "best_bid": 123.0,
        "best_ask": 124.0,
        "ltp": 123.5,
        "current_ltp": 123.5,
        "quote_source": "tick_store",
        "quote_validation_status": "OK",
        "feed_truth_state": "LIVE",
        "feed_truth_reason_code": "OK",
        "execution_truth_state": "executable",
        "execution_truth_blocked": False,
        "execution_truth_advisory": False,
        "execution_truth_blockers": [],
        "fallback_used": False,
        "row_kind": "candidate",
        "candidate_origin": "trade_builder",
        "candidate_class": "primary",
        "reportable_executable": True,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "readiness": "READY",
        "candidate_status": "executable",
        "visibility_bucket": "executable",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "final_emit_block_reason": None,
        "reject_reason": None,
        "reason": None,
    }


def test_candidate_journal_path_defaults_under_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_journal, "runtime_dir", lambda: tmp_path / ".runtime")
    assert candidate_journal.candidate_journal_path() == tmp_path / ".runtime" / "candidates" / "candidate_journal.jsonl"


def test_executable_candidate_row_forces_read_only_safety_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_journal, "runtime_dir", lambda: tmp_path / ".runtime")
    row = candidate_journal.build_candidate_journal_row(_base_row(), journal_event="candidate_reported", created_at="2026-06-07T00:00:00Z")
    assert row["schema_version"] == 1
    assert row["journal_event"] == "candidate_reported"
    assert row["candidate_id"] == "candidate-001"
    assert row["trade_id"] == "trade-001"
    assert row["read_only"] is True
    assert row["append"] is True
    assert row["is_order_action"] is False
    assert row["broker_api_called"] is False
    assert row["live_order_allowed"] is False
    assert row["live_order_action"] is False
    assert row["broker_order_action"] is False
    assert row["allowed_for_live_execution"] is False
    assert row["execution_behavior_changed"] is False
    assert row["execution_truth_blockers"] == []
    assert row["fallback_used"] is False


def test_blocked_candidate_row_preserves_blockers_and_truth():
    row = _base_row()
    row.update(
        {
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "execution_status": "blocked",
            "execution_truth_blocked": True,
            "execution_truth_blockers": ["STALE_OPTION_LTP"],
            "reportable_executable": False,
            "eligible_for_execution": False,
            "execution_allowed": False,
            "readiness": "BLOCKED",
            "candidate_status": "blocked",
            "visibility_bucket": "blocked",
            "final_emit_block_reason": "STALE_OPTION_LTP",
            "reject_reason": "STALE_OPTION_LTP",
            "reason": "STALE_OPTION_LTP",
        }
    )
    journal_row = candidate_journal.build_candidate_journal_row(row)
    assert journal_row["permission"] == "BLOCK"
    assert journal_row["final_action"] == "BLOCK"
    assert journal_row["execution_status"] == "blocked"
    assert journal_row["execution_truth_blocked"] is True
    assert journal_row["execution_truth_blockers"] == ["STALE_OPTION_LTP"]
    assert journal_row["reportable_executable"] is False
    assert journal_row["final_emit_block_reason"] == "STALE_OPTION_LTP"


def test_fallback_candidate_row_marks_fallback_used_without_blocking():
    row = _base_row()
    row.update(
        {
            "row_kind": "recovered_fallback",
            "quote_source": "rest_fallback",
            "fallback_used": False,
        }
    )
    journal_row = candidate_journal.build_candidate_journal_row(row)
    assert journal_row["fallback_used"] is True
    assert journal_row["permission"] == "EXECUTE"
    assert journal_row["final_action"] == "EXECUTE"


def test_queue_only_candidate_row_keeps_queue_only_lifecycle():
    row = _base_row()
    row.update(
        {
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "readiness": "QUEUE_ONLY",
            "candidate_status": "advisory_only",
            "visibility_bucket": "advisory",
            "execution_allowed": False,
            "eligible_for_execution": False,
        }
    )
    journal_row = candidate_journal.build_candidate_journal_row(row)
    assert journal_row["permission"] == "QUEUE_ONLY"
    assert journal_row["final_action"] == "QUEUE_ONLY"
    assert journal_row["execution_status"] == "queue_only"
    assert journal_row["readiness"] == "QUEUE_ONLY"
    assert journal_row["candidate_status"] == "advisory_only"


def test_write_candidate_journal_row_failure_is_non_fatal(monkeypatch):
    class BoomWriter:
        def write(self, payload):
            raise RuntimeError("boom")

    monkeypatch.setattr(candidate_journal, "get_jsonl_writer", lambda path: BoomWriter())
    row, ok = candidate_journal.write_candidate_journal_row(_base_row(), path=Path("/tmp/candidate_journal.jsonl"))
    assert ok is False
    assert row["candidate_id"] == "candidate-001"


def test_review_queue_wires_candidate_journal_at_final_artifact_boundary(tmp_path, monkeypatch):
    entry = _base_row()
    captured = {}

    monkeypatch.setattr(review_queue, "write_queue_rows", lambda path, rows: None)
    monkeypatch.setattr(review_queue, "_emit_review_queue_logs", lambda ranked: {"ok": True})
    monkeypatch.setattr(review_queue, "_update_suggestions_status_latest", lambda *args, **kwargs: None)
    monkeypatch.setattr(review_queue, "_merge_trade_entry", lambda data, row: list(data) + [dict(row)])
    monkeypatch.setattr(review_queue, "_rank_review_queue_rows", lambda data, path=None: list(data))
    monkeypatch.setattr(review_queue, "_find_ranked_queue_entry", lambda ranked_rows, row: ranked_rows[-1])

    def _capture(payload, *, journal_event="candidate_journal", created_at=None, path=None):
        captured["payload"] = dict(payload)
        captured["journal_event"] = journal_event
        return dict(payload), True

    monkeypatch.setattr(review_queue, "write_candidate_journal_row", _capture)

    out = review_queue._write_review_queue_artifacts(tmp_path / "review_queue.json", [], entry)

    assert out["trade_id"] == "trade-001"
    assert captured["payload"]["trade_id"] == "trade-001"
    assert captured["journal_event"] == "candidate_reported"


def test_candidate_journal_module_avoids_broker_and_order_imports():
    source = Path(candidate_journal.__file__).read_text(encoding="utf-8")
    forbidden = ("broker", "order_router", "live_trade", "kite", "upstox")
    assert not any(f"from core.{name}" in source or f"import {name}" in source for name in forbidden)
