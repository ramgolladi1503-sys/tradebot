from __future__ import annotations

import pytest
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


def test_resolve_persistence_mode_explicit_modes():
    assert replay._resolve_persistence_mode("normal_speed", "sync") is True
    assert replay._resolve_persistence_mode("normal_speed", "async_queue") is False
    assert replay._resolve_persistence_mode("normal_speed", "default") is False
    assert replay._resolve_persistence_mode("normal_speed_current_persistence", "default") is True


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


def test_callback_boundary_accepts_audit_row_fields():
    replay.collector.reset(enabled=True)
    replay.collector.callback(1, rows=[{
        "_audit_source_row_index": 9,
        "_audit_source_timestamp": 12.34,
        "instrument_token": 101,
        "last_price": 100.5,
        "volume": 2.0,
        "oi": 3.0,
    }])
    report = replay.collector.report()
    assert report["counters"]["decoded"] == 1
    assert report["checksums"]["callback_order_sha256"] != "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"


def test_fd_trace_summary_emits_terminal_fields(tmp_path):
    trace_path = tmp_path / "fd_trace.jsonl"
    trace_path.write_text(
        "\n".join([
            '{"stage":"on_ticks.callback_entry","fd_count":10}',
            '{"stage":"on_ticks.callback_exit","fd_count":12}',
            '{"stage":"on_ticks.callback_exit","fd_count":15}',
        ]) + "\n",
        encoding="utf-8",
    )
    summary = replay._fd_trace_summary(trace_path, baseline_fd=9, post_worker_shutdown_fd=11)
    assert summary["baseline_fd"] == 9
    assert summary["high_water_fd"] == 15
    assert summary["callback_exit_fd_min"] == 12
    assert summary["callback_exit_fd_max"] == 15
    assert summary["callback_exit_fd_count"] == 2
    assert summary["post_worker_shutdown_fd"] == 11
    assert summary["final_fd"] == 11


def test_tick_store_worker_state_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(tmp_path / "ticks.sqlite"), raising=False)
    replay.tick_store.reset_audit_counters()
    replay.tick_store.shutdown_persistence_worker()
    state = replay.tick_store.get_persistence_worker_state()
    assert {"worker_started", "worker_start_count", "worker_thread_id", "worker_terminated",
            "worker_join_completed", "worker_failures", "rows_enqueued", "rows_dequeued",
            "committed_batches", "committed_rows", "queue_depth_initial",
            "queue_depth_high_water", "queue_depth_at_shutdown", "pending_writes_at_shutdown",
            "flush_count", "batch_size", "flush_interval"} <= set(state)


def test_runner_scenario_filter_selects_only_requested_scenario(monkeypatch, tmp_path):
    all_scenarios = {
        "normal_speed": {"rows": [], "speed_factor": 1.0},
        "5x_speed": {"rows": [], "speed_factor": 5.0},
        "normal_speed_current_persistence": {"rows": [], "speed_factor": 1.0},
    }
    parser = replay.argparse.ArgumentParser()
    selected = replay._select_scenarios(all_scenarios, ["normal_speed"], parser)
    assert list(selected) == ["normal_speed"]
    assert selected["normal_speed"]["speed_factor"] == 1.0


