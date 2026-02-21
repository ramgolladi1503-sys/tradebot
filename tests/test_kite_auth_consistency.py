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


def test_profile_fail_blocks_persist_and_ticker_start(monkeypatch):
    mod = _load_generate_module()

    class _KiteFailProfile:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def generate_session(self, request_token, api_secret=None):
            return {"access_token": "tok_fail_1234"}

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

    with pytest.raises(RuntimeError, match="kite_depth_ws_profile_failed"):
        orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert start_mock.call_count == 0


def test_profile_ok_persists_and_ticker_allowed(monkeypatch):
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

    start_mock = Mock()
    monkeypatch.setattr(orchestrator_mod, "start_depth_ws", start_mock)
    monkeypatch.setattr(orchestrator_mod.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(orchestrator_mod.kite_client, "kite", _KiteOk("api_key_1234"), raising=False)
    import core.kite_depth_ws as ws
    monkeypatch.setattr(ws, "build_depth_subscription_tokens", lambda symbols: ([101], [{"symbol": "NIFTY", "count": 1}]))
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)

    orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert start_mock.call_count == 1
    args, kwargs = start_mock.call_args
    assert 101 in args[0]
    assert kwargs.get("profile_verified") is True


def test_start_depth_ws_seeds_ohlc_before_ws_start(monkeypatch):
    import core.orchestrator as orchestrator_mod
    import core.kite_depth_ws as ws
    import core.auth_health as auth_health

    class _KiteOk:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def profile(self):
            return {"user_id": "ABCD1234"}

    call_order = []

    def _seed(symbols):
        call_order.append(("seed", tuple(symbols)))
        return [{"symbol": "NIFTY", "seeded_bars_count": 60, "last_candle_ts": "x", "indicator_last_update_ts": "y"}]

    def _start(tokens, **kwargs):
        call_order.append(("start", tuple(tokens), kwargs.get("profile_verified")))

    monkeypatch.setattr(orchestrator_mod, "ensure_startup_warmup_bootstrap", _seed)
    monkeypatch.setattr(orchestrator_mod, "start_depth_ws", _start)
    monkeypatch.setattr(orchestrator_mod.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(orchestrator_mod.kite_client, "kite", _KiteOk("api_key_1234"), raising=False)
    monkeypatch.setattr(ws, "build_depth_subscription_tokens", lambda symbols: ([101], [{"symbol": "NIFTY", "count": 1}]))
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=True: {"ok": True, "user_id": "ABCD1234"})
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)

    orchestrator_mod.Orchestrator._start_depth_ws(object())
    assert call_order[0] == ("seed", ("NIFTY",))
    assert call_order[1][0] == "start"
    assert call_order[1][1] == (101,)
    assert call_order[1][2] is True
