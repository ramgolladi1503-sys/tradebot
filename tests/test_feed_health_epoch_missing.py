import sqlite3

from config import config as cfg
from core import freshness_sla


def test_feed_health_epoch_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS ticks (instrument_token INTEGER, timestamp_epoch REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS depth_snapshots (instrument_token INTEGER, timestamp_epoch REAL)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    freshness_sla._reset_cache_for_tests()

    payload = freshness_sla.get_freshness_status(force=True)
    assert payload["ok"] is False
    assert "ltp_missing" in payload["reasons"]
    assert "depth_missing" in payload["reasons"]
