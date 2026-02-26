from __future__ import annotations

import sqlite3
from pathlib import Path

from config import config as cfg
from scripts import repair_ticks


def test_repair_ticks_skips_when_db_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    missing_db = tmp_path / "data" / "missing.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(missing_db), raising=False)

    result = repair_ticks.main()

    assert result["status"] == "skipped"
    assert result["reason"] == "db_missing"


def test_repair_ticks_updates_bad_rows(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "data" / "trades.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE ticks (timestamp TEXT)")
        conn.execute("INSERT INTO ticks(timestamp) VALUES (?)", ("",))
        conn.execute("INSERT INTO ticks(timestamp) VALUES (?)", ("not-a-date",))
        conn.execute("INSERT INTO ticks(timestamp) VALUES (?)", ("2026-02-10T09:15:00",))
        conn.commit()

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)

    result = repair_ticks.main()

    assert result["status"] == "ok"
    assert result["repaired"] >= 2

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT timestamp FROM ticks").fetchall()
    timestamps = [row[0] for row in rows]
    assert all(str(ts).strip() for ts in timestamps)
