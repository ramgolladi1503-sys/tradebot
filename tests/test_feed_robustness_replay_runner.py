from __future__ import annotations

from scripts import run_feed_robustness_replay as replay


def test_timestamp_fidelity_reports_source_and_extracted_timestamps(monkeypatch):
    rows = [{"source_row_index": 0, "ts": 1234.567890123, "token": "NSE_FO|1", "ltp": 100.0, "vol": 1.0, "oi": 2.0}]
    monkeypatch.setattr(replay.kite_depth_ws, "_is_underlying_token", lambda token: True)
    result = replay._capture_timestamp_fidelity(rows)
    assert result["summary"]["checked_rows"] == 1
    assert result["summary"]["pass"] is True
    assert result["rows"][0]["source_timestamp"] == rows[0]["ts"]
    assert result["rows"][0]["adapted_callback_timestamp"] == rows[0]["ts"]
    assert result["rows"][0]["receipt_time_fallback_used"] is False


def test_timestamp_fidelity_flags_missing_timestamp(monkeypatch):
    rows = [{"source_row_index": 0, "token": "NSE_FO|1", "ltp": 100.0, "vol": 1.0, "oi": 2.0}]
    monkeypatch.setattr(replay.kite_depth_ws, "_is_underlying_token", lambda token: True)
    result = replay._capture_timestamp_fidelity(rows)
    assert result["summary"]["checked_rows"] == 0
    assert result["summary"]["pass"] is False
    assert result["summary"]["unexpected_receipt_time_fallback_count"] == 1


def test_tick_store_mode_description_is_explicit():
    mode = replay._describe_tick_store_mode()
    assert {"sync_diagnostic_mode", "actual_production_persistence_mode", "queue_enabled",
            "writes_batched", "batch_size", "one_transaction_commits_multiple_rows",
            "runner_forces_synchronous_persistence", "flush_interval_sec"} <= set(mode)


def test_deterministic_replay_schedule_uses_source_duration():
    rows = [{"ts": 10.0}, {"ts": 12.5}, {"ts": 13.0}]
    source_duration, target_duration = replay._deterministic_replay_schedule(rows, 5.0)
    assert source_duration == 3.0
    assert target_duration == 0.6


def test_resource_snapshot_reports_bytes_and_mib():
    snapshot = replay._resource_snapshot()
    assert "rss_bytes" in snapshot
    assert "rss_mib" in snapshot
    assert "rss_kb" not in snapshot
    assert snapshot["rss_bytes"] > 0


def test_tick_store_worker_counters_are_explicit():
    counters = replay.tick_store.get_audit_counters()
    assert {"worker_started", "rows_enqueued", "rows_dequeued", "committed_batches", "worker_failures"} <= set(counters)
