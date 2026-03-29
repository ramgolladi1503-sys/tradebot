from pathlib import Path
from datetime import datetime, timezone
import sqlite3

from config import config as cfg
import core.auth as auth_module
from core.auth import reset_kite_runtime_credentials_guard
import core.kite_depth_ws as ws
import core.tick_store as tick_store


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
    reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_THREAD", None, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_WARMUP_PENDING", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LOGGED", False, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_LTP_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_DEPTH_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "repo_root", lambda: Path("/tmp"))
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: False)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True})
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "clear_auth_required_state", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(ws, "invalidate_cache", lambda **kwargs: None)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123")
    monkeypatch.setattr(ws.threading, "Thread", _DummyThread)
    rest = _DummyRestClient()
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "kite", rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "api_key_1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "TOKEN123", raising=False)


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
    assert ticker.auto_reconnect is True
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
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101}, raising=False)
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
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
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


def test_on_ticks_does_not_update_index_quote_cache_from_non_underlying_tick(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    cache_updates = []

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
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
    tick_ts = datetime(2026, 2, 19, 9, 35, tzinfo=timezone.utc)
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25123.5,
                "exchange_timestamp": tick_ts,
            }
        ],
    )

    assert cache_updates == []


def test_on_ticks_uses_receipt_time_for_option_freshness(monkeypatch, tmp_path):
    _patch_common(monkeypatch)
    captured = {}
    db_path = tmp_path / "ticks.sqlite"

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    receipt_epoch = datetime(2026, 2, 19, 9, 37, tzinfo=timezone.utc).timestamp()
    stale_payload_ts = datetime(2026, 2, 19, 9, 35, tzinfo=timezone.utc)

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_OPTION_FRESHNESS_USE_RECEIPT_TIME", True, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: receipt_epoch)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {555: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    tick_store._LAST_TICK_EPOCH = None
    tick_store._LAST_TICK_BY_TOKEN.clear()

    ws.start_depth_ws([555], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 555,
                "last_price": 25123.5,
                "exchange_timestamp": stale_payload_ts,
            }
        ],
    )

    assert ws._LAST_MSG_TS_BY_TOKEN[555] == receipt_epoch
    assert ws._LAST_WS_TICK_EPOCH == receipt_epoch

    option_state = ws._option_runtime_state(
        now_epoch=receipt_epoch,
        tokens=[555],
        expected_counts_by_symbol={"NIFTY": 1},
        min_required_by_symbol={"NIFTY": 1},
    )
    assert option_state["last_tick_ts_by_symbol"]["NIFTY"] == receipt_epoch
    assert option_state["option_age_by_symbol"]["NIFTY"] == 0.0
    assert option_state["feed_block_reason_by_symbol"]["NIFTY"] == "OK"

    ltp, tick_epoch = tick_store.get_ltp(555)
    assert ltp == 25123.5
    assert tick_epoch == receipt_epoch

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT MAX(timestamp_epoch) FROM ticks WHERE instrument_token=?", (555,)).fetchone()
    assert row is not None
    assert row[0] == receipt_epoch


def test_on_ticks_newer_same_symbol_option_tick_refreshes_symbol_age(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {555: "NIFTY", 556: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)

    current_epoch = {"value": 100.0}
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: current_epoch["value"])

    ws.start_depth_ws([555, 556], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_ticks(ticker, [{"instrument_token": 555, "last_price": 101.0, "exchange_timestamp": datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc)}])
    current_epoch["value"] = 105.0
    ticker.on_ticks(ticker, [{"instrument_token": 556, "last_price": 102.0, "exchange_timestamp": datetime(2026, 2, 19, 9, 31, tzinfo=timezone.utc)}])

    option_state = ws._option_runtime_state(
        now_epoch=105.0,
        tokens=[555, 556],
        expected_counts_by_symbol={"NIFTY": 2},
        min_required_by_symbol={"NIFTY": 1},
    )

    assert ws._SYMBOL_LAST_OPTION_TICK_TS["NIFTY"] == 105.0
    assert option_state["last_tick_ts_by_symbol"]["NIFTY"] == 105.0
    assert option_state["option_age_by_symbol"]["NIFTY"] == 0.0
    assert option_state["feed_block_reason_by_symbol"]["NIFTY"] == "OK"


def test_auth_failure_sets_auth_required_and_blocks_restarts(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    auth_marks = []
    restarts = {"count": 0}
    stops = {"count": 0}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    def _stop(reason="manual_stop"):
        stops["count"] += 1
        ws._STOP_REQUESTED = True

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "restart_depth_ws", lambda reason="unknown": restarts.__setitem__("count", restarts["count"] + 1))
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: auth_marks.append(kwargs) or {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "stop_depth_ws", _stop)

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 403, "invalid session")

    assert ws._AUTH_REQUIRED_LATCH is True
    assert auth_marks
    assert stops["count"] == 1
    assert restarts["count"] == 0


def test_network_error_restarts_without_auth_required(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    auth_marks = []
    restarts = {"count": 0}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", False, raising=False)
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: auth_marks.append(kwargs) or {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "restart_depth_ws", lambda reason="unknown": restarts.__setitem__("count", restarts["count"] + 1) or True)

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 1006, "connection closed by peer")

    assert restarts["count"] == 1
    assert auth_marks == []
    assert ws._AUTH_REQUIRED_LATCH is False


def test_network_error_uses_internal_reconnect_when_enabled(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    restarts = {"count": 0}
    soft = {"count": 0}

    def _factory(api_key, access_token, debug=True):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker

    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(ws, "restart_depth_ws", lambda reason="unknown": restarts.__setitem__("count", restarts["count"] + 1) or True)
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason="unknown": soft.__setitem__("count", soft["count"] + 1) or True,
    )

    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 1006, "connection closed by peer")

    assert restarts["count"] == 0
    assert soft["count"] == 1
