from __future__ import annotations

from core.observability import build_default_metrics_registry
from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots


def test_runtime_snapshot_producer_emits_stage_latency_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("REPO_LOG_DIR", str(tmp_path / "logs"))

    registry = build_default_metrics_registry()

    outputs = produce_and_store_runtime_snapshots(
        market_snapshot={"symbols": {}},
        producer="unit_test",
        loop_id="cycle-1",
        metrics_registry=registry,
    )

    assert outputs["runtime_cycle_context"]["cycle_id"] == "cycle-1"
    assert registry.get_value("tradebot_snapshot_producer_latency_ms", labels={"producer": "unit_test"}) >= 0.0
    assert registry.get_value(
        "tradebot_snapshot_stage_latency_ms",
        labels={"producer": "unit_test", "stage": "feed_health_truth"},
    ) >= 0.0


def test_snapshot_metrics_registry_renders_new_metrics():
    registry = build_default_metrics_registry()
    registry.observe_latency_ms("tradebot_snapshot_producer_latency_ms", 12.5, labels={"producer": "unit"})
    rendered = registry.render_prometheus()

    assert "tradebot_snapshot_producer_latency_ms" in rendered
    assert 'tradebot_snapshot_producer_latency_ms{producer="unit"} 12.5' in rendered
