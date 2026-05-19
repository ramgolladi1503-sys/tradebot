from __future__ import annotations

from pathlib import Path

from core.torture_test import TortureTestRunner

CI_SAFE_LATENCY_THRESHOLD_MS = 750.0


def _assert_common(summary: dict):
    assert summary["status"] == "PASS"
    assert int(summary["metrics"]["exception_count"]) == 0
    assert int(summary["metrics"]["event_count"]) > 0
    assert int(summary["metrics"]["partial_trade_creation_count"]) == 0
    report_path = Path(str(summary.get("report_path") or ""))
    assert report_path.exists()


def test_torture_replay_market_open_spike(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    runner = TortureTestRunner(latency_threshold_ms=CI_SAFE_LATENCY_THRESHOLD_MS)
    summary = runner.run_scenario("market_open_spike", "DEFAULT")
    _assert_common(summary)


def test_torture_replay_feed_flap_partial_data(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    runner = TortureTestRunner(latency_threshold_ms=CI_SAFE_LATENCY_THRESHOLD_MS)
    summary = runner.run_scenario("feed_flap_partial_data", "DEFAULT")
    _assert_common(summary)


def test_torture_replay_long_run_stability(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    runner = TortureTestRunner(latency_threshold_ms=CI_SAFE_LATENCY_THRESHOLD_MS)
    summary = runner.run_scenario("long_run_stability", "DEFAULT")
    _assert_common(summary)
    metrics = dict(summary.get("metrics") or {})
    assert int(metrics.get("simulated_minutes") or 0) == 360
    assert int(metrics.get("rotation_cap_bytes") or 0) > 0
    assert int(metrics.get("rotation_max_file_size_bytes") or 0) <= int(metrics.get("rotation_cap_bytes") or 0)
    assert int(metrics.get("max_bounded_buffer_observed") or 0) <= int(metrics.get("bounded_buffer_limit") or 0)


def test_torture_replay_fault_injection_fail_closed_and_integrity(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    runner = TortureTestRunner(latency_threshold_ms=CI_SAFE_LATENCY_THRESHOLD_MS)
    summary = runner.run_scenario("fault_injection", "DEFAULT")
    _assert_common(summary)
    metrics = dict(summary.get("metrics") or {})
    assert int(metrics.get("injected_feed_latency_spikes") or 0) > 0
    assert int(metrics.get("injected_missing_depth") or 0) > 0
    assert int(metrics.get("injected_order_rejections") or 0) > 0
    assert int(metrics.get("injected_db_write_failures") or 0) > 0
    assert int(metrics.get("fail_closed_blocks") or 0) >= int(metrics.get("injected_order_rejections") or 0)
    assert int(metrics.get("unsafe_order_attempts") or 0) == 0
    assert bool(metrics.get("events_integrity_ok")) is True
    assert int(metrics.get("events_bad_lines") or 0) == 0
    assert bool(metrics.get("events_truncated_tail")) is False