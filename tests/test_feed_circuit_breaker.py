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
    monkeypatch.setattr(
        readiness_gate,
        "feed_breaker_maybe_auto_clear",
        lambda _state=None: {"tripped": True, "cleared": False, "reason": "manual_test"},
    )
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


def test_feed_breaker_auto_clears_on_fresh_feed_state(tmp_path, monkeypatch):
    state_path = tmp_path / "feed_circuit_breaker.json"
    monkeypatch.setattr(feed_circuit_breaker, "STATE_PATH", state_path)
    feed_circuit_breaker._reset_for_tests()
    feed_circuit_breaker.trip("slo_failover", meta={"reasons": ["FEED_LTP_STALE"]})

    out = feed_circuit_breaker.maybe_auto_clear(
        {
            "ws_connected": True,
            "last_ws_tick_age_sec": 0.5,
            "last_tick_age_sec": 0.6,
        }
    )
    assert out["cleared"] is True
    assert out["clear_reason"] == "auto_recovered"
    assert feed_circuit_breaker.is_tripped() is False


def test_feed_breaker_timeout_clear(tmp_path, monkeypatch):
    state_path = tmp_path / "feed_circuit_breaker.json"
    monkeypatch.setattr(feed_circuit_breaker, "STATE_PATH", state_path)
    feed_circuit_breaker._reset_for_tests()
    feed_circuit_breaker.trip("slo_failover", meta={"reasons": ["FEED_LTP_STALE"]})
    monkeypatch.setattr(cfg, "FEED_BREAKER_MAX_BLOCK_TIME_SEC", 0.1, raising=False)

    # Force elapsed trip duration above timeout threshold.
    payload = json.loads(state_path.read_text())
    payload["ts_epoch"] = float(payload.get("ts_epoch", 0.0)) - 5.0
    state_path.write_text(json.dumps(payload, indent=2))

    out = feed_circuit_breaker.maybe_auto_clear(
        {
            "ws_connected": False,
            "last_ws_tick_age_sec": 999.0,
            "last_tick_age_sec": 999.0,
        }
    )
    assert out["cleared"] is True
    assert out["clear_reason"] == "timeout_auto_clear"
    assert feed_circuit_breaker.is_tripped() is False
