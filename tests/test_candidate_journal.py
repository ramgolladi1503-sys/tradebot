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
    assert row["setup_id"].startswith("breakout__LIVE__")
    assert row["setup_family"] == "breakout"
    assert row["regime_bucket"] == "LIVE"
    assert row["metadata"]["setup_fingerprint"]["setup_id"] == row["setup_id"]


def test_candidate_journal_preserves_timing_and_oos_when_present():
    row = _base_row()
    row.update(
        {
            "snapshot_ts_utc": "2026-06-07T09:15:00+05:30",
            "feature_cutoff_ts": "2026-06-07T09:15:00+05:30",
            "signal_ts": "2026-06-07T09:16:00+05:30",
            "earliest_entry_ts": "2026-06-07T09:16:30+05:30",
            "is_oos": True,
            "oos_label": "OOS",
            "oos_source": "wfa_partition_context",
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "OK",
        }
    )

    journal_row = candidate_journal.build_candidate_journal_row(row, created_at="2026-06-07T09:17:00+05:30")

    assert journal_row["feature_cutoff_ts"] == "2026-06-07T09:15:00+05:30"
    assert journal_row["signal_ts"] == "2026-06-07T09:16:00+05:30"
    assert journal_row["earliest_entry_ts"] == "2026-06-07T09:16:30+05:30"
    assert journal_row["is_oos"] is True
    assert journal_row["oos_label"] == "OOS"
    assert journal_row["oos_source"] == "wfa_partition_context"
    assert journal_row["feature_cutoff_ts_source"] == "preserved:feature_cutoff_ts"
    assert journal_row["signal_ts_source"] == "preserved:signal_ts"
    assert journal_row["earliest_entry_ts_source"] == "preserved:earliest_entry_ts"
    assert journal_row["oos_source"] == "wfa_partition_context"
    assert journal_row["strict_replay_export_ready"] is True
    assert journal_row["strict_replay_export_blockers"] == []
    assert journal_row["replay_context_ready"] is True
    assert journal_row["replay_context_blockers"] == []
    assert journal_row["replay_context"]["feature_cutoff_ts"] == "2026-06-07T09:15:00+05:30"
    assert journal_row["replay_context"]["signal_ts"] == "2026-06-07T09:16:00+05:30"
    assert journal_row["replay_context"]["is_oos"] is True
    assert journal_row["replay_context"]["oos_label"] == "OOS"
    assert journal_row["rank_score"] == 91.2
    assert journal_row["confidence_final"] == 0.74


def test_candidate_journal_marks_missing_timing_and_oos_as_blocked():
    row = _base_row()
    row.pop("snapshot_ts_utc", None)
    row.pop("feature_cutoff_ts", None)
    row.pop("signal_ts", None)
    row.pop("earliest_entry_ts", None)
    row.pop("is_oos", None)
    row.pop("oos_label", None)

    journal_row = candidate_journal.build_candidate_journal_row(row, created_at="2026-06-07T09:17:00+05:30")

    assert journal_row["feature_cutoff_ts"] is None
    assert journal_row["signal_ts"] == "2026-06-07T09:17:00+05:30"
    assert journal_row["earliest_entry_ts"] is None
    assert journal_row["is_oos"] is None
    assert journal_row["oos_label"] is None
    assert journal_row["feature_cutoff_ts_source"] == "missing"
    assert journal_row["signal_ts_source"] == "preserved:signal_ts"
    assert journal_row["earliest_entry_ts_source"] == "missing"
    assert journal_row["oos_source"] == "unknown_runtime_context"
    assert journal_row["strict_replay_export_ready"] is False
    assert journal_row["strict_replay_export_blockers"] == [
        "missing_feature_cutoff_ts",
        "missing_earliest_entry_ts",
        "missing_is_oos",
        "missing_oos_label",
    ]
    assert journal_row["replay_context_ready"] is False
    assert "missing_feature_cutoff_ts" in journal_row["replay_context_blockers"]
    assert "missing_earliest_entry_ts" in journal_row["replay_context_blockers"]
    assert "missing_is_oos" in journal_row["replay_context_blockers"]
    assert "missing_oos_label" in journal_row["replay_context_blockers"]


def test_candidate_journal_does_not_guess_feature_cutoff_from_created_timestamp():
    row = _base_row()
    row.pop("snapshot_ts_utc", None)
    row.pop("feature_cutoff_ts", None)
    row.pop("signal_ts", None)
    row.pop("earliest_entry_ts", None)
    row.pop("is_oos", None)
    row.pop("oos_label", None)
    row["created_ts_utc"] = "2026-06-07T09:17:00+05:30"

    journal_row = candidate_journal.build_candidate_journal_row(row, created_at="2026-06-07T09:17:00+05:30")

    assert journal_row["feature_cutoff_ts"] is None
    assert journal_row["feature_cutoff_ts_source"] == "missing"
    assert journal_row["replay_context"]["feature_cutoff_ts"] is None
    assert "missing_feature_cutoff_ts" in journal_row["replay_context_blockers"]


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


def test_fallback_candidate_row_preserves_queue_only_lifecycle():
    row = _base_row()
    row.update(
        {
            "row_kind": "recovered_fallback",
            "quote_source": "rest_fallback",
            "fallback_used": True,
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "readiness": "QUEUE_ONLY",
            "candidate_status": "advisory_only",
            "visibility_bucket": "advisory",
            "execution_allowed": False,
            "eligible_for_execution": False,
            "reportable_executable": False,
        }
    )
    journal_row = candidate_journal.build_candidate_journal_row(row)
    assert journal_row["fallback_used"] is True
    assert journal_row["permission"] == "QUEUE_ONLY"
    assert journal_row["final_action"] == "QUEUE_ONLY"
    assert journal_row["execution_status"] == "queue_only"
    assert journal_row["readiness"] == "QUEUE_ONLY"
    assert journal_row["candidate_status"] == "advisory_only"
    assert journal_row["reportable_executable"] is False


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
    entry.update(
        {
            "feature_cutoff_ts": "2026-06-07T09:15:00+05:30",
            "signal_ts": "2026-06-07T09:16:00+05:30",
            "earliest_entry_ts": "2026-06-07T09:16:30+05:30",
            "is_oos": False,
            "oos_label": "IS",
        }
    )
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
    assert captured["payload"]["feature_cutoff_ts"] == "2026-06-07T09:15:00+05:30"
    assert captured["payload"]["signal_ts"] == "2026-06-07T09:16:00+05:30"
    assert captured["payload"]["earliest_entry_ts"] == "2026-06-07T09:16:30+05:30"
    assert captured["payload"]["is_oos"] is False
    assert captured["payload"]["oos_label"] == "IS"
    assert captured["journal_event"] == "candidate_reported"


def test_candidate_journal_module_avoids_broker_and_order_imports():
    source = Path(candidate_journal.__file__).read_text(encoding="utf-8")
    forbidden = ("broker", "order_router", "live_trade", "kite", "upstox")
    assert not any(f"from core.{name}" in source or f"import {name}" in source for name in forbidden)