def test_runner_main_runs_filtered_normal_speed_once(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(replay, "_load", lambda *args, **kwargs: [
        {"source_row_index": 0, "ts": 1.0, "token": "A", "ltp": 100.0, "vol": 1.0, "oi": 2.0},
        {"source_row_index": 1, "ts": 2.0, "token": "A", "ltp": 101.0, "vol": 1.0, "oi": 2.0},
    ])
    monkeypatch.setattr(replay, "_capture_timestamp_fidelity", lambda rows: {"summary": {"pass": True}, "rows": []})
    monkeypatch.setattr(replay, "_run_once", lambda rows, scenario, seed, **kwargs: calls.append((scenario, seed, kwargs)) or {
        "checksums": {"scenario": scenario, "seed": seed},
        "verdict": "PASS",
        "assertions": [],
        "unexplained_message_differences": [],
        "records": [],
        "latency": {},
        "reconnects": {},
        "resource_snapshot": {},
        "counters": {"pending_at_shutdown": 0},
    })
    monkeypatch.setattr(replay.tick_store, "reset_audit_counters", lambda: None)
    monkeypatch.setattr(replay.tick_store, "flush_pending_ticks", lambda *args, **kwargs: 0)
    monkeypatch.setattr(replay.tick_store, "pending_tick_count", lambda: 0)
    monkeypatch.setattr(replay.collector, "reset", lambda enabled=True: None)
    monkeypatch.setattr(replay, "_sha", lambda path: "sha")
    monkeypatch.setattr(replay, "_atomic_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(replay.subprocess, "check_output", lambda *args, **kwargs: "deadbeef\n")
    monkeypatch.setattr(replay.platform, "platform", lambda: "test-platform")
    monkeypatch.setattr(replay.Path, "is_file", lambda self: True)
    monkeypatch.setattr(replay.Path, "resolve", lambda self: self)
    monkeypatch.setattr(replay.sys, "argv", [
        "run_feed_robustness_replay.py",
        "--input", str(tmp_path / "input.parquet"),
        "--output-dir", str(tmp_path / "out"),
        "--iterations", "1",
        "--max-rows", "10",
        "--session-cycles", "0",
        "--scenario", "normal_speed",
    ])

    exit_code = replay.main()
    assert exit_code == 0
    assert [name for name, _, _ in calls] == ["normal_speed"]
    assert calls[0][1] == 0


def test_runner_main_records_persistence_mode(monkeypatch, tmp_path):
    captured = {}
    def _fake_run_once(rows, scenario, seed, **kwargs):
        captured["kwargs"] = kwargs
        return {
            "checksums": {"scenario": scenario, "seed": seed},
            "verdict": "PASS",
            "assertions": [],
            "unexplained_message_differences": [],
            "records": [],
            "latency": {},
            "reconnects": {},
            "resource_snapshot": {},
            "counters": {"pending_at_shutdown": 0},
        }

    monkeypatch.setattr(replay, "_load", lambda *args, **kwargs: [
        {"source_row_index": 0, "ts": 1.0, "token": "A", "ltp": 100.0, "vol": 1.0, "oi": 2.0},
    ])
    monkeypatch.setattr(replay, "_capture_timestamp_fidelity", lambda rows: {"summary": {"pass": True}, "rows": []})
    monkeypatch.setattr(replay, "_run_once", _fake_run_once)
    monkeypatch.setattr(replay.tick_store, "reset_audit_counters", lambda: None)
    monkeypatch.setattr(replay.tick_store, "flush_pending_ticks", lambda *args, **kwargs: 0)
    monkeypatch.setattr(replay.tick_store, "shutdown_persistence_worker", lambda: None)
    monkeypatch.setattr(replay.tick_store, "pending_tick_count", lambda: 0)
    monkeypatch.setattr(replay.collector, "reset", lambda enabled=True: None)
    monkeypatch.setattr(replay, "_sha", lambda path: "sha")
    monkeypatch.setattr(replay, "_atomic_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(replay.subprocess, "check_output", lambda *args, **kwargs: "deadbeef\n")
    monkeypatch.setattr(replay.platform, "platform", lambda: "test-platform")
    monkeypatch.setattr(replay.Path, "is_file", lambda self: True)
    monkeypatch.setattr(replay.Path, "resolve", lambda self: self)
    monkeypatch.setattr(replay.sys, "argv", [
        "run_feed_robustness_replay.py",
        "--input", str(tmp_path / "input.parquet"),
        "--output-dir", str(tmp_path / "out"),
        "--iterations", "1",
        "--max-rows", "10",
        "--session-cycles", "0",
        "--scenario", "normal_speed",
        "--persistence-mode", "async_queue",
    ])

    exit_code = replay.main()
    assert exit_code == 0
    assert captured["kwargs"]["selected_persistence_mode"] == "async_queue"


def test_runner_rejects_unknown_scenario():
    parser = replay.argparse.ArgumentParser()
    with pytest.raises(SystemExit):
        replay._select_scenarios({}, ["unknown"], parser)


def test_runner_rejects_unknown_persistence_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(replay.sys, "argv", [
        "run_feed_robustness_replay.py",
        "--input", str(tmp_path / "input.parquet"),
        "--output-dir", str(tmp_path / "out"),
        "--persistence-mode", "bogus",
    ])
    with pytest.raises(SystemExit):
        replay.main()
