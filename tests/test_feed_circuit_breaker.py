import json

from config import config as cfg
from core import feed_circuit_breaker
from core import readiness_gate


def test_feed_circuit_breaker_trip_clear(tmp_path, monkeypatch):
    state_path = tmp_path / "feed_circuit_breaker.json"
    monkeypatch.setattr(feed_circuit_breaker, "STATE_PATH", state_path)
    feed_circuit_breaker._reset_for_tests()

    assert feed_circuit_breaker.is_tripped() is False
    feed_circuit_breaker.trip("test_trip", meta={"count": 1})
    assert feed_circuit_breaker.is_tripped() is True

    payload = json.loads(state_path.read_text())
    assert payload["tripped"] is True
    assert payload["reason"] == "test_trip"
    assert payload["meta"]["count"] == 1

    feed_circuit_breaker.clear(reason="manual_clear")
    assert feed_circuit_breaker.is_tripped() is False
    payload = json.loads(state_path.read_text())
    assert payload["tripped"] is False


def test_readiness_blocks_when_breaker_tripped(monkeypatch, tmp_path):
    monkeypatch.setattr(readiness_gate, "feed_breaker_tripped", lambda: True)
    monkeypatch.setattr(cfg, "DESK_ID", "TEST")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"))
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"])
    monkeypatch.setattr(cfg, "READINESS_REQUIRE_RISK_HALT_CLEAR", False)
    monkeypatch.setattr(cfg, "READINESS_REQUIRE_AUDIT_CHAIN", False)
    monkeypatch.setattr(cfg, "READINESS_REQUIRE_KITE_AUTH", False)
    monkeypatch.setattr(cfg, "READINESS_REQUIRE_TRADE_SCHEMA", False)
    monkeypatch.setattr(cfg, "READINESS_REQUIRE_FEED_HEALTH", False)

    res = readiness_gate.run_readiness_state(write_log=False)
    assert res.state.value == "BLOCKED"
    assert "feed_circuit_breaker_tripped" in res.blockers
