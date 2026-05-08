from __future__ import annotations


def test_ws_quotes_for_instruments_builds_kite_like_payload(monkeypatch):
    import core.option_chain as oc

    # Default behavior should be memory-first and must not hit SQLite on the hot path.
    monkeypatch.setattr(
        oc,
        "get_latest_tick_rows_db_no_flush",
        lambda tokens: (_ for _ in ()).throw(AssertionError("unexpected sqlite tick read")),
        raising=False,
    )
    monkeypatch.setattr(
        oc,
        "get_last_tick",
        lambda token, allow_db=True, decision_path=False: {"ltp": 123.45, "ts_epoch": 1000.0, "source": "memory"},
        raising=False,
    )

    class _DS:
        def get(self, instrument_token):
            return {"depth": {"buy": [{"price": 123.4}], "sell": [{"price": 123.5}]}, "ts_epoch": 1000.0}

    monkeypatch.setattr(oc, "depth_store", _DS(), raising=False)

    inst = {"tradingsymbol": "NIFTYTEST", "instrument_token": 111}
    quotes = oc._ws_quotes_for_instruments(exchange="NFO", instruments=[inst])
    assert "NFO:NIFTYTEST" in quotes
    q = quotes["NFO:NIFTYTEST"]
    assert q.get("last_price") == 123.45
    assert q.get("depth", {}).get("buy")
    assert q.get("depth", {}).get("sell")
    assert q.get("timestamp") == 1000.0


def test_ws_quotes_for_instruments_db_seeds_when_memory_ticks_missing(monkeypatch):
    import core.option_chain as oc

    # Force cold-start conditions: memory ticks missing.
    monkeypatch.setattr(
        oc,
        "get_last_tick",
        lambda token, allow_db=True, decision_path=False: None,
        raising=False,
    )
    called = {"n": 0}

    def _fake_db(tokens):
        called["n"] += 1
        return {int(tokens[0]): {"ltp": 222.0, "ts_epoch": 1234.0}}

    monkeypatch.setattr(oc, "get_latest_tick_rows_db_no_flush", _fake_db, raising=False)
    monkeypatch.setattr(oc, "now_utc_epoch", lambda: 1000.0, raising=False)
    monkeypatch.setattr(oc, "_WS_QUOTES_DB_SEED_LAST_EPOCH", 0.0, raising=False)

    class _DS:
        def get(self, instrument_token):
            return {"depth": {"buy": [{"price": 221.5}], "sell": [{"price": 222.5}]}, "ts_epoch": None}

    monkeypatch.setattr(oc, "depth_store", _DS(), raising=False)

    # Enable seed with no min interval for test determinism.
    monkeypatch.setattr(oc.cfg, "OPTION_CHAIN_WS_QUOTES_DB_SEED_ENABLE", True, raising=False)
    monkeypatch.setattr(oc.cfg, "OPTION_CHAIN_WS_QUOTES_DB_SEED_MIN_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(oc.cfg, "OPTION_CHAIN_WS_QUOTES_ALLOW_DB_FALLBACK", False, raising=False)

    inst = {"tradingsymbol": "NIFTYTEST", "instrument_token": 111}
    quotes = oc._ws_quotes_for_instruments(exchange="NFO", instruments=[inst])
    q = quotes["NFO:NIFTYTEST"]
    assert called["n"] == 1
    assert q.get("timestamp") == 1234.0
    assert q.get("last_price") == 222.0
