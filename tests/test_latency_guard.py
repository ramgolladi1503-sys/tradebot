from core.latency_guard import (
    ACTION_COOLDOWN,
    ACTION_DEGRADE_EXIT_ONLY,
    ACTION_HALT_ALL,
    ACTION_OK,
    LatencyGuard,
)
from core.latency_monitor import LatencyMonitor


def _build_monitor_with_samples(*, total_ms: float, decision_ms: float, windows: int = 3):
    monitor = LatencyMonitor(
        window_size=32,
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=windows,
    )
    stats = {}
    for _ in range(windows):
        monitor.record("feature_build", 8.0)
        monitor.record("decision_build", decision_ms)
        monitor.record("execution_route", 6.0)
        stats = monitor.tick_end(total_ms)
    return monitor, stats


def test_latency_guard_ok_under_budget():
    _monitor, stats = _build_monitor_with_samples(total_ms=40.0, decision_ms=12.0)
    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=True,
    )
    out = guard.evaluate(stats, market_open=True, now_ts=100.0)
    assert out.action == ACTION_OK
    assert out.blocks_new_entries is False


def test_latency_guard_degrade_on_sustained_breach():
    _monitor, stats = _build_monitor_with_samples(total_ms=180.0, decision_ms=90.0)
    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=False,
    )
    out = guard.evaluate(stats, market_open=True, now_ts=100.0)
    assert out.action == ACTION_DEGRADE_EXIT_ONLY
    assert out.blocks_new_entries is True
    assert out.blocks_non_emergency_exits is False


def test_latency_guard_halt_on_severe_breach():
    _monitor, stats = _build_monitor_with_samples(total_ms=310.0, decision_ms=180.0)
    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=True,
    )
    out = guard.evaluate(stats, market_open=True, now_ts=100.0)
    assert out.action == ACTION_HALT_ALL
    assert out.blocks_new_entries is True
    assert out.blocks_non_emergency_exits is True


def test_latency_guard_halt_remains_sticky_until_recovery_windows():
    _monitor, breach_stats = _build_monitor_with_samples(total_ms=310.0, decision_ms=180.0)
    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=True,
    )

    out1 = guard.evaluate(breach_stats, market_open=True, now_ts=100.0)
    out2 = guard.evaluate(breach_stats, market_open=True, now_ts=105.0)
    out3 = guard.evaluate(breach_stats, market_open=True, now_ts=111.0)

    assert out1.action == ACTION_HALT_ALL
    assert out2.action == ACTION_HALT_ALL
    assert out3.action == ACTION_HALT_ALL
    assert out3.blocks_non_emergency_exits is True


def test_latency_guard_clears_halt_only_after_consecutive_healthy_recovery_windows():
    _monitor, breach_stats = _build_monitor_with_samples(total_ms=310.0, decision_ms=180.0)
    _healthy_monitor, healthy_stats = _build_monitor_with_samples(total_ms=42.0, decision_ms=24.0)
    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=True,
    )

    out1 = guard.evaluate(breach_stats, market_open=True, now_ts=100.0)
    out2 = guard.evaluate(healthy_stats, market_open=True, now_ts=111.0)
    out3 = guard.evaluate(healthy_stats, market_open=True, now_ts=112.0)
    out4 = guard.evaluate(healthy_stats, market_open=True, now_ts=113.0)

    assert out1.action == ACTION_HALT_ALL
    assert out2.action == ACTION_HALT_ALL
    assert out3.action == ACTION_HALT_ALL
    assert out4.action == ACTION_OK


def test_latency_guard_cooldown_on_transient_breach():
    monitor = LatencyMonitor(
        window_size=32,
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
    )
    monitor.record("feature_build", 8.0)
    monitor.record("decision_build", 20.0)
    monitor.record("execution_route", 5.0)
    monitor.tick_end(36.0)
    monitor.record("feature_build", 8.0)
    monitor.record("decision_build", 82.0)
    monitor.record("execution_route", 5.0)
    stats = monitor.tick_end(130.0)

    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=False,
    )
    out1 = guard.evaluate(stats, market_open=True, now_ts=200.0)
    out2 = guard.evaluate(stats, market_open=True, now_ts=205.0)
    assert out1.action == ACTION_COOLDOWN
    assert out2.action == ACTION_COOLDOWN


def test_latency_guard_ignores_background_overhead_when_guard_metric_stays_healthy():
    monitor = LatencyMonitor(
        window_size=32,
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
    )
    stats = {}
    for _ in range(3):
        monitor.record("feature_build", 10.0)
        monitor.record("decision_build", 24.0)
        monitor.record("execution_route", 8.0)
        stats = monitor.tick_end(42.0)
    stats["cycle"] = {
        "critical_path_ms": 42.0,
        "full_cycle_ms": 360.0,
        "background_overhead_ms": 318.0,
        "guard_total_ms": 42.0,
        "guard_uses_critical_path": True,
    }

    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=3,
        cooldown_sec=10.0,
        halt_on_breach=True,
    )
    out = guard.evaluate(stats, market_open=True, now_ts=300.0)
    assert out.action == ACTION_OK
    assert out.blocks_new_entries is False
