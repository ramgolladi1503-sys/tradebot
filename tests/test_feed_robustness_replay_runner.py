from __future__ import annotations

import sqlite3
import time

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
            "shutdown_state", "shutdown_started_monotonic_ns", "shutdown_finished_monotonic_ns",
            "writes_rejected_after_shutdown", "last_accepted_enqueue_monotonic_ns",
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
    monkeypatch.setattr(replay.tick_store, "shutdown_persistence_worker", lambda **kwargs: None)
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


def test_pressure_controller_is_disabled_by_default():
    controller = replay._ReplayPressureController(profile="none")
    assert controller.enabled is False
    assert controller.profile == "none"


def test_pressure_queue_threshold_treats_unbounded_queue_as_backlog_100():
    assert replay._pressure_queue_threshold() == 100


def test_constant_delay_pressure_hook_records_worker_side_delay(monkeypatch):
    controller = replay._ReplayPressureController(profile="constant_delay", delay_before_each_commit_ms=1)
    slept = []
    monkeypatch.setattr(replay.time, "sleep", lambda seconds: slept.append(seconds))

    before = time.monotonic_ns()
    controller.maybe_pause_before_commit({"rows_dequeued": 1, "rows_enqueued": 1})
    after = time.monotonic_ns()

    assert slept == [pytest.approx(0.001)]
    assert controller.worker_lifecycle[0]["stage"] == "hook_start"
    assert controller.worker_lifecycle[1]["stage"] == "stall_start"
    assert controller.worker_lifecycle[2]["stage"] == "hook_end"
    assert controller.worker_lifecycle[3]["stage"] == "stall_end"
    assert after >= before


def test_intermittent_stall_triggers_only_on_configured_dequeue_boundary(monkeypatch):
    controller = replay._ReplayPressureController(
        profile="intermittent_stall",
        stall_after_each_dequeued_rows=10,
        stall_duration_ms=2,
    )
    slept = []
    monkeypatch.setattr(replay.time, "sleep", lambda seconds: slept.append(seconds))

    controller.maybe_pause_before_commit({"rows_dequeued": 9, "rows_enqueued": 9})
    assert slept == []
    controller.maybe_pause_before_commit({"rows_dequeued": 10, "rows_enqueued": 10})

    assert slept == [pytest.approx(0.002)]
    assert controller.worker_lifecycle[0]["stage"] == "hook_start"
    assert controller.worker_lifecycle[1]["stage"] == "stall_start"
    assert controller.worker_lifecycle[2]["stage"] == "hook_end"
    assert controller.worker_lifecycle[3]["stage"] == "stall_end"


def test_pressure_profile_cannot_be_enabled_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADEBOT_FEED_FD_TRACE", "1")
    monkeypatch.setenv("TRADEBOT_FEED_PRESSURE_PROFILE", "constant_delay")
    monkeypatch.setenv("TICK_STORE_PRESSURE_PROFILE", "intermittent_stall")

    captured = []

    monkeypatch.setattr(replay, "_load", lambda *args, **kwargs: [
        {"source_row_index": 0, "ts": 1.0, "token": "A", "ltp": 100.0, "vol": 1.0, "oi": 2.0},
    ])
    monkeypatch.setattr(replay, "_capture_timestamp_fidelity", lambda rows: {"summary": {"pass": True}, "rows": []})
    monkeypatch.setattr(replay, "_run_once", lambda rows, scenario, seed, **kwargs: captured.append(kwargs.get("pressure_controller")) or {
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
    monkeypatch.setattr(replay.tick_store, "shutdown_persistence_worker", lambda **kwargs: None)
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
        "--max-rows", "1",
        "--session-cycles", "0",
        "--scenario", "normal_speed",
    ])

    exit_code = replay.main()
    assert exit_code == 0
    assert captured == [None]


