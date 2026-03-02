from __future__ import annotations

from dataclasses import dataclass

from core.feed.gate import check_execution_allowed
from core.feed.runtime import build_default_feed_health, classify_group


@dataclass
class _FakeClock:
    now: float = 0.0

    def now_fn(self) -> float:
        return float(self.now)


def _attempt_execute(symbol: str, *, machine, metrics_map, broker_calls: dict) -> tuple[bool, str, str, dict]:
    allowed, reason, state, details = check_execution_allowed(
        symbol,
        machine=machine,
        metrics_map=metrics_map,
    )
    if allowed:
        broker_calls["count"] += 1
    return allowed, reason, state, details


def test_blocks_execution_when_feed_degraded():
    clock = _FakeClock(now=100.0)
    machine, metrics_map = build_default_feed_health(now_fn=clock.now_fn)
    group_key = classify_group("NIFTY")
    metrics = metrics_map[group_key]
    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick(token=101, ts=clock.now)
    metrics.observe_quote(
        token=101,
        bid=100.0,
        ask=100.2,
        ltp=100.1,
        ts=clock.now,
        depth_ok=True,
    )

    clock.now = 101.6  # INDEX ok threshold is 1.0s, down threshold is 3.0s.
    broker_calls = {"count": 0}
    allowed, reason, state, _ = _attempt_execute(
        "NIFTY",
        machine=machine,
        metrics_map=metrics_map,
        broker_calls=broker_calls,
    )
    assert allowed is False
    assert reason == "feed_state_DEGRADED"
    assert state == "DEGRADED"
    assert broker_calls["count"] == 0


def test_allows_execution_when_feed_ok():
    clock = _FakeClock(now=200.0)
    machine, metrics_map = build_default_feed_health(now_fn=clock.now_fn)
    group_key = classify_group("NIFTY")
    metrics = metrics_map[group_key]
    metrics.observe_ws(ts=clock.now)
    metrics.observe_tick(token=202, ts=clock.now)
    metrics.observe_quote(
        token=202,
        bid=99.9,
        ask=100.1,
        ltp=100.0,
        ts=clock.now,
        depth_ok=True,
    )

    clock.now = 200.2
    broker_calls = {"count": 0}
    allowed, reason, state, _ = _attempt_execute(
        "NIFTY",
        machine=machine,
        metrics_map=metrics_map,
        broker_calls=broker_calls,
    )
    assert allowed is True
    assert reason == "ok"
    assert state == "OK"
    assert broker_calls["count"] == 1


def test_unknown_group_fail_closed():
    clock = _FakeClock(now=300.0)
    machine, metrics_map = build_default_feed_health(now_fn=clock.now_fn)
    broker_calls = {"count": 0}

    allowed, reason, state, details = _attempt_execute(
        "WEIRD_SYMBOL_123",
        machine=machine,
        metrics_map=metrics_map,
        broker_calls=broker_calls,
    )
    assert allowed is False
    assert reason == "feed_state_UNKNOWN"
    assert state == "DOWN"
    assert "UNKNOWN" in str(details.get("group_key"))
    assert broker_calls["count"] == 0
