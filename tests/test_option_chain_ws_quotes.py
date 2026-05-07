from __future__ import annotations


def test_ws_quotes_for_instruments_builds_kite_like_payload(monkeypatch):
    import core.option_chain as oc

    # Fake tick rows source (sqlite bulk read path).
    monkeypatch.setattr(
        oc,
        "get_latest_tick_rows_db_no_flush",
        lambda tokens: {int(tokens[0]): {"ltp": 123.45, "ts_epoch": 1000.0}},
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