def test_pressure_profile_records_real_async_persistence_and_shutdown_drain(monkeypatch, tmp_path):
    rows = [
        {"source_row_index": i, "ts": float(1_000 + i), "token": "A", "ltp": 100.0 + i, "vol": 1.0, "oi": 2.0}
        for i in range(12)
    ]
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.time, "sleep", lambda *_args, **_kwargs: None)

    controller = replay._ReplayPressureController(
        profile="constant_delay",
        delay_before_each_commit_ms=1,
        expected_total_rows=len(rows),
    )
    report = replay._run_once(
        rows,
        "normal_speed",
        seed=0,
        synchronous=False,
        speed_factor=1.0,
        batch_size=3,
        trace_path=tmp_path / "fd_trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=controller,
    )

    worker = report["persistence_worker"]
    shutdown = report["shutdown_result"]
    drain = report["drain_report"]
    assert worker["worker_started"] == 1
    assert worker["worker_failures"] == 0
    assert worker["rows_enqueued"] == len(rows)
    assert worker["rows_dequeued"] == len(rows)
    assert worker["committed_batches"] > 0
    assert worker["committed_rows"] == len(rows)
    assert worker["queue_depth_high_water"] > 1
    assert worker["queue_depth_at_shutdown"] == 0
    assert worker["pending_writes_at_shutdown"] == 0
    assert shutdown["status"] == "COMPLETE_DRAIN"
    assert shutdown["deadline_expired"] is False
    assert shutdown["worker_join_completed"] is True
    assert shutdown["worker_terminated"] is True
    assert shutdown["queue_depth"] == 0
    assert shutdown["pending_writes"] == 0
    assert drain["shutdown_status"] == "COMPLETE_DRAIN"
    assert drain["deadline_expired"] is False
    assert drain["actual_thread_join_duration_ns"] is not None
    assert drain["final_accounting_duration_ns"] is not None
    assert drain["rows_enqueued"] == len(rows)
    assert drain["rows_dequeued"] == len(rows)
    assert drain["rows_committed"] == len(rows)
    assert drain["pending_writes_at_shutdown"] == 0
    assert drain["worker_daemon"] is True
    assert report["pressure_profile"]["hook_invocation_count"] == worker["committed_batches"]
    assert report["pressure_profile"]["cumulative_requested_delay_ms"] == 1 * worker["committed_batches"]
    assert report["pressure_profile"]["max_pending_writes"] >= worker["queue_depth_high_water"]
    assert report["pressure_profile"]["hook_ordinal"] == report["pressure_profile"]["hook_invocation_count"]
    assert report["pressure_profile"]["worker_commit_hook_count"] == worker["committed_batches"]
    assert report["pressure_profile"]["committed_batch_count"] == worker["committed_batches"]
    post_commit = [entry for entry in report["worker_lifecycle"] if entry["stage"] == "post_commit"]
    assert sum(int(entry["batch_size"]) for entry in post_commit) == worker["committed_rows"]
    assert all(int(entry["configured_delay_ms"]) == 1 for entry in post_commit)
    stages = [entry["stage"] for entry in report["worker_lifecycle"]]
    for stage in ["shutdown_started", "stop_accepting_writes", "drain_started", "drain_completed", "worker_join_started", "worker_join_completed", "shutdown_completed"]:
        assert stage in stages
    timeline_stages = [entry["stage"] for entry in report["queue_depth_timeline"]]
    assert "producer_completed" in timeline_stages
    assert stages.index("shutdown_started") < stages.index("shutdown_completed")
    assert controller.hook_invocation_count == report["pressure_profile"]["hook_invocation_count"]
    with sqlite3.connect(str(db_path)) as conn:
        committed_rows = conn.execute("select count(*) from ticks").fetchone()[0]
    assert committed_rows == len(rows)


