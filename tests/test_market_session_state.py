from datetime import datetime
from zoneinfo import ZoneInfo

from core import feed_circuit_breaker
from core.market_session_state import (
    MARKET_CLOSED,
    MARKET_OPEN,
    POSTMARKET,
    PREMARKET,
    SESSION_STATE_UNKNOWN,
    derive_market_session_policy,
)


def ist(hour, minute=0):
    return datetime(2026, 8, 25, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_market_closed_disables_liveness_and_restart_policy():
    policy = derive_market_session_policy(now=ist(2, 30))
    assert policy.market_state == MARKET_CLOSED
    assert policy.fresh_ticks_required is False
    assert policy.feed_restart_allowed is False
    assert policy.restart_storm_counter_increment_allowed is False


def test_premarket_does_not_use_normal_market_staleness():
    policy = derive_market_session_policy(now=ist(9, 5))
    assert policy.market_state == PREMARKET
    assert policy.feed_staleness_timer_active is False
    assert policy.strategies_active is False
    assert policy.restart_storm_counter_increment_allowed is False


def test_market_open_enables_strict_liveness():
    policy = derive_market_session_policy(now=ist(9, 15))
    assert policy.market_state == MARKET_OPEN
    assert policy.fresh_ticks_required is True
    assert policy.persistence_advancement_required is True
    assert policy.strategies_active is True
    assert policy.ranking_active is True
    assert policy.advisory_emission_active is True
    assert policy.feed_restart_allowed is True


def test_postmarket_disables_downstream_activation():
    policy = derive_market_session_policy(now=ist(15, 31))
    assert policy.market_state == POSTMARKET
    assert policy.strategies_active is False
    assert policy.cas_active is False
    assert policy.ranking_active is False
    assert policy.advisory_emission_active is False


def test_holiday_is_closed(monkeypatch):
    import core.market_session_state as module
    holiday = ist(10).date()
    monkeypatch.setattr(module, "IN_HOLIDAYS", {holiday})
    assert derive_market_session_policy(now=ist(10)).market_state == MARKET_CLOSED


def test_same_session_breaker_fails_closed_but_old_session_does_not_poison(tmp_path, monkeypatch):
    path = tmp_path / "feed_circuit_breaker.json"
    monkeypatch.setattr(feed_circuit_breaker, "STATE_PATH", path)
    feed_circuit_breaker.trip("feed_restart_storm")
    assert feed_circuit_breaker.is_tripped(session_date="2026-08-25") is True
    assert feed_circuit_breaker.is_tripped(session_date="2026-08-26") is False
    assert path.exists()


def test_unknown_state_is_fail_closed(monkeypatch):
    import core.market_session_state as module
    monkeypatch.setattr(module, "get_session", lambda _: (_ for _ in ()).throw(RuntimeError("calendar unavailable")))
    policy = derive_market_session_policy(now=ist(10))
    assert policy.market_state == SESSION_STATE_UNKNOWN
    assert policy.feed_restart_allowed is False
    assert policy.fresh_ticks_required is False
