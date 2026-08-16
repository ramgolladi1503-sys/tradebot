import json
import os
from pathlib import Path
from collections import deque

from core import market_data as md
from config import config as cfg


class _DummyNewsCal:
    def get_shock(self):
        return {}


class _DummyNewsText:
    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


def test_runtime_fixture_rebinds_trade_db_path(monkeypatch, tmp_path):
    expected = tmp_path / "runtime" / "db" / "DEFAULT.sqlite"
    assert Path(os.environ["TRADE_DB_PATH"]) == expected
    assert Path(cfg.TRADE_DB_PATH) == expected


class _DummyRegimeModel:
    def predict(self, _features):
        return {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.9, "RANGE": 0.1},
            "regime_entropy": 0.1,
            "unstable_regime_flag": False,
        }


def test_get_token_for_symbol_resolves_index_aliases(monkeypatch):
    md._SYMBOL_TO_TOKEN_CACHE.clear()
    monkeypatch.setattr(
        md.cfg,
        "INDEX_TOKEN_BY_SYMBOL",
        {"NIFTY": 0, "BANKNIFTY": 0, "SENSEX": 0},
        raising=False,
    )

    class _StubKite:
        def instruments(self):
            return [
                {"tradingsymbol": "NIFTY 50", "instrument_token": 256265},
                {"tradingsymbol": "NIFTY BANK", "instrument_token": 260105},
                {"tradingsymbol": "SENSEX", "instrument_token": 265},
            ]

    monkeypatch.setattr(md, "kite_client", _StubKite())

    assert md.get_token_for_symbol("NIFTY") == 256265
    assert md.get_token_for_symbol("BANKNIFTY") == 260105
    assert md.get_token_for_symbol("SENSEX") == 265


def test_index_quote_cache_stores_bid_ask_mid_ts_source(monkeypatch):
    monkeypatch.setattr(md.cfg, "DEPTH_WS_USE_SUBPROCESS", False, raising=False)
    monkeypatch.setattr(md.cfg, "FEED_USE_SUBPROCESS", False, raising=False)
    md._DATA_CACHE.clear()
    md.update_index_quote_snapshot(
        symbol="NIFTY",
        bid=100.0,
        ask=102.0,
        ts_epoch=1234.0,
        source="ws",
        book_source="depth",
        ltp=101.5,
        volume=456.0,
        last_price_source="ws_tick",
    )
    snap = md.get_index_quote_snapshot("NIFTY")
    assert snap["bid"] == 100.0
    assert snap["ask"] == 102.0
    assert snap["mid"] == 101.0
    assert snap["last_price"] == 101.5
    assert snap["volume"] == 456.0
    assert snap["ts_epoch"] == 1234.0
    assert snap["source"] == "ws"
    assert snap["book_source"] == "depth"
    assert snap["last_price_source"] == "ws_tick"


def test_resolve_index_quote_sim_ltp_only_synthetic(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="SIM",
        ltp=25000.0,
        depth=None,
    )
    assert out["quote_ok"] is True
    assert out["quote_source"] == "synthetic_index"
    assert out["bid"] is not None
    assert out["ask"] is not None
    assert out["ask"] > out["bid"]


def test_resolve_index_quote_sim_ltp100_depth_none_synthetic(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="SIM",
        ltp=100.0,
        depth=None,
    )
    assert out["quote_ok"] is True
    assert out["quote_source"] == "synthetic_index"
    assert out["bid"] is not None
    assert out["ask"] is not None
    assert out["ask"] > out["bid"]


