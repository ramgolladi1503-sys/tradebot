import pytest
from pathlib import Path

from config import config as cfg
from core import auth_health
from core import risk_halt


class _FakeKite:
    def __init__(self, counter):
        self._counter = counter

    def profile(self):
        self._counter["calls"] += 1
        return {"user_id": "U999", "user_name": "Tester"}


def _setup_fake_kite(monkeypatch, counter):
    fake = _FakeKite(counter)
    monkeypatch.setattr(auth_health.kite_client, "kite", fake)
    monkeypatch.setattr(auth_health.kite_client, "ensure", lambda: None)


def test_auth_health_cache_and_force(monkeypatch):
    auth_health._reset_cache_for_tests()
    monkeypatch.setattr(cfg, "KITE_API_KEY", "abc123KEY")
    monkeypatch.setattr(auth_health, "resolve_access_token", lambda **kwargs: "token1234")

    counter = {"calls": 0}
    _setup_fake_kite(monkeypatch, counter)

    first = auth_health.get_kite_auth_health(force=False)
    second = auth_health.get_kite_auth_health(force=False)
    third = auth_health.get_kite_auth_health(force=True)

    assert first["ok"] is True
    assert second["source"] == "cache"
    assert counter["calls"] == 2
    assert third["ok"] is True


def test_auth_health_whitespace_token(monkeypatch):
    auth_health._reset_cache_for_tests()
    monkeypatch.setattr(cfg, "KITE_API_KEY", "abc123KEY")
    monkeypatch.setattr(auth_health, "resolve_access_token", lambda **kwargs: "  tok_xx91pk  ")

    counter = {"calls": 0}
    _setup_fake_kite(monkeypatch, counter)

    payload = auth_health.get_kite_auth_health(force=True)
    assert payload["access_token_has_whitespace"] is True
    assert payload["access_token_tail4"] == "91pk"


def test_auth_health_clears_db_write_halt(tmp_path, monkeypatch):
    auth_health._reset_cache_for_tests()
    monkeypatch.setattr(cfg, "KITE_API_KEY", "abc123KEY")
    monkeypatch.setattr(auth_health, "resolve_access_token", lambda **kwargs: "token1234")

    halt_path = tmp_path / "risk_halt.json"
    halt_path.write_text('{"halted": true, "reason": "db_write_fail"}')
    monkeypatch.setattr(cfg, "RISK_HALT_FILE", str(halt_path), raising=False)

    counter = {"calls": 0}
    _setup_fake_kite(monkeypatch, counter)

    payload = auth_health.get_kite_auth_health(force=True)
    assert payload["ok"] is True
    state = risk_halt.load_halt()
    assert state.get("halted") is False


def test_preopen_auth_warm_check_degrades_to_planning_when_unhealthy(tmp_path, monkeypatch):
    auth_health._reset_cache_for_tests()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "AUTH_PREOPEN_WARM_CHECK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "AUTH_PREOPEN_DEGRADE_TO_PLANNING", True, raising=False)
    monkeypatch.setattr(cfg, "AUTH_PREOPEN_FORCE_REFRESH", False, raising=False)
    guard_path = tmp_path / "auth_runtime_guard.json"
    monkeypatch.setattr(cfg, "AUTH_RUNTIME_GUARD_PATH", str(guard_path), raising=False)
    monkeypatch.setattr(
        auth_health,
        "get_kite_auth_health",
        lambda force=False: {
            "ok": False,
            "auth_state": "FAILED",
            "error": "profile_error:TokenException",
            "ts_epoch": 1_700_000_000.0,
        },
    )

    payload = auth_health.run_preopen_auth_warm_check(
        force=False,
        market_context={"execution_mode": "LIVE", "market_open": False},
        now_epoch=1_700_000_010.0,
    )
    assert payload["preopen"] is True
    assert payload["degrade_to_planning"] is True
    assert "TokenException" in str(payload.get("reason"))
    assert Path(guard_path).exists()
