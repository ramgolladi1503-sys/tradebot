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
        self.auto_reconnect = True
        self.connected = False
        self.closed = False
        self.on_connect = None
        self.on_reconnect = None
        self.on_error = None
        self.on_close = None
        self.on_ticks = None

    def subscribe(self, tokens):
        self.tokens = list(tokens)

    def set_mode(self, mode, tokens):
        self.mode = mode
        self.mode_tokens = list(tokens)

    def connect(self, threaded=True):
        self.connected = True

    def close(self):
        self.closed = True


class _DummyRestClient:
    def __init__(self):
        self.token = ""

    def set_access_token(self, token):
        self.token = token

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
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "repo_root", lambda: Path("/tmp"))
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: False)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True})
    monkeypatch.setattr(ws, "resolve_kite_access_token", lambda **kwargs: "TOKEN123")
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(ws.threading, "Thread", _DummyThread)
    rest = _DummyRestClient()
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: None, raising=False)
    monkeypatch.setattr(ws.kite_client, "_ensure", lambda: None, raising=False)
    monkeypatch.setattr(ws.kite_client, "kite", rest, raising=False)


def test_start_depth_ws_uses_resolved_token(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)

    ticker = captured["ticker"]
    assert ticker.api_key == "api_key_1234"
    assert ticker.access_token == "TOKEN123"
    assert ticker.auto_reconnect is False
    assert ticker.connected is True


def test_on_close_does_not_restart_after_stop(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    restarts = {"count": 0}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    def _restart(reason="unknown"):
        restarts["count"] += 1
        return True

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "restart_depth_ws", _restart)

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ws.stop_depth_ws(reason="unit_test_stop")
    ticker.on_close(ticker, 1000, "normal")

    assert restarts["count"] == 0
