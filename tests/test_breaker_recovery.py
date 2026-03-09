from __future__ import annotations

from core.breakers.breaker import BreakerConfig, BreakerState, BreakerSuite, RollingErrorRateBreaker


def _cfg(name: str) -> BreakerConfig:
    return BreakerConfig(
        name=name,
        window_sec=10.0,
        min_samples=4,
        trip_error_rate=0.5,
        cooldown_sec=3.0,
        recovery_healthy_ticks=3,
    )


def test_breaker_trips_on_rolling_error_rate_and_blocks_approvals() -> None:
    breaker = RollingErrorRateBreaker(_cfg("stale_feed_breaker"))

    # 3/4 errors => 0.75 > 0.5 threshold
    breaker.observe(True, now_ts=0.0)
    breaker.observe(True, now_ts=1.0)
    breaker.observe(False, now_ts=2.0)
    event = breaker.observe(True, now_ts=3.0)

    assert event["action"] == "TRIPPED"
    assert breaker.state == BreakerState.TRIPPED
    assert breaker.approvals_blocked is True


def test_breaker_transitions_to_recovering_and_clears_after_healthy_ticks() -> None:
    breaker = RollingErrorRateBreaker(_cfg("price_mismatch_breaker"))

    # Trip it first.
    breaker.observe(True, now_ts=0.0)
    breaker.observe(True, now_ts=1.0)
    breaker.observe(False, now_ts=2.0)
    breaker.observe(True, now_ts=3.0)
    assert breaker.state == BreakerState.TRIPPED

    # Cooldown not elapsed -> remain tripped.
    event = breaker.observe(False, now_ts=4.0)
    assert event["state"] == BreakerState.TRIPPED.value

    # Cooldown elapsed and healthy tick -> RECOVERING.
    event = breaker.observe(False, now_ts=6.5)
    assert event["action"] == "RECOVERING"
    assert breaker.state == BreakerState.RECOVERING

    # Enough healthy ticks -> HEALTHY.
    breaker.observe(False, now_ts=7.0)
    event = breaker.observe(False, now_ts=8.0)
    assert event["action"] == "CLEARED"
    assert breaker.state == BreakerState.HEALTHY
    assert breaker.approvals_blocked is False


def test_breaker_retrips_when_error_occurs_during_recovery() -> None:
    breaker = RollingErrorRateBreaker(_cfg("broker_failure_breaker"))
    breaker.observe(True, now_ts=0.0)
    breaker.observe(True, now_ts=1.0)
    breaker.observe(False, now_ts=2.0)
    breaker.observe(True, now_ts=3.0)
    assert breaker.state == BreakerState.TRIPPED

    breaker.observe(False, now_ts=6.5)  # -> recovering
    assert breaker.state == BreakerState.RECOVERING

    event = breaker.observe(True, now_ts=7.0)
    assert event["action"] == "RETRIPPED"
    assert breaker.state == BreakerState.TRIPPED
    assert breaker.approvals_blocked is True


def test_suite_blocks_when_any_breaker_is_tripped() -> None:
    suite = BreakerSuite(
        stale_feed_config=_cfg("stale_feed_breaker"),
        price_mismatch_config=_cfg("price_mismatch_breaker"),
        broker_failure_config=_cfg("broker_failure_breaker"),
    )

    # Trip only stale-feed breaker.
    suite.observe_stale_feed(True, now_ts=0.0)
    suite.observe_stale_feed(True, now_ts=1.0)
    suite.observe_stale_feed(False, now_ts=2.0)
    suite.observe_stale_feed(True, now_ts=3.0)

    blocked, blockers = suite.should_block_new_trade_approvals(now_ts=3.1)
    assert blocked is True
    assert "stale_feed_breaker" in blockers
    assert "price_mismatch_breaker" not in blockers
