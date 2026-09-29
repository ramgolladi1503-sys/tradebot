import time
import sqlite3
from datetime import datetime, timezone

from config import config as cfg
import core.kite_depth_ws as ws
import core.tick_store as tick_store
from core.observation_lineage import current_tick_store_lineage


def test_ws_tick_ingestion_updates_tick_store(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    tick_store._LAST_TICK_EPOCH = None
    tick_store._LAST_TICK_BY_TOKEN.clear()

    token = 123456
    price = 25123.45
    now_ts = datetime.now(timezone.utc)
    sample_tick = {
        "instrument_token": token,
        "last_price": price,
        "exchange_timestamp": now_ts,
        "volume_traded": 101,
        "oi": 202,
    }

    ws.on_ticks(None, [sample_tick])

    ltp, tick_epoch = tick_store.get_ltp(token)
    assert ltp == price
    assert tick_epoch is not None
    assert tick_store.last_tick_epoch() is not None
    age = float(time.time()) - float(tick_epoch)
    assert 0.0 <= age < 2.0

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT MAX(timestamp_epoch) FROM ticks WHERE instrument_token=?", (token,)).fetchone()
    assert row is not None
    assert row[0] is not None


def test_ws_callback_event_envelope_reaches_process_local_lineage(monkeypatch, tmp_path):
    db_path = tmp_path / "callback_lineage.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", False, raising=False)
    tick_store._INIT_DONE = False
    tick_store._LAST_TICK_BY_TOKEN.clear()
    monkeypatch.setattr(ws, "_FEED_SESSION_ID", "lineage-test-session")
    monkeypatch.setattr(ws, "_FEED_ON_TICKS_ROW_SEQ", 0)
    monkeypatch.setitem(ws._TOKEN_TO_SYMBOL, 765432, "NIFTY")
    emitted = []
    monkeypatch.setattr(ws, "_NORMALIZED_TICK_SINK", emitted.append)

    ws.on_ticks(None, [{
        "instrument_token": 765432,
        "last_price": 25123.45,
        "exchange_timestamp": datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc),
        "volume_traded": 101,
        "oi": 202,
    }])

    assert len(emitted) == 1
    callback_event = emitted[0]
    assert callback_event["source_event_id"].startswith("lineage-test-session:")
    lineage = current_tick_store_lineage([765432])
    observed = lineage["tokens"]["765432"]
    assert observed["event_identity_status"] == "VERIFIED_EVENT_PAYLOAD"
    assert observed["source_event_id"] == callback_event["source_event_id"]
    assert observed["source_event_sha256"] == callback_event["source_event_sha256"]
    assert observed["source_event_payload"] == callback_event["source_event_payload"]
