from pathlib import Path

from config import config as cfg
from core.auth import reset_kite_runtime_credentials_guard
import core.auth as auth_module
import core.kite_depth_ws as ws


class _DummyThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


class _DummyTicker:
    MODE_FULL = "full"

    def __init__(self, api_key, access_token, debug=True):
        self.api_key = api_key
        self.access_token = access_token
        self.debug = debug
        self.connected = False
        self.auto_reconnect = True
        self.on_connect = None
        self.on_reconnect = None
        self.on_error = None
        self.on_close = None
        self.on_ticks = None
        self.subscribed = []
        self.mode_tokens = []

    def subscribe(self, tokens):
        self.subscribed = list(tokens)

    def set_mode(self, mode, tokens):
        self.mode_tokens = list(tokens)

    def connect(self, threaded=True):
        self.connected = True

    def close(self):
        return None


class _DummyRestClient:
    def set_access_token(self, token):
        _ = token

    def profile(self):
        return {"user_id": "ABCD1234"}


def _patch_common(monkeypatch):
    reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_THREAD", None, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_WARMUP_PENDING", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_FEED_TICK_LOG_MINUTE", None, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LOGGED", False, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "repo_root", lambda: Path("/tmp"))
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: False)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True})
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123")
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "clear_auth_required_state", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(ws, "invalidate_cache", lambda **kwargs: None)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(ws.threading, "Thread", _DummyThread)
    rest = _DummyRestClient()
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "_ensure", lambda: rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "kite", rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "api_key_1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "TOKEN123", raising=False)


def test_on_connect_forces_subscribe(monkeypatch):
    pass