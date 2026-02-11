import time

from core import feed_circuit_breaker


def test_feed_breaker_trip_and_clear(tmp_path, monkeypatch):
    state_path = tmp_path / "feed_circuit_breaker.json"
    monkeypatch.setattr(feed_circuit_breaker, "STATE_PATH", state_path)
    feed_circuit_breaker._reset_for_tests()

    assert feed_circuit_breaker.is_tripped() is False

    feed_circuit_breaker.trip("test", meta={"count": 3, "window_sec": 3600})
    assert feed_circuit_breaker.is_tripped() is True

    feed_circuit_breaker.clear(reason="manual")
    assert feed_circuit_breaker.is_tripped() is False
