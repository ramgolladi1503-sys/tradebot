import json

from core import market_data as md


class _DummyNewsCal:
    def get_shock(self):
        return {}


class _DummyNewsText:
    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


class _DummyRegimeModel:
    def predict(self, _features):
        return {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.9, "RANGE": 0.1},
            "regime_entropy": 0.1,
            "unstable_regime_flag": False,
        }


def test_index_quote_cache_stores_bid_ask_mid_ts_source():
    md._DATA_CACHE.clear()
    md.update_index_quote_snapshot(
        symbol="NIFTY",
        bid=100.0,
        ask=102.0,
        ts_epoch=1234.0,
        source="ws",
    )
    snap = md.get_index_quote_snapshot("NIFTY")
    assert snap["bid"] == 100.0
    assert snap["ask"] == 102.0
    assert snap["mid"] == 101.0
    assert snap["ts_epoch"] == 1234.0
    assert snap["source"] == "ws"


def test_index_bidask_missing_log_rate_limited(monkeypatch, tmp_path):
    md._INDEX_BIDASK_MISSING_LOG_TS.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(md.cfg, "INDEX_BIDASK_MISSING_LOG_SEC", 60.0, raising=False)
    monkeypatch.setattr(md, "now_utc_epoch", lambda: 1000.0)
    md._log_index_bidask_missing("NIFTY", source="ws")
    # second call inside same minute must be suppressed
    monkeypatch.setattr(md, "now_utc_epoch", lambda: 1010.0)
    md._log_index_bidask_missing("NIFTY", source="ws")
    p = tmp_path / "logs" / "live_quote_errors.jsonl"
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["event"] == "index_bidask_missing"


def test_refresh_index_quote_from_rest_populates_bid_ask(monkeypatch):
    md._DATA_CACHE.clear()
    md._INDEX_REST_QUOTE_REFRESH_TS.clear()

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
    fixed_epoch = 1710000000.0
    fixed_now = md.now_ist().replace(hour=10, minute=0, second=0, microsecond=0)

    monkeypatch.setattr(md.cfg, "SYMBOLS", ["NIFTY"], raising=False)
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
