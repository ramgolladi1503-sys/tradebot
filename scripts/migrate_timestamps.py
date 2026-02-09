import sys
import time
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg


def _now_epoch():
    return time.time()


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_columns(conn, table, cols):
    cur = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    for col, col_type in cols.items():
        if col in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")


def _backfill_epoch_iso(conn, table, ts_col="timestamp", epoch_col="timestamp_epoch", iso_col="timestamp_iso"):
    cur = conn.execute(f"SELECT rowid, {ts_col}, {epoch_col}, {iso_col} FROM {table}")
    rows = cur.fetchall()
    updates = 0
    for rowid, ts, epoch, iso in rows:
        if epoch is not None and iso:
            continue
        now_epoch = _now_epoch()
        epoch_val = None
        if isinstance(ts, (int, float)):
            epoch_val = float(ts)
        else:
            try:
                epoch_val = datetime.fromisoformat(str(ts)).timestamp()
            except Exception:
                epoch_val = None
        if epoch_val is None:
            epoch_val = now_epoch - 0.001
        iso_val = iso or _iso_from_epoch(epoch_val)
        conn.execute(
            f"UPDATE {table} SET {epoch_col} = ?, {iso_col} = ? WHERE rowid = ?",
            (epoch_val, iso_val, rowid),
        )
        updates += 1
    return updates


def main():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    _ensure_columns(conn, "ticks", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})
    _ensure_columns(conn, "depth_snapshots", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})
    _ensure_columns(conn, "decision_events", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})
    _ensure_columns(conn, "broker_fills", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})
    _ensure_columns(conn, "execution_stats", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})
    _ensure_columns(conn, "trades", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})
    _ensure_columns(conn, "outcomes", {"timestamp_epoch": "REAL", "timestamp_iso": "TEXT"})

    stats = {}
    stats["ticks"] = _backfill_epoch_iso(conn, "ticks", "timestamp", "timestamp_epoch", "timestamp_iso")
    stats["depth_snapshots"] = _backfill_epoch_iso(conn, "depth_snapshots", "timestamp", "timestamp_epoch", "timestamp_iso")
    stats["decision_events"] = _backfill_epoch_iso(conn, "decision_events", "ts", "timestamp_epoch", "timestamp_iso")
    stats["broker_fills"] = _backfill_epoch_iso(conn, "broker_fills", "timestamp", "timestamp_epoch", "timestamp_iso")
    stats["execution_stats"] = _backfill_epoch_iso(conn, "execution_stats", "timestamp", "timestamp_epoch", "timestamp_iso")
    stats["trades"] = _backfill_epoch_iso(conn, "trades", "timestamp", "timestamp_epoch", "timestamp_iso")
    stats["outcomes"] = _backfill_epoch_iso(conn, "outcomes", "exit_time", "timestamp_epoch", "timestamp_iso")
    conn.commit()
    conn.close()
    print("migrate_timestamps:", stats)


if __name__ == "__main__":
    main()
