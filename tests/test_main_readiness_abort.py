from config import config as cfg
import main as main_module


def test_non_global_readiness_blocker_does_not_abort(monkeypatch):
    monkeypatch.setattr(cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", ["risk_halt_active"], raising=False)
    monkeypatch.setattr(cfg, "READINESS_GLOBAL_ABORT_PREFIXES", ["audit_chain:"], raising=False)
    readiness = {
        "state": "BLOCKED",
        "market_open": True,
        "blockers": ["feed_health:feed_stale:NIFTY", "missing_option_token"],
        "reasons": ["feed_health:feed_stale:NIFTY", "missing_option_token"],
    }
    should_abort, reasons = main_module._classify_readiness_abort(readiness)
    assert should_abort is False
    assert reasons == []


def test_global_readiness_blocker_aborts(monkeypatch):
    monkeypatch.setattr(cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", ["risk_halt_active"], raising=False)
    monkeypatch.setattr(cfg, "READINESS_GLOBAL_ABORT_PREFIXES", ["audit_chain:"], raising=False)
    readiness = {
        "state": "BLOCKED",
        "market_open": True,
        "blockers": ["risk_halt_active"],
        "reasons": ["risk_halt_active"],
    }
    should_abort, reasons = main_module._classify_readiness_abort(readiness)
    assert should_abort is True
    assert reasons == ["risk_halt_active"]


def test_market_closed_aborts(monkeypatch):
    monkeypatch.setattr(cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", ["risk_halt_active"], raising=False)
    monkeypatch.setattr(cfg, "READINESS_GLOBAL_ABORT_PREFIXES", ["audit_chain:"], raising=False)
    readiness = {
        "state": "MARKET_CLOSED",
        "market_open": False,
        "blockers": [],
        "reasons": [],
    }
    should_abort, reasons = main_module._classify_readiness_abort(readiness)
    assert should_abort is True
    assert reasons == ["market_closed"]
