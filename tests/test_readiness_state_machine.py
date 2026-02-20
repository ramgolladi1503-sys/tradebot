from datetime import datetime

import core.readiness_gate as readiness_gate
from core.readiness_state import ReadinessState


def _common_ok(monkeypatch):
    monkeypatch.setattr(readiness_gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(readiness_gate, "verify_audit_chain", lambda: (True, "ok", 0))
    monkeypatch.setattr(readiness_gate, "_check_kite_auth", lambda: (True, "ok", "OK"))
    monkeypatch.setattr(readiness_gate, "_check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(readiness_gate, "_disk_free_gb", lambda _=".": 10.0)


def test_readiness_ready_market_open(monkeypatch):
    _common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: datetime(2026, 2, 10, 10, 0, 0))
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(
        readiness_gate,
        "_decision_gate_health",
        lambda now_epoch, market_open: {
            "ok": True,
            "feed_ok": True,
            "blockers": [],
            "reasons": [],
            "symbols": ["NIFTY"],
            "allowed_symbols": ["NIFTY"],
            "blocked_symbols": [],
            "blockers_by_symbol": {"NIFTY": []},
            "rows": {},
            "ltp_age_sec": 1.0,
            "depth_age_sec": 1.2,
            "latest_explain": [],
        },
    )

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.READY
    assert result.can_trade is True
    assert result.blockers == []


def test_readiness_blocked_market_open_feed_stale(monkeypatch):
    _common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: datetime(2026, 2, 10, 10, 0, 0))
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(
        readiness_gate,
        "_decision_gate_health",
        lambda now_epoch, market_open: {
            "ok": False,
            "feed_ok": False,
            "blockers": ["decision_gate_blocked"],
            "reasons": ["tick_feed_stale"],
            "symbols": ["NIFTY"],
            "allowed_symbols": [],
            "blocked_symbols": ["NIFTY"],
            "blockers_by_symbol": {"NIFTY": ["FEED_STALE"]},
            "rows": {},
            "ltp_age_sec": 300.0,
            "depth_age_sec": 2.0,
            "latest_explain": [],
        },
    )

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.BLOCKED
    assert result.can_trade is False
    assert any("feed_health:tick_feed_stale" in reason for reason in result.blockers)


def test_readiness_degraded_market_closed_feed_stale(monkeypatch):
    _common_ok(monkeypatch)
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: datetime(2026, 2, 10, 20, 0, 0))
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: False)
    monkeypatch.setattr(
        readiness_gate,
        "_decision_gate_health",
        lambda now_epoch, market_open: {
            "ok": True,
            "feed_ok": True,
            "blockers": [],
            "reasons": [],
            "symbols": [],
            "allowed_symbols": [],
            "blocked_symbols": [],
            "blockers_by_symbol": {},
            "rows": {},
            "ltp_age_sec": 300.0,
            "depth_age_sec": 2.0,
            "latest_explain": [],
        },
    )

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.MARKET_CLOSED
    assert result.can_trade is False
    assert result.blockers == []
    assert result.warnings == []
