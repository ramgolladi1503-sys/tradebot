from pathlib import Path
from datetime import datetime, timezone

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
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_LTP_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_DEPTH_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {}, raising=False)
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


def test_on_ticks_updates_index_quote_cache_from_underlying_depth(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    cache_updates = []

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(
        ws,
        "_update_index_quote_cache",
        lambda symbol, bid, ask, mid, ts_epoch, last_price: cache_updates.append(
            {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "ts_epoch": ts_epoch,
                "last_price": last_price,
            }
        ),
    )

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 101.0,
                "depth": {
                    "buy": [{"price": 100.0, "quantity": 10}],
                    "sell": [{"price": 102.0, "quantity": 12}],
                },
                "exchange_timestamp": datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc),
            }
        ],
    )

    assert cache_updates
    row = cache_updates[-1]
    assert row["symbol"] == "NIFTY"
    assert row["bid"] == 100.0
    assert row["ask"] == 102.0
    assert row["mid"] == 101.0


def test_on_ticks_updates_symbol_ltp_and_depth_timestamps(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "record_tick_epoch", lambda ts: None)

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]

    ltp_ts = datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc)
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25000.0,
                "exchange_timestamp": ltp_ts,
            }
        ],
    )
    assert ws._SYMBOL_LAST_LTP_TS.get("NIFTY") == ltp_ts.timestamp()
    assert "NIFTY" not in ws._SYMBOL_LAST_DEPTH_TS
    assert ws._LAST_WS_TICK_EPOCH > 0

    depth_ts = datetime(2026, 2, 19, 9, 31, tzinfo=timezone.utc)
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25001.0,
                "exchange_timestamp": depth_ts,
                "depth": {
                    "buy": [{"price": 25000.0, "quantity": 12}],
                    "sell": [{"price": 25002.0, "quantity": 9}],
                },
            }
        ],
    )
    assert ws._SYMBOL_LAST_LTP_TS.get("NIFTY") == depth_ts.timestamp()
    assert ws._SYMBOL_LAST_DEPTH_TS.get("NIFTY") == depth_ts.timestamp()
