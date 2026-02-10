from core.circuit_breaker import CircuitBreaker


def test_error_storm_triggers_circuit_breaker_halt():
    breaker = CircuitBreaker(
        error_threshold=3,
        error_window_sec=60.0,
        halt_sec=120.0,
        feed_unhealthy_sec=30.0,
    )

    tripped, reason = breaker.record_error("ERR_1", now=1000.0)
    assert tripped is False
    assert reason is None

    tripped, reason = breaker.record_error("ERR_2", now=1010.0)
    assert tripped is False
    assert reason is None

    tripped, reason = breaker.record_error("ERR_3", now=1020.0)
    assert tripped is True
    assert reason == "CB_ERROR_STORM"
    assert breaker.halt_reason == "CB_ERROR_STORM"
    assert breaker.is_halted(now=1030.0) is True

    state = breaker.state_dict(now=1030.0)
    assert state["halted"] is True
    assert state["halt_reason"] == "CB_ERROR_STORM"
    assert state["error_count_window"] == 3