def test_pressure_profile_preserves_checksums_with_and_without_delay(monkeypatch, tmp_path):
    rows = [
        {"source_row_index": i, "ts": float(2_000 + i), "token": "A", "ltp": 200.0 + i, "vol": 2.0, "oi": 3.0}
        for i in range(8)
    ]
    monkeypatch.setattr(replay.time, "sleep", lambda *_args, **_kwargs: None)

    baseline_db_path = tmp_path / "baseline.sqlite"
    pressured_db_path = tmp_path / "pressured.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(baseline_db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(baseline_db_path), raising=False)
    baseline = replay._run_once(
        rows,
        "normal_speed",
        seed=1,
        synchronous=False,
        speed_factor=1.0,
        batch_size=2,
        trace_path=tmp_path / "baseline_trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=None,
    )
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(pressured_db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(pressured_db_path), raising=False)
    controller = replay._ReplayPressureController(
        profile="constant_delay",
        delay_before_each_commit_ms=1,
        expected_total_rows=len(rows),
    )
    pressured = replay._run_once(
        rows,
        "normal_speed",
        seed=1,
        synchronous=False,
        speed_factor=1.0,
        batch_size=2,
        trace_path=tmp_path / "pressured_trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=controller,
    )

    assert baseline["checksums"] == pressured["checksums"]
    assert [
        {
            "source_row_index": record["source_row_index"],
            "instrument_token": record["instrument_token"],
            "source_timestamp": record["source_timestamp"],
            "last_price": record["last_price"],
            "volume": record["volume"],
            "oi": record["oi"],
        }
        for record in baseline["records"]
    ] == [
        {
            "source_row_index": record["source_row_index"],
            "instrument_token": record["instrument_token"],
            "source_timestamp": record["source_timestamp"],
            "last_price": record["last_price"],
            "volume": record["volume"],
            "oi": record["oi"],
        }
        for record in pressured["records"]
    ]
    assert pressured["pressure_profile"]["max_pending_writes"] >= pressured["persistence_worker"]["queue_depth_high_water"]


def test_pressure_profile_intermittent_stall_uses_only_10k_to_90k_boundaries(monkeypatch):
    controller = replay._ReplayPressureController(
        profile="intermittent_stall",
        stall_after_each_dequeued_rows=10_000,
        stall_duration_ms=1,
        expected_total_rows=100_000,
    )
    slept = []
    monkeypatch.setattr(replay.time, "sleep", lambda seconds: slept.append(seconds))

    for dequeued_rows in range(10_000, 100_001, 10_000):
        controller.maybe_pause_before_commit({"rows_dequeued": dequeued_rows, "rows_enqueued": dequeued_rows})

    assert len(slept) == 9
    assert controller.hook_invocation_count == 9
    assert controller._stall_index == 9


def test_pressure_accounting_reports_max_pending_writes_and_batch_size(monkeypatch, tmp_path):
    rows = [
        {"source_row_index": i, "ts": float(3_000 + i), "token": "A", "ltp": 300.0 + i, "vol": 2.0, "oi": 4.0}
        for i in range(6)
    ]
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.time, "sleep", lambda *_args, **_kwargs: None)
    controller = replay._ReplayPressureController(profile="constant_delay", delay_before_each_commit_ms=1, expected_total_rows=len(rows))
    report = replay._run_once(
        rows,
        "normal_speed",
        seed=0,
        synchronous=False,
        speed_factor=1.0,
        batch_size=2,
        trace_path=tmp_path / "trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=controller,
    )

    profile = report["pressure_profile"]
    worker = report["persistence_worker"]
    assert profile["max_pending_writes"] >= worker["queue_depth_high_water"]
    assert profile["hook_invocation_count"] == worker["committed_batches"]
    assert profile["cumulative_requested_delay_ms"] == 1 * worker["committed_batches"]
    assert profile["hook_ordinal"] == profile["hook_invocation_count"]
    assert profile["max_pending_writes"] > 0
    assert any(entry["stage"] == "producer_completed" for entry in report["queue_depth_timeline"])
    assert any(entry["stage"] == "shutdown_started" for entry in report["worker_lifecycle"])
    worker_stages = [entry["stage"] for entry in report["worker_lifecycle"] if entry["stage"] in {"hook_start", "hook_end", "post_commit"}]
    assert worker_stages[:3] == ["hook_start", "hook_end", "post_commit"]


