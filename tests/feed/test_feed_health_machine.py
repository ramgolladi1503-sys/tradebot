from __future__ import annotations

from dataclasses import dataclass

from core.feed.health import FeedHealthMachine
from core.feed.metrics import FeedGroupMetrics
from core.feed.types import FeedGroupKey, FeedState, FeedThresholds


@dataclass
class _FakeClock:
    now: float = 0.0

    def now_fn(self) -> float:
        return float(self.now)

    def advance(self, sec: float) -> float:
        self.now += float(sec)
        return self.now


def _index_thresholds(**overrides) -> FeedThresholds:
    base = FeedThresholds(
        ok_age_p95=2.0,
        deg_age_p95=5.0,
        down_age_p95=20.0,
        downgrade_window_sec=10.0,
        upgrade_window_sec=20.0,
        min_hold_sec=0.0,
        ws_down_age_sec=30.0,
        flap_window_sec=300.0,
        flap_max_transitions=3,
        flap_lock_sec=300.0,
    )
    data = dict(base.__dict__)
    data.update(overrides)
    return FeedThresholds(**data)


def _option_thresholds(**overrides) -> FeedThresholds:
    base = FeedThresholds(
        ok_age_p95=3.0,
        deg_age_p95=7.0,
        down_age_p95=10.0,
        ok_spread_p95=0.0035,
        deg_spread_p95=0.0060,
        ok_depth_missing_pct=20.0,
        deg_depth_missing_pct=40.0,
        downgrade_window_sec=10.0,
        upgrade_window_sec=20.0,
        min_hold_sec=0.0,
        ws_down_age_sec=15.0,
        flap_window_sec=300.0,
        flap_max_transitions=3,
        flap_lock_sec=300.0,
    )
    data = dict(base.__dict__)
    data.update(overrides)
    return FeedThresholds(**data)


def _update(machine: FeedHealthMachine, key: FeedGroupKey, metrics: FeedGroupMetrics) -> dict:
    return machine.update_group(key, metrics.snapshot())


def test_ok_to_degraded_downgrade_window():
    clock = _FakeClock(now=0.0)
    key = FeedGroupKey("INDEX:NIFTY")
    machine = FeedHealthMachine(
        {key: _index_thresholds(downgrade_window_sec=5.0)},
        now_fn=clock.now_fn,
    )
    metrics = FeedGroupMetrics(now_fn=clock.now_fn)

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    first = _update(machine, key, metrics)
    assert first["state"] == FeedState.OK

    clock.advance(3.0)
    still_ok = _update(machine, key, metrics)
    assert still_ok["state"] == FeedState.OK

    clock.advance(4.0)
    still_ok_2 = _update(machine, key, metrics)
    assert still_ok_2["state"] == FeedState.OK

    clock.advance(1.0)
    degraded = _update(machine, key, metrics)
    assert degraded["state"] == FeedState.DEGRADED
    assert degraded["execution_allowed"] is False


def test_degraded_to_ok_upgrade_window():
    clock = _FakeClock(now=0.0)
    key = FeedGroupKey("INDEX:NIFTY")
    thresholds = _index_thresholds(downgrade_window_sec=2.0, upgrade_window_sec=2.0)
    machine = FeedHealthMachine({key: thresholds}, now_fn=clock.now_fn)
    metrics = FeedGroupMetrics(now_fn=clock.now_fn)

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(3.0)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(2.0)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED
    clock.advance(1.0)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED

    clock.advance(1.0)
    recovered = _update(machine, key, metrics)
    assert recovered["state"] == FeedState.OK
    assert recovered["execution_allowed"] is True


def test_degraded_to_down_on_ws_age():
    clock = _FakeClock(now=0.0)
    key = FeedGroupKey("INDEX:NIFTY")
    thresholds = _index_thresholds(
        downgrade_window_sec=2.0,
        ws_down_age_sec=8.0,
        down_age_p95=100.0,
    )
    machine = FeedHealthMachine({key: thresholds}, now_fn=clock.now_fn)
    metrics = FeedGroupMetrics(now_fn=clock.now_fn)

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(3.0)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(2.0)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED

    clock.advance(4.0)  # ws_age now 9s => down condition starts
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED

    clock.advance(2.0)  # down condition held for downgrade window
    assert _update(machine, key, metrics)["state"] == FeedState.DOWN


