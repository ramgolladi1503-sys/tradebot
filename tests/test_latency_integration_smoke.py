from core.latency_guard import ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL, LatencyGuard
from core.latency_monitor import LatencyMonitor


def _run_loop_with_injected_decision_latency(decision_latency_ms):
    monitor = LatencyMonitor(
        window_size=64,
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=2,
    )
    guard = LatencyGuard(
        max_p95_total_ms=120.0,
        max_p95_decision_ms=80.0,
        sustained_windows=2,
        cooldown_sec=0.0,
        halt_on_breach=False,
    )
    blocked = []
    actions = []
    now_ts = 1_700_000_000.0
    for dt in decision_latency_ms:
        monitor.record("feature_build", 10.0)
        monitor.record("decision_build", float(dt))
        monitor.record("execution_route", 8.0)
        stats = monitor.tick_end(float(dt + 24.0))
        result = guard.evaluate(stats, market_open=True, now_ts=now_ts)
        now_ts += 1.0
        blocked.append(bool(result.blocks_new_entries))
        actions.append(str(result.action))
    return blocked, actions


def test_latency_integration_smoke_blocks_entries_on_slow_stage():
    blocked, actions = _run_loop_with_injected_decision_latency(
        [18.0, 20.0, 145.0, 150.0, 155.0]
    )
    assert any(blocked), "latency guard never blocked entries under sustained slow stage"
    assert actions[-1] in {ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL}