def test_pressure_hook_context_includes_batch_size(monkeypatch, tmp_path):
    rows = [
        {"source_row_index": i, "ts": float(4_000 + i), "token": "A", "ltp": 400.0 + i, "vol": 2.0, "oi": 4.0}
        for i in range(4)
    ]
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.time, "sleep", lambda *_args, **_kwargs: None)
    seen = []
    controller = replay._ReplayPressureController(profile="constant_delay", delay_before_each_commit_ms=1, expected_total_rows=len(rows))

    original = controller.maybe_pause_before_commit

    def wrapped(context):
        seen.append(dict(context))
        return original(context)

    controller.maybe_pause_before_commit = wrapped  # type: ignore[assignment]
    replay._run_once(
        rows,
        "normal_speed",
        seed=0,
        synchronous=False,
        speed_factor=1.0,
        batch_size=2,
        trace_path=tmp_path / "trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=controller,
    )

    assert seen
    assert all("batch_size" in item for item in seen)
    assert all(item["batch_size"] > 0 for item in seen)


def test_pressure_resource_timeline_records_pre_producer_and_post_join_samples(monkeypatch, tmp_path):
    rows = [
        {"source_row_index": i, "ts": float(5_000 + i), "token": "A", "ltp": 500.0 + i, "vol": 2.0, "oi": 4.0}
        for i in range(6)
    ]
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.time, "sleep", lambda *_args, **_kwargs: None)
    controller = replay._ReplayPressureController(profile="constant_delay", delay_before_each_commit_ms=1, expected_total_rows=len(rows))
    report = replay._run_once(
        rows,
        "normal_speed",
        seed=0,
        synchronous=False,
        speed_factor=1.0,
        batch_size=2,
        trace_path=tmp_path / "trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=controller,
    )

    kinds = [entry["kind"] for entry in report["resource_timeline"]]
    assert kinds[0] == "pre_producer_sample"
    assert "post_join_sample" in kinds
    assert len(kinds) >= 2
    assert len(report["resource_timeline"]) >= 2


def test_pressure_producer_completion_precedes_shutdown_and_join(monkeypatch, tmp_path):
    rows = [
        {"source_row_index": i, "ts": float(6_000 + i), "token": "A", "ltp": 600.0 + i, "vol": 2.0, "oi": 4.0}
        for i in range(6)
    ]
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.time, "sleep", lambda *_args, **_kwargs: None)
    controller = replay._ReplayPressureController(profile="constant_delay", delay_before_each_commit_ms=1, expected_total_rows=len(rows))
    replay._run_once(
        rows,
        "normal_speed",
        seed=0,
        synchronous=False,
        speed_factor=1.0,
        batch_size=2,
        trace_path=tmp_path / "trace.jsonl",
        selected_persistence_mode="async_queue",
        pressure_controller=controller,
    )

    producer_completed = next(entry["monotonic_ns"] for entry in controller.timeline if entry["stage"] == "producer_completed")
    shutdown_requested = next(entry["monotonic_ns"] for entry in controller.worker_lifecycle if entry["stage"] == "shutdown_started")
    worker_join_completed = next(entry["monotonic_ns"] for entry in controller.worker_lifecycle if entry["stage"] == "worker_join_completed")
    assert producer_completed < shutdown_requested < worker_join_completed


def test_pressure_write_failure_is_observable(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(replay.tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(replay.tick_store, "init_ticks", lambda: None)
    monkeypatch.setattr(replay.tick_store, "_conn", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    before = replay.tick_store.get_audit_counters()["worker_failures"]
    ok = replay.tick_store._write_rows(
        [("2026-07-09T03:56:45Z", 1, 100.0, 1.0, 2.0, 1.0, "2026-07-09T03:56:45Z")],
        worker_owned=True,
    )

    assert ok is False
    assert replay.tick_store.get_audit_counters()["worker_failures"] == before + 1
