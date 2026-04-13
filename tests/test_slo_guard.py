from __future__ import annotations

from pathlib import Path

from config import config as cfg
import core.slo_guard as slo_guard


def test_slo_guard_triggers_failover_after_consecutive_breaches(monkeypatch, tmp_path):
    state_path = tmp_path / "slo_state.json"
    events_path = tmp_path / "slo_events.jsonl"
    monkeypatch.setattr(cfg, "SLO_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_CONSECUTIVE_BREACHES", 2, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_ACTION", "RISK_HALT", raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_STATE_PATH", str(state_path), raising=False)
    monkeypatch.setattr(cfg, "SLO_EVENT_LOG_PATH", str(events_path), raising=False)

    calls = {"halt": 0, "breaker": 0}
    monkeypatch.setattr(slo_guard.risk_halt, "set_halt", lambda *_a, **_k: calls.__setitem__("halt", calls["halt"] + 1))
    monkeypatch.setattr(slo_guard, "trip_feed_breaker", lambda *_a, **_k: calls.__setitem__("breaker", calls["breaker"] + 1))

    auth = {"ok": False, "ts_epoch": 1700000000.0, "latency_sec": 3.0}
    feed = {"ltp": {"age_sec": 999.0}, "depth": {"age_sec": 999.0, "required": True}}
    first = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "LIVE", "market_open": True},
        now_epoch=1700000100.0,
        enforce_failover=True,
    )
    second = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "LIVE", "market_open": True},
        now_epoch=1700000200.0,
        enforce_failover=True,
    )
    assert first["failover_triggered"] is False
    assert second["failover_triggered"] is True
    assert calls["halt"] == 1
    assert calls["breaker"] == 1
    assert Path(state_path).exists()


def test_slo_guard_does_not_enforce_failover_in_paper(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "SLO_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(cfg, "SLO_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"), raising=False)
    auth = {"ok": False, "ts_epoch": 1700000000.0, "latency_sec": 4.0}
    feed = {"ltp": {"age_sec": 1000.0}, "depth": {"age_sec": 1000.0, "required": True}}
    out = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "PAPER", "market_open": True},
        now_epoch=1700000100.0,
        enforce_failover=True,
    )
    assert out["ok"] is True
    assert out["failover_triggered"] is False
    assert out["warnings"]


def test_slo_guard_suppresses_feed_warnings_when_allow_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "SLO_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(cfg, "SLO_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"), raising=False)

    auth = {"ok": True, "ts_epoch": 1700000090.0, "latency_sec": 0.1}
    feed = {
        "market_open": True,
        "allow_stale_quotes": True,
        "ltp": {"age_sec": 999.0},
        "depth": {"age_sec": 999.0, "required": False},
    }
    out = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "PAPER", "market_open": True},
        now_epoch=1700000100.0,
        enforce_failover=True,
    )
    assert out["warnings"] == []
    assert "FEED_LTP_STALE" in out["suppressed_warnings"]


def test_slo_guard_suppresses_auth_noise_when_market_closed_and_not_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "SLO_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(cfg, "SLO_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"), raising=False)

    auth = {"ok": False, "ts_epoch": None, "latency_sec": None}
    feed = {
        "market_open": False,
        "allow_stale_quotes": True,
        "ltp": {"age_sec": None},
        "depth": {"age_sec": None, "required": False},
    }
    out = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "PAPER", "market_open": False},
        now_epoch=1700000100.0,
        enforce_failover=True,
    )
    assert out["ok"] is True
    assert out["warnings"] == []
    assert "AUTH_UNHEALTHY" in out["suppressed_warnings"]
    assert "AUTH_LATENCY_MISSING" in out["suppressed_warnings"]


def test_slo_guard_startup_grace_suppresses_live_transient_feed_breach(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "SLO_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_STARTUP_GRACE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_STARTUP_GRACE_SEC", 30.0, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_CONSECUTIVE_BREACHES", 1, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_ACTION", "RISK_HALT", raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(cfg, "SLO_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"), raising=False)
    monkeypatch.setattr(slo_guard, "_PROCESS_START_MONOTONIC", 100.0, raising=False)
    monkeypatch.setattr(slo_guard.time, "monotonic", lambda: 110.0)

    auth = {"ok": True, "ts_epoch": 1700000090.0, "latency_sec": 3.0}
    feed = {"ltp": {"age_sec": 999.0}, "depth": {"age_sec": 999.0, "required": True}}
    out = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "LIVE", "market_open": True},
        now_epoch=1700000100.0,
        enforce_failover=True,
    )
    assert out["startup_grace_active"] is True
    assert out["failover_triggered"] is False
    assert out["reasons"] == []
    assert "FEED_LTP_STALE" in out["startup_suppressed_warnings"]


def test_slo_guard_startup_grace_expiry_restores_live_failover(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "SLO_GUARD_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_STARTUP_GRACE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SLO_STARTUP_GRACE_SEC", 30.0, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_CONSECUTIVE_BREACHES", 1, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_ACTION", "RISK_HALT", raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "SLO_FAILOVER_STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(cfg, "SLO_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"), raising=False)
    monkeypatch.setattr(slo_guard, "_PROCESS_START_MONOTONIC", 100.0, raising=False)
    monkeypatch.setattr(slo_guard.time, "monotonic", lambda: 140.0)

    calls = {"halt": 0, "breaker": 0}
    monkeypatch.setattr(slo_guard.risk_halt, "set_halt", lambda *_a, **_k: calls.__setitem__("halt", calls["halt"] + 1))
    monkeypatch.setattr(slo_guard, "trip_feed_breaker", lambda *_a, **_k: calls.__setitem__("breaker", calls["breaker"] + 1))

    auth = {"ok": True, "ts_epoch": 1700000090.0, "latency_sec": 3.0}
    feed = {"ltp": {"age_sec": 999.0}, "depth": {"age_sec": 999.0, "required": True}}
    out = slo_guard.evaluate_slo_status(
        auth_payload=auth,
        feed_payload=feed,
        market_context={"execution_mode": "LIVE", "market_open": True},
        now_epoch=1700000100.0,
        enforce_failover=True,
    )
    assert out["startup_grace_active"] is False
    assert out["failover_triggered"] is True
    assert "FEED_LTP_STALE" in out["reasons"]
    assert calls["halt"] == 1
    assert calls["breaker"] == 1