def test_down_to_degraded_then_ok_requires_sustained_recovery():
    clock = _FakeClock(now=0.0)
    key = FeedGroupKey("INDEX:NIFTY")
    thresholds = _index_thresholds(
        downgrade_window_sec=2.0,
        upgrade_window_sec=5.0,
        ws_down_age_sec=4.0,
        down_age_p95=5.0,
        flap_max_transitions=10,
    )
    machine = FeedHealthMachine({key: thresholds}, now_fn=clock.now_fn)
    metrics = FeedGroupMetrics(now_fn=clock.now_fn)

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(6.0)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(2.0)
    assert _update(machine, key, metrics)["state"] == FeedState.DOWN

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DOWN

    # Maintain sustained healthy observations while in DOWN.
    # DOWN -> DEGRADED requires at least 30s of deg_conditions.
    transitioned_to_degraded = False
    for _ in range(8):
        clock.advance(4.0)
        metrics.observe_ws(ts=clock.now)
        metrics.observe_tick("t1", ts=clock.now)
        state = _update(machine, key, metrics)["state"]
        if state == FeedState.DEGRADED:
            transitioned_to_degraded = True
            break
    assert transitioned_to_degraded is True

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED

    clock.advance(3.0)
    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED

    clock.advance(3.0)
    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.OK


def test_flap_lock_prevents_upgrade():
    clock = _FakeClock(now=0.0)
    key = FeedGroupKey("INDEX:NIFTY")
    thresholds = _index_thresholds(
        ok_age_p95=1.0,
        deg_age_p95=5.0,
        down_age_p95=50.0,
        downgrade_window_sec=1.0,
        upgrade_window_sec=1.0,
        flap_window_sec=10.0,
        flap_max_transitions=3,
        flap_lock_sec=20.0,
    )
    machine = FeedHealthMachine({key: thresholds}, now_fn=clock.now_fn)
    metrics = FeedGroupMetrics(now_fn=clock.now_fn)

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(2.0)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(1.0)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED  # transition 1

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED
    clock.advance(1.0)
    assert _update(machine, key, metrics)["state"] == FeedState.OK  # transition 2

    clock.advance(2.0)
    assert _update(machine, key, metrics)["state"] == FeedState.OK

    clock.advance(1.0)
    third = _update(machine, key, metrics)  # transition 3 => flap lock
    assert third["state"] == FeedState.DEGRADED
    assert third["flap_locked"] is True

    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED
    clock.advance(2.0)
    blocked = _update(machine, key, metrics)
    assert blocked["state"] == FeedState.DEGRADED
    assert blocked["flap_locked"] is True

    clock.advance(25.0)
    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick("t1", ts=clock.now)
    assert _update(machine, key, metrics)["state"] == FeedState.DEGRADED
    clock.advance(1.0)
    unlocked = _update(machine, key, metrics)
    assert unlocked["state"] == FeedState.OK
    assert unlocked["flap_locked"] is False


def test_per_group_isolation_options_down_index_ok():
    clock = _FakeClock(now=0.0)
    idx = FeedGroupKey("INDEX:NIFTY")
    opt = FeedGroupKey("OPT:NIFTY")
    machine = FeedHealthMachine(
        {
            idx: _index_thresholds(),
            opt: _option_thresholds(),
        },
        now_fn=clock.now_fn,
    )
    idx_metrics = FeedGroupMetrics(now_fn=clock.now_fn)
    opt_metrics = FeedGroupMetrics(now_fn=clock.now_fn)

    idx_metrics.observe_ws(ts=clock.now)
    idx_metrics.observe_tick("idx", ts=clock.now)
    idx_state = _update(machine, idx, idx_metrics)
    assert idx_state["state"] == FeedState.OK

    opt_metrics.observe_ws(ts=clock.now)
    opt_metrics.observe_tick("opt", ts=clock.now)
    clock.advance(11.0)
    opt_state = _update(machine, opt, opt_metrics)
    assert opt_state["state"] == FeedState.DOWN

    idx_metrics.observe_ws(ts=clock.now)
    idx_metrics.observe_tick("idx", ts=clock.now)
    idx_state2 = _update(machine, idx, idx_metrics)
    assert idx_state2["state"] == FeedState.OK
    assert idx_state2["execution_allowed"] is True
    assert opt_state["execution_allowed"] is False
