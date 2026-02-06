import sqlite3
from pathlib import Path

from core import tick_store


def _count_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM ticks")
        return cur.fetchone()[0]


def test_duplicate_ticks_do_not_crash(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.db"
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path))

    tick_store.insert_tick("2026-01-01T09:15:00", 123, 100.0, 10, 5)
    tick_store.insert_tick("2026-01-01T09:15:00", 123, 100.0, 10, 5)

    assert db_path.exists()
    assert _count_rows(db_path) >= 2


def test_stale_or_missing_timestamp_is_normalized(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.db"
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path))

    tick_store.insert_tick(None, 321, 101.0, 11, 6)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT timestamp FROM ticks LIMIT 1")
        ts = cur.fetchone()[0]
    assert ts is not None
    assert isinstance(ts, str)
