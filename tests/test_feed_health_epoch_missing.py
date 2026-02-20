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
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "SLA_REQUIRE_OPTIONS_DEPTH_LIVE", True, raising=False)
    monkeypatch.setattr(freshness_sla, "_mem_last_tick_epoch", lambda: None)
    monkeypatch.setattr(freshness_sla, "_latest_depth_epoch_from_store", lambda: None)
    monkeypatch.setattr(freshness_sla, "_depth_store_tokens", lambda: [])
    freshness_sla._reset_cache_for_tests()

    payload = freshness_sla.get_freshness_status(force=True)
    assert payload["ok"] is False
    assert "ltp_missing" in payload["reasons"]
    assert "depth_missing" in payload["reasons"]


def test_feed_health_sim_does_not_require_depth_for_index(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS ticks (instrument_token INTEGER, timestamp_epoch REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS depth_snapshots (instrument_token INTEGER, timestamp_epoch REAL)")
    conn.execute("INSERT INTO ticks (instrument_token, timestamp_epoch) VALUES (?, ?)", (256265, 1700000000.0))
    conn.commit()
    conn.close()

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(freshness_sla.time, "time", lambda: 1700000000.2)
    monkeypatch.setattr(freshness_sla, "_mem_last_tick_epoch", lambda: None)
    monkeypatch.setattr(freshness_sla, "_latest_depth_epoch_from_store", lambda: None)
    monkeypatch.setattr(freshness_sla, "_depth_store_tokens", lambda: [])
    freshness_sla._reset_cache_for_tests()

    payload = freshness_sla.get_freshness_status(force=True)
    assert payload["ok"] is True
    assert payload["state"] in {"OK", "DEGRADED"}
    assert "depth_missing" not in payload["reasons"]
    assert payload["depth"]["required"] is False
