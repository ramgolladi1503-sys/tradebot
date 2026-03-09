from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from config import config as cfg
from core import feed_debug, freshness_sla, tick_store


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def test_tick_schema_migrates_legacy_ts_epoch_and_feed_reads_db(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_ticks.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE ticks (
                timestamp TEXT,
                instrument_token INTEGER,
                last_price REAL,
                volume INTEGER,
                oi INTEGER,
                ts_epoch REAL
            )
            """
        )
        now_epoch = float(time.time())
        conn.execute(
            "INSERT INTO ticks (timestamp, instrument_token, last_price, volume, oi, ts_epoch) VALUES (?,?,?,?,?,?)",
            ("", 256265, 25000.0, 10, 1000, now_epoch - 1.0),
        )
        conn.commit()

    tick_store.init_ticks()

    with sqlite3.connect(str(db_path)) as conn:
        cols = _columns(conn, "ticks")
        assert "timestamp_epoch" in cols
        max_epoch = tick_store.get_max_tick_epoch(conn)
        last_row = tick_store.get_last_tick_for_token(conn, 256265)
    assert max_epoch is not None
    assert last_row is not None
    assert float(last_row[0]) == 25000.0
    assert float(last_row[1]) == float(max_epoch)

    dbg = feed_debug.get_feed_debug(now_epoch=time.time())
    assert dbg["last_db_tick_epoch"] is not None
    assert dbg["last_db_tick_age_sec"] is not None
    assert float(dbg["last_db_tick_age_sec"]) >= 0.0

    freshness_sla._reset_cache_for_tests()
    monkeypatch.setattr(freshness_sla, "is_market_open_ist", lambda: True)
    status = freshness_sla.get_freshness_status(force=True)
    assert (status.get("ltp") or {}).get("age_sec") is not None


def test_no_ticks_sql_uses_ts_epoch_column():
    repo_root = Path(__file__).resolve().parents[1]
    scan_dirs = ("core", "dashboard", "scripts", "strategies", "runtime", "tools")
    violations: list[tuple[Path, str]] = []

    for folder in scan_dirs:
        root = repo_root / folder
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            # Multiline SQL blocks in triple-quoted strings.
            for block in re.finditer(r"([\"']{3})(.*?)(\1)", text, flags=re.DOTALL):
                body = str(block.group(2) or "").lower()
                if "from ticks" in body and "ts_epoch" in body:
                    violations.append((path, "triple_quote_sql_from_ticks_uses_ts_epoch"))
                    break
            # Single-line SQL strings.
            if any("from ticks" in line.lower() and "ts_epoch" in line.lower() for line in text.splitlines()):
                violations.append((path, "single_line_sql_from_ticks_uses_ts_epoch"))

    assert not violations, "ticks SQL uses ts_epoch:\n" + "\n".join(
        f"{p}: {pat}" for p, pat in violations
    )


def test_get_max_tick_epoch_with_current_schema(monkeypatch, tmp_path):
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    tick_store.init_ticks()
    now_epoch = float(time.time())
    tick_store.insert_tick(
        ts=now_epoch - 2.0,
        token=111,
        last_price=101.5,
        volume=10,
        oi=100,
    )
    tick_store.insert_tick(
        ts=now_epoch - 1.0,
        token=111,
        last_price=102.0,
        volume=11,
        oi=105,
    )
    with sqlite3.connect(str(db_path)) as conn:
        max_epoch = tick_store.get_max_tick_epoch(conn)
        last_tick = tick_store.get_last_tick_for_token(conn, 111)
    assert max_epoch is not None
    assert abs(float(max_epoch) - float(now_epoch - 1.0)) < 5.0
    assert last_tick is not None
    assert float(last_tick[0]) == 102.0
    assert abs(float(last_tick[1]) - float(max_epoch)) < 0.001
