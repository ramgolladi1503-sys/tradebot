from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

from config import config as cfg


def _load_generate_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_kite_access_token.py"
    spec = importlib.util.spec_from_file_location("generate_kite_access_token_mod", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key")
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token")

def test_profile_fail_blocks_persist_and_ticker_start(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    mod = _load_generate_module()

    class _KiteFailProfile:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def generate_session(self, request_token, api_secret=None):
            return {"access_token": "f_1234_fail"}

        def set_access_token(self, token):
            return None

        def profile(self):
            raise RuntimeError("profile_failed")

        def margins(self):
            return {"equity": {}}

    token_path = Path("/tmp/kite_access_token_fail")
    def _persist(token):
        token_path.write_text(token)
        return token_path

    monkeypatch.setattr(mod, "get_kite_auth_health", lambda force=False: {"ok": False, "error": "profile_failed"})
    with pytest.raises(RuntimeError):
        mod.generate_token_flow(
            "api_key_1234",
            "api_secret",
            "request_token",
            update_store=True,
            kite_connect_cls=_KiteFailProfile,
            persist_fn=_persist,
        )
    assert not token_path.exists()

    import core.orchestrator as orchestrator_mod

    start_mock = Mock()
    monkeypatch.setattr(orchestrator_mod, "start_depth_ws", start_mock)
    monkeypatch.setattr(orchestrator_mod.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(orchestrator_mod.kite_client, "kite", _KiteFailProfile("api_key_1234"), raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(orchestrator_mod, "_validated_depth_ws_startup_snapshot", lambda: ({"valid": True, "runtime_state": "RUNNING", "ws_connected": True}, 0.0))

    with pytest.raises(RuntimeError, match="kite_depth_ws_profile_failed"):
        orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert start_mock.call_count == 0


def test_profile_ok_persists_and_ticker_allowed(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)
    mod = _load_generate_module()

    class _KiteOk:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def generate_session(self, request_token, api_secret=None):
            return {"access_token": "tok_ok_9999"}

        def set_access_token(self, token):
            self.token = token

        def profile(self):
            return {"user_id": "ABCD1234"}

        def margins(self):
            return {"equity": {"available": {"cash": 1000}}}

    token_path = Path("/tmp/kite_access_token_ok")
    def _persist(token):
        token_path.write_text(token)
        return token_path

    monkeypatch.setattr(mod, "get_kite_auth_health", lambda force=False: {"ok": True, "user_id": "ABCD1234"})
    flow = mod.generate_token_flow(
        "api_key_1234",
        "api_secret",
        "request_token",
        update_store=True,
        kite_connect_cls=_KiteOk,
        persist_fn=_persist,
    )
    assert flow["access_token"] == "tok_ok_9999"
    assert token_path.exists()

    import core.orchestrator as orchestrator_mod
    import core.auth_health as auth_health

    start_mock = Mock()
    monkeypatch.setattr(orchestrator_mod, "start_depth_ws", start_mock)
    monkeypatch.setattr(orchestrator_mod.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(orchestrator_mod.kite_client, "kite", _KiteOk("api_key_1234"), raising=False)
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=True: {"ok": True, "user_id": "ABCD1234"})
    import core.kite_depth_ws as ws
    monkeypatch.setattr(ws, "build_depth_subscription_tokens", lambda symbols: ([101], [{"symbol": "NIFTY", "count": 1}]))
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(orchestrator_mod, "_validated_depth_ws_startup_snapshot", lambda: ({"valid": True, "runtime_state": "RUNNING", "ws_connected": True}, 0.0))

    orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert start_mock.call_count == 1
    args, kwargs = start_mock.call_args
    assert 101 in args[0]
    assert kwargs.get("profile_verified") is True


def test_start_depth_ws_does_not_seed_ohlc(monkeypatch):
    import config.config as cfg
    import core.orchestrator as orchestrator_mod
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {})
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.orchestrator as orchestrator_mod
    import core.kite_depth_ws as ws
    import core.auth_health as auth_health

    class _KiteOk:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def profile(self):
            return {"user_id": "ABCD1234"}

    call_order = []

    def _start(tokens, **kwargs):
        call_order.append(("start", tuple(tokens), kwargs.get("profile_verified")))

    monkeypatch.setattr(orchestrator_mod, "start_depth_ws", _start)
    monkeypatch.setattr(orchestrator_mod.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(orchestrator_mod.kite_client, "kite", _KiteOk("api_key_1234"), raising=False)
    monkeypatch.setattr(ws, "build_depth_subscription_tokens", lambda symbols: ([101], [{"symbol": "NIFTY", "count": 1}]))
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=True: {"ok": True, "user_id": "ABCD1234"})
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(orchestrator_mod, "_validated_depth_ws_startup_snapshot", lambda: ({"valid": True, "runtime_state": "RUNNING", "ws_connected": True}, 0.0))

    orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert call_order == [("start", (101,), True)]


def test_init_runs_startup_warmup_when_depth_ws_disabled(monkeypatch):
    import core.orchestrator as orchestrator_mod

    calls = {"warmup": 0, "depth": 0}

    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

    class _StubTracker(_Stub):
        def load(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(orchestrator_mod, "auto_clear_risk_halt_if_safe", lambda: None)
    monkeypatch.setattr(orchestrator_mod, "ensure_trade_log_exists", lambda: None)
    monkeypatch.setattr(orchestrator_mod, "TradePredictor", _Stub)
    monkeypatch.setattr(orchestrator_mod, "ExecutionEngine", _Stub)
    monkeypatch.setattr(orchestrator_mod, "ExecutionRouter", _Stub)
    monkeypatch.setattr(orchestrator_mod, "StrategyGatekeeper", _Stub)
    monkeypatch.setattr(orchestrator_mod, "PortfolioRiskAllocator", _Stub)
    monkeypatch.setattr(orchestrator_mod, "RiskEngine", _Stub)
    monkeypatch.setattr(orchestrator_mod, "ExecutionGuard", _Stub)
    monkeypatch.setattr(orchestrator_mod, "StrategyTracker", _StubTracker)
    monkeypatch.setattr(orchestrator_mod, "TradeBuilder", _Stub)
    monkeypatch.setattr(orchestrator_mod, "AutoRetrain", _Stub)
    monkeypatch.setattr(orchestrator_mod, "StrategyAllocator", _Stub)
    monkeypatch.setattr(orchestrator_mod, "BlockedTradeTracker", _Stub)
    monkeypatch.setattr(orchestrator_mod, "CircuitBreaker", _Stub)
    monkeypatch.setattr(orchestrator_mod, "RunLock", _Stub)
    monkeypatch.setattr(orchestrator_mod, "ExposureLedger", _Stub)
    monkeypatch.setattr(orchestrator_mod, "RiskState", _Stub)
    monkeypatch.setattr(orchestrator_mod, "verify_audit_chain", lambda: (True, "OK", None))
    monkeypatch.setattr(orchestrator_mod.Orchestrator, "_load_symbol_eps", lambda self: None)
    monkeypatch.setattr(orchestrator_mod.Orchestrator, "_load_suggestion_eval", lambda self: None)
    monkeypatch.setattr(
        orchestrator_mod.Orchestrator,
        "_run_startup_warmup_bootstrap",
        lambda self: calls.__setitem__("warmup", calls["warmup"] + 1) or [],
    )
    monkeypatch.setattr(
        orchestrator_mod.Orchestrator,
        "_start_depth_ws",
        lambda self: calls.__setitem__("depth", calls["depth"] + 1),
    )
    monkeypatch.setattr(cfg, "DECISION_LOG_ENABLED", False, raising=False)
    monkeypatch.setattr(cfg, "RL_ENABLED", False, raising=False)

    orchestrator_mod.Orchestrator(start_depth_ws_enabled=False)
    assert calls["warmup"] == 1
    assert calls["depth"] == 0