def test_resolve_index_quote_live_ltp_only_synthesizes_when_depth_optional(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    monkeypatch.setattr(md.cfg, "INDEX_REQUIRE_DEPTH_LIVE", False, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="LIVE",
        ltp=25000.0,
        depth=None,
        market_open=True,
        ltp_age_sec=1.0,
    )
    assert out["quote_ok"] is True
    assert out["quote_source"] == "synthetic_index"
    assert out["bid"] is not None
    assert out["ask"] is not None
    assert out["ask"] > out["bid"]


def test_resolve_index_quote_live_ltp100_depth_none_fails_when_depth_required(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    monkeypatch.setattr(md.cfg, "INDEX_REQUIRE_DEPTH_LIVE", True, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="LIVE",
        ltp=100.0,
        depth=None,
        market_open=True,
        ltp_age_sec=1.0,
    )
    assert out["quote_ok"] is False
    assert out["quote_source"] == "missing_depth"
    assert out["bid"] is None
    assert out["ask"] is None


def test_resolve_index_quote_live_market_closed_allows_synthetic_with_fresh_ltp(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    monkeypatch.setattr(md.cfg, "OFFHOURS_MAX_LTP_AGE_SEC", 3600.0, raising=False)
    monkeypatch.setattr(md.cfg, "OFFHOURS_SYNTH_INDEX_SPREAD_BPS", 0.5, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="LIVE",
        ltp=25000.0,
        depth=None,
        market_open=False,
        ltp_age_sec=12.0,
    )
    assert out["quote_ok"] is True
    assert out["quote_source"] == "synthetic_index"
    assert out["bid"] is not None
    assert out["ask"] is not None
    assert out["ask"] > out["bid"]


def test_resolve_index_quote_live_market_closed_rejects_stale_ltp(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    monkeypatch.setattr(md.cfg, "OFFHOURS_MAX_LTP_AGE_SEC", 60.0, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="LIVE",
        ltp=25000.0,
        depth=None,
        market_open=False,
        ltp_age_sec=120.0,
    )
    assert out["quote_ok"] is False
    assert out["quote_source"] == "stale_ltp"
    assert out["bid"] is None
    assert out["ask"] is None


def test_resolve_index_quote_non_index_never_synthesizes(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    out = md.resolve_index_quote(
        symbol="RELIANCE",
        mode="SIM",
        ltp=100.0,
        depth=None,
    )
    assert out["quote_ok"] is False
    assert out["quote_source"] == "missing_depth"
    assert out["bid"] is None
    assert out["ask"] is None


def test_resolve_index_quote_depth_present_uses_depth(monkeypatch):
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    out = md.resolve_index_quote(
        symbol="NIFTY",
        mode="LIVE",
        ltp=25000.0,
        depth={"buy": [{"price": 24999.0}], "sell": [{"price": 25001.0}]},
    )
    assert out["quote_ok"] is True
    assert out["quote_source"] == "depth"
    assert out["bid"] == 24999.0
    assert out["ask"] == 25001.0
    assert out["mid"] == 25000.0


def test_resolve_index_quote_depth_present_prefers_live_tick_source_detail():
    pass


def test_get_ltp_index_uses_exchange_qualified_mapping(monkeypatch, tmp_path):
    monkeypatch.setattr(md.cfg, "DEPTH_WS_USE_SUBPROCESS", False, raising=False)
    monkeypatch.setattr(md.cfg, "FEED_USE_SUBPROCESS", False, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(md.cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(md.cfg, "DRY_RUN", False, raising=False)
    md._DATA_CACHE.clear()
    monkeypatch.setattr(md, "get_index_quote_snapshot", lambda symbol: {})
    md._LAST_GOOD_LTP.clear()
    md._INDEX_QUOTE_REQUEST_LOG_TS.clear()
    monkeypatch.setattr(md.cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    # Deliberately misconfigured to prove canonical mapping is still used.
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NIFTY"}, raising=False)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    class _StubKiteClient:
        def __init__(self):
            self.kite = object()
            self.calls = []

        def ensure(self):
            return None

        def ltp(self, symbols):
            self.calls.append(list(symbols))
            key = symbols[0]
            if key == "NSE:NIFTY 50":
                return {key: {"last_price": 25000.0}}
            return {}

    stub = _StubKiteClient()
    monkeypatch.setattr(md, "kite_client", stub)

    price = md.get_ltp("NIFTY")
    assert price == 25000.0
    assert stub.calls == [["NSE:NIFTY 50"]]
    req_log = Path(md.cfg.LOGS_ROOT) / "index_quote_requests.jsonl"
    assert req_log.exists()
    rows = [json.loads(line) for line in req_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(
        row.get("event") == "index_quote_request"
        and row.get("endpoint") == "ltp"
        and row.get("symbol") == "NIFTY"
        and row.get("requested_symbols") == ["NSE:NIFTY 50"]
        for row in rows
    )


def test_update_index_quote_snapshot_latest_ltp_used(monkeypatch):
    monkeypatch.setattr(md.cfg, "DEPTH_WS_USE_SUBPROCESS", False, raising=False)
    monkeypatch.setattr(md.cfg, "FEED_USE_SUBPROCESS", False, raising=False)
    md._DATA_CACHE.clear()
    md._LAST_GOOD_LTP.clear()
    monkeypatch.setattr(md.cfg, "KITE_USE_API", False, raising=False)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    md.update_index_quote_snapshot(
        symbol="NIFTY",
        bid=None,
        ask=None,
        ts_epoch=1000.0,
        source="ws",
        ltp=25000.0,
    )
    first = md.get_ltp("NIFTY")
    first_ts = (md._DATA_CACHE.get("NIFTY") or {}).get("ltp_ts_epoch")

    md.update_index_quote_snapshot(
        symbol="NIFTY",
        bid=None,
        ask=None,
        ts_epoch=1010.0,
        source="ws",
        ltp=25010.0,
    )
    second = md.get_ltp("NIFTY")
    second_ts = (md._DATA_CACHE.get("NIFTY") or {}).get("ltp_ts_epoch")

    assert first == 25000.0
    assert second == 25010.0
    assert isinstance(first_ts, float)
    assert isinstance(second_ts, float)
    assert second_ts > first_ts


def test_index_bidask_missing_log_rate_limited(monkeypatch, tmp_path):
    md._LIVE_QUOTE_ERROR_LAST_TS.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(md.cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(md.cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 60.0, raising=False)
    monkeypatch.setattr(md, "now_utc_epoch", lambda: 1000.0)
    md._log_index_bidask_missing("NIFTY", source="ws")
    # second call inside same minute must be suppressed
    monkeypatch.setattr(md, "now_utc_epoch", lambda: 1010.0)
    md._log_index_bidask_missing("NIFTY", source="ws")
    p = Path(md.cfg.LOGS_ROOT) / "live_quote_errors.jsonl"
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert (rows).__len__() == 1
    assert rows[0]["event_code"] == "index_bidask_missing"


def test_refresh_index_quote_from_rest_populates_bid_ask(monkeypatch):
    monkeypatch.setattr(md.cfg, "DEPTH_WS_USE_SUBPROCESS", False, raising=False)
    monkeypatch.setattr(md.cfg, "FEED_USE_SUBPROCESS", False, raising=False)
    md._DATA_CACHE.clear()
    md._INDEX_REST_QUOTE_REFRESH_TS.clear()
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(md.cfg, "DRY_RUN", False, raising=False)

    class _StubKite:
        def quote(self, keys):
            key = keys[0]
            return {
                key: {
                    "last_price": 25000.25,
                    "timestamp": 1710000000.0,
                    "depth": {
                        "buy": [{"price": 24999.9, "quantity": 100}],
                        "sell": [{"price": 25000.6, "quantity": 110}],
                    },
                }
            }

    monkeypatch.setattr(md.cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(md.cfg, "INDEX_REST_QUOTE_REFRESH_SEC", 5.0, raising=False)
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    monkeypatch.setattr(md.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(md.kite_client, "kite", _StubKite())

    ok = md._refresh_index_quote_from_rest("NIFTY", force=True)
    assert ok is True
    snap = md.get_index_quote_snapshot("NIFTY")
    assert snap["symbol"] == "NIFTY"
    assert snap["bid"] == 24999.9
    assert snap["ask"] == 25000.6
    assert snap["last_price"] == 25000.25
    assert snap["ts_epoch"] == 1710000000.0


def test_index_depth_missing_synthesizes_quote(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    md._DATA_CACHE.clear()
    fixed_now = md.now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
    fixed_epoch = fixed_now.timestamp()

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(md.cfg, "SYNTH_INDEX_SPREAD_PCT", 0.00005, raising=False)
    monkeypatch.setattr(md.cfg, "SYNTH_INDEX_SPREAD_ABS", 0.5, raising=False)
    monkeypatch.setattr(md, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(md, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(md, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(md, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(md, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(md, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(md, "now_utc_epoch", lambda: fixed_epoch)
    monkeypatch.setattr(md, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    def _fake_get_ltp(sym: str):
        md._DATA_CACHE.setdefault(sym, {})
        md._DATA_CACHE[sym]["ltp_source"] = "live"
        md._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_epoch
        return 25000.0

    monkeypatch.setattr(md, "get_ltp", _fake_get_ltp)

    rows = md.fetch_live_market_data()
    snap = next(r for r in rows if r.get("symbol") == "NIFTY" and r.get("instrument") == "OPT")
    assert snap["quote_ok"] is True
    assert snap["quote_source"] == "synthetic_index"
    assert snap["bid"] is not None
    assert snap["ask"] is not None
    assert snap["ask"] > snap["bid"]
    assert snap["index_quote_source"] == "synthetic_index"


def test_fetch_live_market_data_prefers_tick_backed_index_ltp_source():
    pass


def test_fetch_live_market_data_marks_depth_only_quote_source_degraded(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    md._DATA_CACHE.clear()
    fixed_epoch = 1710000000.0
    fixed_now = md.now_ist().replace(hour=10, minute=0, second=0, microsecond=0)

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(md.cfg, "DEPTH_WS_USE_SUBPROCESS", False, raising=False)
    monkeypatch.setattr(md.cfg, "FEED_USE_SUBPROCESS", False, raising=False)
    monkeypatch.setattr(md, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(md, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(md, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(md, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(md, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(md, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(md, "now_utc_epoch", lambda: fixed_epoch)
    monkeypatch.setattr(md, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    md.update_index_quote_snapshot(
        symbol="NIFTY",
        bid=24999.0,
        ask=25001.0,
        mid=25000.0,
        ts_epoch=fixed_epoch,
        source="ws",
        book_source="depth",
    )

    def _fake_get_ltp(sym: str):
        md._DATA_CACHE.setdefault(sym, {})
        md._DATA_CACHE[sym]["ltp_source"] = "live"
        md._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_epoch
        return 25000.0

    monkeypatch.setattr(md, "get_ltp", _fake_get_ltp)

    rows = md.fetch_live_market_data()
    snap = next(r for r in rows if r.get("symbol") == "NIFTY" and r.get("instrument") == "OPT")
    assert snap["quote_ok"] is True
    assert snap["quote_source"] == "depth"


def test_compute_tick_feature_summary_marks_warming_up_without_enough_real_samples():
    pass


def test_compute_tick_feature_summary_builds_real_features_from_tick_buffer():
    pass


def test_fetch_live_market_data_uses_tick_buffer_features_and_marks_ready():
    pass


def test_index_depth_missing_live_keeps_quote_false(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    md._DATA_CACHE.clear()
    fixed_now = md.now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
    fixed_epoch = fixed_now.timestamp()

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(md.cfg, "INDEX_REQUIRE_DEPTH_LIVE", True, raising=False)
    monkeypatch.setattr(md, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(md, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(md, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(md, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(md, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(md, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(md, "now_utc_epoch", lambda: fixed_epoch)
    monkeypatch.setattr(md, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(md, "is_open", lambda now_dt=None, segment="NSE_FNO": True)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    def _fake_get_ltp(sym: str):
        md._DATA_CACHE.setdefault(sym, {})
        md._DATA_CACHE[sym]["ltp_source"] = "live"
        md._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_epoch
        return 25000.0

    monkeypatch.setattr(md, "get_ltp", _fake_get_ltp)

    rows = md.fetch_live_market_data()
    snap = next(r for r in rows if r.get("symbol") == "NIFTY" and r.get("instrument") == "OPT")
    assert snap["quote_ok"] is False
    assert snap["quote_source"] == "missing_depth"
    assert snap["bid"] is None
    assert snap["ask"] is None
    assert snap["chain_source"] == "empty"


def test_index_depth_missing_live_offhours_allows_synthetic_and_offhours_chain(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    md._DATA_CACHE.clear()
    fixed_now = md.now_ist().replace(hour=6, minute=0, second=0, microsecond=0)
    fixed_epoch = fixed_now.timestamp()

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(md.cfg, "ALLOW_SYNTHETIC_CHAIN", True, raising=False)
    monkeypatch.setattr(md.cfg, "OFFHOURS_MAX_LTP_AGE_SEC", 3600.0, raising=False)
    monkeypatch.setattr(md, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(md, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(md, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(md, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(md, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(md, "now_utc_epoch", lambda: fixed_epoch)
    monkeypatch.setattr(md, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(md, "is_open", lambda now_dt=None, segment="NSE_FNO": False)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    def _fake_get_ltp(sym: str):
        md._DATA_CACHE.setdefault(sym, {})
        md._DATA_CACHE[sym]["ltp_source"] = "live"
        md._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_epoch
        return 25000.0

    def _fake_chain(_symbol, _ltp, force_synthetic=False, **_kwargs):
        if not force_synthetic:
            return []
        return [
            {
                "type": "CE",
                "strike": 25000,
                "ltp": 100.0,
                "bid": 99.0,
                "ask": 101.0,
                "quote_ok": True,
                "quote_live": False,
            }
        ]

    monkeypatch.setattr(md, "get_ltp", _fake_get_ltp)
    monkeypatch.setattr(md, "fetch_option_chain", _fake_chain)

    rows = md.fetch_live_market_data()
    snap = next(r for r in rows if r.get("symbol") == "NIFTY" and r.get("instrument") == "OPT")
    assert snap["quote_ok"] is True
    assert snap["quote_source"] == "synthetic_index"
    assert snap["chain_source"] == "synthetic_offhours"
    assert snap["market_open"] is False


def test_market_open_never_uses_synthetic_offhours_chain(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    md._DATA_CACHE.clear()
    fixed_epoch = 1710000000.0
    fixed_now = md.now_ist().replace(hour=10, minute=0, second=0, microsecond=0)

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(md.cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(md.cfg, "ALLOW_SYNTHETIC_CHAIN", True, raising=False)
    monkeypatch.setattr(md, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(md, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(md, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(md, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(md, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(md, "now_utc_epoch", lambda: fixed_epoch)
    monkeypatch.setattr(md, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(md, "is_open", lambda now_dt=None, segment="NSE_FNO": True)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)
    monkeypatch.setattr(md, "get_ltp", lambda _sym: 25000.0)
    monkeypatch.setattr(md, "fetch_option_chain", lambda *_args, **_kwargs: [])

    rows = md.fetch_live_market_data()
    snap = next(r for r in rows if r.get("symbol") == "NIFTY" and r.get("instrument") == "OPT")
    assert snap["chain_source"] == "empty"
    assert snap["market_open"] is True


def test_non_index_depth_missing_keeps_quote_false(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    md._DATA_CACHE.clear()
    fixed_epoch = 1710000000.0
    fixed_now = md.now_ist().replace(hour=10, minute=0, second=0, microsecond=0)

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["RELIANCE"], raising=False)
    monkeypatch.setattr(md.cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"}, raising=False)
    monkeypatch.setattr(md.cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(md, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(md, "_NEWS_CAL", _DummyNewsCal(), raising=False)
    monkeypatch.setattr(md, "_NEWS_TEXT", _DummyNewsText(), raising=False)
    monkeypatch.setattr(md, "_CROSS_ASSET", _DummyCross(), raising=False)
    monkeypatch.setattr(md, "fetch_option_chain", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(md, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(md, "now_utc_epoch", lambda: fixed_epoch)
    monkeypatch.setattr(md, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(md, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)

    def _fake_get_ltp(sym: str):
        md._DATA_CACHE.setdefault(sym, {})
        md._DATA_CACHE[sym]["ltp_source"] = "live"
        md._DATA_CACHE[sym]["ltp_ts_epoch"] = fixed_epoch
        return 1500.0

    monkeypatch.setattr(md, "get_ltp", _fake_get_ltp)

    rows = md.fetch_live_market_data()
    snap = next(r for r in rows if r.get("symbol") == "RELIANCE" and r.get("instrument") == "OPT")
    assert snap["quote_ok"] is False
    assert snap["quote_source"] == "none"
    assert snap["bid"] is None
    assert snap["ask"] is None
