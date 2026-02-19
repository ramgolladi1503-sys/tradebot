import json

from core import market_data as md


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
