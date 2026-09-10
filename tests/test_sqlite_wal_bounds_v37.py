import sqlite3

from config import config as cfg
from core import tick_store


def test_tick_writer_applies_wal_checkpoint_bound(tmp_path, monkeypatch):
    db = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db), raising=False)
    tick_store._INIT_DONE = False
    tick_store._INIT_DB_PATH = None
    tick_store.init_ticks()
    row = (
        "2026-09-06T09:15:00Z", 1, 100.0, 10, 2, 1_725_600_000.0,
        "2026-09-06T09:15:00Z", "RECEIPT", "exchange_timestamp",
        1_725_600_000.0, 1_725_600_000.0, False,
    )
    assert tick_store._write_rows([row]) is True
    with tick_store._conn() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA journal_size_limit").fetchone()[0] == 65_536
        assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 1
    wal = db.with_name(db.name + "-wal")
    assert not wal.exists() or wal.stat().st_size <= 65_536
