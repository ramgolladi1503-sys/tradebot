import json
from pathlib import Path

from config import config as cfg
from core.feed_debug import get_feed_debug


def test_feed_debug_handles_missing_db_tables(tmp_path, monkeypatch):
    isolated_logs = tmp_path / "logs"
    isolated_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: isolated_logs)
    db_path = tmp_path / "missing.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    out = get_feed_debug(now_epoch=1700000000.0)
    assert isinstance(out, dict)
    assert out["last_db_tick_epoch"] is None
    assert out["last_depth_epoch"] is None


def test_feed_debug_counts_recent_distinct_tokens(tmp_path, monkeypatch):
    import sqlite3

    isolated_logs = tmp_path / "logs"
    isolated_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: isolated_logs)
    db_path = tmp_path / "ticks.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE ticks (
                timestamp TEXT,
                instrument_token INTEGER,
                last_price REAL,
                volume INTEGER,
                oi INTEGER,
                timestamp_epoch REAL,
                timestamp_iso TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO ticks (instrument_token, timestamp_epoch) VALUES (?, ?)",
            [
                (101, 999.0),
                (101, 998.5),
                (102, 997.0),
                (103, 970.0),
                (104, 1001.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    (isolated_logs / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "ts_epoch": 1000.0,
                "ws_connected": True,
                "subscribed_tokens_count": 0,
                "intended_tokens_count": 123,
            }
        ),
        encoding="utf-8",
    )
    out = get_feed_debug(now_epoch=1000.0)
    assert out["distinct_tokens_recent"] == 2
    assert out["observed_tokens_recent_count"] == 2
    assert out["observed_tokens_recent_available"] is True
    assert out["observed_tokens_recent_status"] == "ok"
    assert out["subscribed_tokens_count"] == 0
    assert out["subscribed_tokens_source"] == "snapshot_file"
    assert out["intended_tokens_count"] == 123
    assert out["intended_tokens_source"] == "snapshot_file"
