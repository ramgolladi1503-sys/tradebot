from __future__ import annotations

from pathlib import Path

from core.torture_test import TortureTestRunner


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

    runner = TortureTestRunner(latency_threshold_ms=100.0)
    summary = runner.run_scenario("market_open_spike", "DEFAULT")
    _assert_common(summary)


def test_torture_replay_feed_flap_partial_data(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    runner = TortureTestRunner(latency_threshold_ms=100.0)
    summary = runner.run_scenario("feed_flap_partial_data", "DEFAULT")
    _assert_common(summary)
