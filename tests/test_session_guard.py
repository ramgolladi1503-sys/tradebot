from config import config as cfg
import core.session_guard as session_guard


def test_auto_clear_risk_halt_market_closed_no_positions(monkeypatch):
    monkeypatch.setattr(cfg, "AUTO_CLEAR_RISK_HALT_ON_START", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_RISK_HALT_REQUIRE_MARKET_CLOSED", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_RISK_HALT_REQUIRE_NO_OPEN_POSITIONS", True, raising=False)
    monkeypatch.setattr(session_guard, "_write_guard_log", lambda payload: payload)
    monkeypatch.setattr(session_guard.risk_halt, "is_halted", lambda: True)
    cleared = {"count": 0}

    def _clear():
        cleared["count"] += 1

    monkeypatch.setattr(session_guard.risk_halt, "clear_halt", _clear)
    monkeypatch.setattr(session_guard, "is_market_open_ist", lambda now=None: False)
    monkeypatch.setattr(session_guard, "fetch_open_positions_dict", lambda limit=5000: [])

    result = session_guard.auto_clear_risk_halt_if_safe()

    assert result["cleared"] is True
    assert result["reason_code"] == "HALT_AUTO_CLEARED_SAFE_SESSION_START"
    assert cleared["count"] == 1


def test_auto_clear_risk_halt_blocked_when_market_open(monkeypatch):
    monkeypatch.setattr(cfg, "AUTO_CLEAR_RISK_HALT_ON_START", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_RISK_HALT_REQUIRE_MARKET_CLOSED", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_RISK_HALT_REQUIRE_NO_OPEN_POSITIONS", True, raising=False)
    monkeypatch.setattr(session_guard, "_write_guard_log", lambda payload: payload)
    monkeypatch.setattr(session_guard.risk_halt, "is_halted", lambda: True)
    monkeypatch.setattr(session_guard.risk_halt, "clear_halt", lambda: (_ for _ in ()).throw(RuntimeError("should_not_clear")))
    monkeypatch.setattr(session_guard, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(session_guard, "fetch_open_positions_dict", lambda limit=5000: [])

    result = session_guard.auto_clear_risk_halt_if_safe()

    assert result["cleared"] is False
    assert result["reason_code"] == "HALT_CLEAR_BLOCKED_MARKET_OPEN"
