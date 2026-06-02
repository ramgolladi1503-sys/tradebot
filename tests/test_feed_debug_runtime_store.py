import sqlite3
import pytest

from config import config as cfg
from core.feed.runtime_store import _db_path, write_runtime_snapshot
from core.feed_debug import get_feed_debug
from core.fs_utils import ensure_parent_dir


def _seed_ticks(db_path, rows):
    ensure_parent_dir(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticks (
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
        for token, ts_epoch in rows:
            conn.execute(
                "INSERT INTO ticks (instrument_token, timestamp_epoch, last_price) VALUES (?, ?, ?)",
                (token, float(ts_epoch), 100.0),
            )


def test_feed_debug_uses_feed_runtime_row_when_present(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime" / "trades.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: logs_path)

    now_ts = 1_700_000_000.0
    write_runtime_snapshot(
        {
            "ts_epoch": now_ts,
            "ws_connected": True,
            "subscribed_tokens_count": 73,
            "subscribed_tokens_sample": [1, 2, 3],
            "last_ws_tick_epoch": now_ts - 0.5,
            "source": "unit",
        }
    )

    payload = get_feed_debug(now_epoch=now_ts + 1.0)
    assert payload["ws_connected"] is True
    assert payload["ws_connected_source"] == "feed_runtime"
    assert payload["subscribed_tokens_count"] == 73


def test_feed_debug_infers_connected_when_ticks_recent(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime" / "trades.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: logs_path)

    now_ts = 1_700_000_100.0
    _seed_ticks(db_path, [(101, now_ts - 1.0), (102, now_ts - 0.5)])
    monkeypatch.setattr(cfg, "FEED_DB_MAX_STALENESS_SEC", 8.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_DB_TOKEN_WINDOW_SEC", 10.0, raising=False)

    payload = get_feed_debug(now_epoch=now_ts)
    assert payload["ws_connected"] is True
    assert payload["ws_connected_source"] == "inferred_ticks"
    assert payload["subscribed_tokens_count"] == 2


def test_feed_debug_reports_disconnected_when_ticks_stale(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime" / "trades.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: logs_path)

    now_ts = 1_700_000_300.0
    _seed_ticks(db_path, [(201, now_ts - 30.0)])
    monkeypatch.setattr(cfg, "FEED_DB_MAX_STALENESS_SEC", 8.0, raising=False)

    payload = get_feed_debug(now_epoch=now_ts)
    assert payload["ws_connected"] is False
    assert payload["ws_connected_source"] == "inferred_ticks"


def test_runtime_store_db_path_fails_deterministically_when_parent_is_file(monkeypatch, tmp_path):
    blocking_parent = tmp_path / "blocked-parent"
    blocking_parent.write_text("not-a-directory", encoding="utf-8")
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(blocking_parent / "runtime.sqlite"), raising=False)

    with pytest.raises(NotADirectoryError, match="path_exists_as_file"):
        _db_path()
