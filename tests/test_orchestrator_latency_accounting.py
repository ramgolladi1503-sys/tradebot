import pytest

import core.orchestrator as orch_mod
from core.latency_monitor import LatencyMonitor


def _make_monitor() -> LatencyMonitor:
    return LatencyMonitor(
        window_size=32,
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
    )


def test_build_cycle_latency_snapshot_prefers_critical_path_for_guard(monkeypatch):
    monitor = _make_monitor()
    monkeypatch.setattr(orch_mod.time, "perf_counter", lambda: 10.40)

    stats = orch_mod._build_cycle_latency_snapshot(
        latency_monitor=monitor,
        cycle_perf_start=10.00,
        critical_path_end_perf=10.06,
        feature_build_ms=12.0,
        decision_build_ms=18.0,
        execution_route_ms=9.0,
        use_critical_path_only=True,
    )

    cycle = stats["cycle"]
    assert cycle["critical_path_ms"] == pytest.approx(60.0)
    assert cycle["full_cycle_ms"] == pytest.approx(400.0)
    assert cycle["background_overhead_ms"] == pytest.approx(340.0)
    assert cycle["guard_total_ms"] == pytest.approx(60.0)
    assert cycle["guard_uses_critical_path"] is True
    assert stats["stages"]["total_loop"]["p95_ms"] == pytest.approx(60.0)


def test_build_cycle_latency_snapshot_can_use_full_cycle_for_guard(monkeypatch):
    monitor = _make_monitor()
    monkeypatch.setattr(orch_mod.time, "perf_counter", lambda: 21.20)

    stats = orch_mod._build_cycle_latency_snapshot(
        latency_monitor=monitor,
        cycle_perf_start=20.00,
        critical_path_end_perf=20.08,
        feature_build_ms=10.0,
        decision_build_ms=20.0,
        execution_route_ms=6.0,
        use_critical_path_only=False,
    )

    cycle = stats["cycle"]
    assert cycle["critical_path_ms"] == pytest.approx(80.0)
    assert cycle["full_cycle_ms"] == pytest.approx(1200.0)
    assert cycle["background_overhead_ms"] == pytest.approx(1120.0)
    assert cycle["guard_total_ms"] == pytest.approx(1200.0)
    assert cycle["guard_uses_critical_path"] is False
    assert stats["stages"]["total_loop"]["p95_ms"] == pytest.approx(1200.0)


def test_latency_budget_config_uses_live_specific_thresholds(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "LIVE_MAX_P95_TOTAL_MS", 8000.0, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "LIVE_MAX_P95_DECISION_MS", 3000.0, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "LIVE_SUSTAINED_WINDOWS", 5, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "LIVE_EXIT_ONLY_COOLDOWN_S", 45.0, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "LIVE_HALT_ON_BREACH", False, raising=False)

    budget = orch_mod._latency_budget_config(execution_mode="LIVE")

    assert budget["scope"] == "live"
    assert budget["max_p95_total_ms"] == pytest.approx(8000.0)
    assert budget["max_p95_decision_ms"] == pytest.approx(3000.0)
    assert budget["sustained_windows"] == 5
    assert budget["cooldown_sec"] == pytest.approx(45.0)
    assert budget["halt_on_breach"] is False


def test_latency_budget_config_preserves_default_thresholds_for_non_live(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "MAX_P95_TOTAL_MS", 120.0, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "MAX_P95_DECISION_MS", 80.0, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "SUSTAINED_WINDOWS", 3, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "EXIT_ONLY_COOLDOWN_S", 30.0, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "HALT_ON_BREACH", True, raising=False)

    budget = orch_mod._latency_budget_config(execution_mode="SIM")

    assert budget["scope"] == "default"
    assert budget["max_p95_total_ms"] == pytest.approx(120.0)
    assert budget["max_p95_decision_ms"] == pytest.approx(80.0)
    assert budget["sustained_windows"] == 3
    assert budget["cooldown_sec"] == pytest.approx(30.0)
    assert budget["halt_on_breach"] is True


def test_latency_skip_trade_builder_enabled_for_live_guard(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "LATENCY_GUARD_LIVE_SKIP_TRADE_BUILDER", True, raising=False)

    assert (
        orch_mod._should_skip_trade_builder_for_latency_guard(
            latency_soften_active=True,
            execution_mode="LIVE",
        )
        is True
    )


def test_latency_skip_trade_builder_disabled_for_paper(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "LATENCY_GUARD_LIVE_SKIP_TRADE_BUILDER", True, raising=False)

    assert (
        orch_mod._should_skip_trade_builder_for_latency_guard(
            latency_soften_active=True,
            execution_mode="PAPER",
        )
        is False
    )
