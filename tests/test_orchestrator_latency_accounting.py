import pytest

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


def test_latency_skip_background_maintenance_for_live_guard(monkeypatch):
    monkeypatch.setattr(
        orch_mod.cfg,
        "LATENCY_GUARD_LIVE_SKIP_BACKGROUND_MAINTENANCE",
        True,
        raising=False,
    )

    assert (
        orch_mod._should_skip_background_maintenance_for_latency_guard(
            latency_action="halt_all",
            execution_mode="LIVE",
            feed_ok=True,
        )
        is True
    )


def test_latency_skip_background_maintenance_disabled_for_sim(monkeypatch):
    monkeypatch.setattr(
        orch_mod.cfg,
        "LATENCY_GUARD_LIVE_SKIP_BACKGROUND_MAINTENANCE",
        True,
        raising=False,
    )

    assert (
        orch_mod._should_skip_background_maintenance_for_latency_guard(
            latency_action="halt_all",
            execution_mode="SIM",
            feed_ok=False,
        )
        is False
    )


def test_latency_guard_evidence_reports_healthy_state_as_not_triggered(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    state = {
        "action": "OK",
        "reason": "latency_within_budget",
        "ts_epoch": 100.0,
    }
    stats = {
        "thresholds": {"max_p95_total_ms": 120.0, "max_p95_decision_ms": 80.0},
        "stages": {
            "total_loop": {"p95_ms": 42.0},
            "decision_build": {"p95_ms": 24.0},
        },
        "breach": {
            "p95_total_breach": False,
            "p95_decision_breach": False,
            "sustained_total_breach": False,
            "sustained_decision_breach": False,
        },
    }

    evidence = orch_mod._latency_guard_metric_context(state, stats)

    assert evidence["latency_guard_triggered"] is False
    assert evidence["latency_guard_action"] == "OK"
    assert evidence["latency_guard_reason"] == "latency_within_budget"
    assert evidence["latency_guard_metric"] is None
    assert evidence["latency_guard_value"] is None
    assert evidence["latency_guard_threshold"] is None
    assert evidence["latency_guard_recovery_required"] is False


def test_latency_guard_evidence_reports_degraded_state_with_metric_and_threshold(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    state = {
        "action": "DEGRADE_EXIT_ONLY",
        "reason": "latency_sustained_breach",
        "ts_epoch": 100.0,
    }
    stats = {
        "thresholds": {"max_p95_total_ms": 120.0, "max_p95_decision_ms": 80.0},
        "stages": {
            "total_loop": {"p95_ms": 180.0},
            "decision_build": {"p95_ms": 60.0},
        },
        "breach": {
            "p95_total_breach": True,
            "p95_decision_breach": False,
            "sustained_total_breach": True,
            "sustained_decision_breach": False,
        },
    }

    evidence = orch_mod._latency_guard_metric_context(state, stats)

    assert evidence["latency_guard_triggered"] is True
    assert evidence["latency_guard_action"] == "DEGRADE_EXIT_ONLY"
    assert evidence["latency_guard_reason"] == "latency_sustained_breach"
    assert evidence["latency_guard_source"] == "latency_monitor.stages.total_loop.p95_ms"
    assert evidence["latency_guard_metric"] == "total_loop.p95_ms"
    assert evidence["latency_guard_value"] == pytest.approx(180.0)
    assert evidence["latency_guard_threshold"] == pytest.approx(120.0)
    assert evidence["latency_guard_recovery_required"] is True


def test_latency_guard_evidence_fails_closed_when_state_is_unknown(monkeypatch):
    monkeypatch.setattr(orch_mod.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    evidence = orch_mod._latency_guard_metric_context({}, {})

    assert evidence["latency_guard_triggered"] is True
    assert evidence["latency_guard_reason"] == "latency_guard_state_unknown"
    assert evidence["latency_guard_source"] == "latency_guard_state"
    assert evidence["latency_guard_recovery_required"] is True
