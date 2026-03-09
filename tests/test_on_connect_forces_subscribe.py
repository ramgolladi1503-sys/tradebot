from pathlib import Path

from config import config as cfg
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
    monkeypatch.setattr(ws, "resolve_access_token", lambda **kwargs: "TOKEN123")
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "clear_auth_required_state", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(ws, "invalidate_cache", lambda **kwargs: None)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(ws.threading, "Thread", _DummyThread)
    rest = _DummyRestClient()
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: None, raising=False)
    monkeypatch.setattr(ws.kite_client, "_ensure", lambda: None, raising=False)
    monkeypatch.setattr(ws.kite_client, "kite", rest, raising=False)


def test_on_connect_forces_subscribe(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)

    ws.start_depth_ws([101, 102, 103], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ws._LAST_TOKENS = [101, 102, 103]
    ticker.subscribed = []
    ticker.mode_tokens = []

    ticker.on_connect(ticker, {"event": "unit"})

    assert ticker.subscribed == [101, 102, 103]
    assert ticker.mode_tokens == [101, 102, 103]
