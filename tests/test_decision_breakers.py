from config import config as cfg
from core.decision_breakers import (
    BREAKER_BROKER_FAILURE,
    BREAKER_PRICE_MISMATCH_RATE,
    BREAKER_STALE_FEED,
    DecisionCircuitBreakers,
)


def _configure_for_test(monkeypatch):
    monkeypatch.setattr(cfg, "DECISION_BREAKERS_ENABLE", True)
    monkeypatch.setattr(cfg, "BREAKER_STALE_FEED_WINDOW_SEC", 20.0)
    monkeypatch.setattr(cfg, "BREAKER_STALE_FEED_MIN_SAMPLES", 3)
    monkeypatch.setattr(cfg, "BREAKER_STALE_FEED_TRIP_RATIO", 0.6)
    monkeypatch.setattr(cfg, "BREAKER_STALE_FEED_CLEAR_RATIO", 0.2)
    monkeypatch.setattr(cfg, "BREAKER_STALE_FEED_COOLDOWN_SEC", 10.0)
    monkeypatch.setattr(cfg, "BREAKER_PRICE_MISMATCH_WINDOW_SEC", 20.0)
    monkeypatch.setattr(cfg, "BREAKER_PRICE_MISMATCH_MIN_SAMPLES", 2)
    monkeypatch.setattr(cfg, "BREAKER_PRICE_MISMATCH_TRIP_RATIO", 0.5)
    monkeypatch.setattr(cfg, "BREAKER_PRICE_MISMATCH_CLEAR_RATIO", 0.1)
    monkeypatch.setattr(cfg, "BREAKER_PRICE_MISMATCH_COOLDOWN_SEC", 8.0)
    monkeypatch.setattr(cfg, "BREAKER_BROKER_FAILURE_WINDOW_SEC", 20.0)
    monkeypatch.setattr(cfg, "BREAKER_BROKER_FAILURE_MIN_SAMPLES", 2)
    monkeypatch.setattr(cfg, "BREAKER_BROKER_FAILURE_TRIP_RATIO", 0.5)
    monkeypatch.setattr(cfg, "BREAKER_BROKER_FAILURE_CLEAR_RATIO", 0.1)
    monkeypatch.setattr(cfg, "BREAKER_BROKER_FAILURE_COOLDOWN_SEC", 8.0)


def test_stale_feed_breaker_trips_blocks_then_clears(monkeypatch):
    _configure_for_test(monkeypatch)
    clock = {"t": 0.0}
    breakers = DecisionCircuitBreakers(now_fn=lambda: clock["t"])

    breakers.observe_stale_feed(True, now_ts=0.0)
    breakers.observe_stale_feed(True, now_ts=1.0)
    transitions = breakers.observe_stale_feed(False, now_ts=2.0)
    assert any(t.get("action") == "TRIPPED" and t.get("breaker") == BREAKER_STALE_FEED for t in transitions)

    blocked, reasons = breakers.should_block_decisions(now_ts=3.0)
    assert blocked is True
    assert BREAKER_STALE_FEED in reasons

    # After cooldown and healthy rolling window, breaker auto-clears.
    transitions = breakers.observe_stale_feed(False, now_ts=22.0)
    assert not any(t.get("action") == "CLEARED" for t in transitions)
    transitions = breakers.observe_stale_feed(False, now_ts=23.0)
    assert not any(t.get("action") == "CLEARED" for t in transitions)
    transitions = breakers.observe_stale_feed(False, now_ts=24.0)
    assert any(t.get("action") == "CLEARED" and t.get("breaker") == BREAKER_STALE_FEED for t in transitions)

    blocked, reasons = breakers.should_block_decisions(now_ts=25.0)
    assert blocked is False
    assert BREAKER_STALE_FEED not in reasons


def test_price_mismatch_rate_breaker_blocks_decisions(monkeypatch):
    _configure_for_test(monkeypatch)
    breakers = DecisionCircuitBreakers(now_fn=lambda: 0.0)

    breakers.observe_price_mismatch(True, now_ts=0.0)
    transitions = breakers.observe_price_mismatch(False, now_ts=1.0)
    assert any(
        t.get("action") == "TRIPPED" and t.get("breaker") == BREAKER_PRICE_MISMATCH_RATE
        for t in transitions
    )

    blocked, reasons = breakers.should_block_decisions(now_ts=2.0)
    assert blocked is True
    assert BREAKER_PRICE_MISMATCH_RATE in reasons

    snap = breakers.snapshot(now_ts=2.0)
    state = snap["breakers"][BREAKER_PRICE_MISMATCH_RATE]
    assert state["tripped"] is True
    assert isinstance(state["tripped_at"], float)
    assert state["cooldown_seconds"] > 0


def test_broker_failure_breaker_auto_recovers_after_healthy_window(monkeypatch):
    _configure_for_test(monkeypatch)
    breakers = DecisionCircuitBreakers(now_fn=lambda: 0.0)

    breakers.observe_broker_failure(True, now_ts=0.0)
    breakers.observe_broker_failure(True, now_ts=1.0)
    blocked, reasons = breakers.should_block_decisions(now_ts=1.0)
    assert blocked is True
    assert BREAKER_BROKER_FAILURE in reasons

    # Healthy signals over a fresh window after cooldown clear the breaker.
    breakers.observe_broker_failure(False, now_ts=22.0)
    transitions = breakers.observe_broker_failure(False, now_ts=23.0)
    if not any(t.get("action") == "CLEARED" for t in transitions):
        transitions = breakers.observe_broker_failure(False, now_ts=24.0)
    assert any(
        t.get("action") == "CLEARED" and t.get("breaker") == BREAKER_BROKER_FAILURE
        for t in transitions
    )
    blocked, reasons = breakers.should_block_decisions(now_ts=25.0)
    assert blocked is False
    assert BREAKER_BROKER_FAILURE not in reasons


def test_unknown_breaker_name_is_rejected_without_state_mutation(monkeypatch):
    _configure_for_test(monkeypatch)
    breakers = DecisionCircuitBreakers(now_fn=lambda: 10.0)
    before = breakers.snapshot(now_ts=10.0)

    transitions = breakers._record("UNKNOWN_BREAKER", True, evidence={"unexpected": True}, now_ts=11.0)

    assert transitions == []
    after = breakers.snapshot(now_ts=10.0)
    assert after["breakers"] == before["breakers"]


def test_disabled_breakers_never_block_even_when_state_is_tripped(monkeypatch):
    _configure_for_test(monkeypatch)
    breakers = DecisionCircuitBreakers(now_fn=lambda: 0.0)
    breakers.observe_broker_failure(True, now_ts=0.0)
    breakers.observe_broker_failure(True, now_ts=1.0)
    assert breakers.snapshot(now_ts=1.0)["blocked"] is True

    breakers.enabled = False

    assert breakers.should_block_decisions(now_ts=2.0) == (False, [])
    snapshot = breakers.snapshot(now_ts=2.0)
    assert snapshot["enabled"] is False
    assert snapshot["blocked"] is False
    assert snapshot["blocked_reasons"] == []
