import time
import sqlite3
from datetime import datetime, timezone

from config import config as cfg
import core.kite_depth_ws as ws
import core.tick_store as tick_store


def test_ws_tick_ingestion_updates_tick_store(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
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
