import sqlite3
import time

from config import config as cfg
from core import freshness_sla, tick_store


def _init_tables(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS ticks (instrument_token INTEGER, timestamp_epoch REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS depth_snapshots (instrument_token INTEGER, timestamp_epoch REAL)")


def test_feed_freshness_normalizes_ms_epochs(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(db_path)
    _init_tables(conn)
    now = time.time()
    ms_epoch = (now - 10.0) * 1000.0
    conn.execute("INSERT INTO ticks (instrument_token, timestamp_epoch) VALUES (?,?)", (111, ms_epoch))
    conn.execute("INSERT INTO depth_snapshots (instrument_token, timestamp_epoch) VALUES (?,?)", (111, ms_epoch))
    conn.commit()
    conn.close()

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    freshness_sla._reset_cache_for_tests()

    payload = freshness_sla.get_freshness_status(force=True)
    ltp_age = (payload.get("ltp") or {}).get("age_sec")
    depth_age = (payload.get("depth") or {}).get("age_sec")
    assert ltp_age is not None
    assert abs(ltp_age - 10.0) < 2.0
    assert depth_age is not None
    assert abs(depth_age - 10.0) < 2.0


def test_feed_freshness_uses_db_even_if_memory_epoch_is_newer(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(db_path)
    _init_tables(conn)
    now = time.time()
    # DB tick is 20s old.
    conn.execute("INSERT INTO ticks (instrument_token, timestamp_epoch) VALUES (?,?)", (222, now - 20.0))
    conn.commit()
    conn.close()

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_STALE_QUOTES", False, raising=False)
    monkeypatch.setattr(tick_store, "_LAST_TICK_EPOCH", now)  # Should be ignored by SLA path.
    freshness_sla._reset_cache_for_tests()

    payload = freshness_sla.get_freshness_status(symbol="NIFTY", tokens=[222], force=True)
    assert payload["stale_tokens"] == [222]
    assert payload["ltp"]["source"] == "ticks_db_filtered"
    assert (payload.get("max_tick_age_sec") or 0.0) >= 18.0
