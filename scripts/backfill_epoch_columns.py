import sys
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg


def _parse_ts(ts_value):
    if ts_value is None:
        return None
    try:
        if isinstance(ts_value, (int, float)):
            return float(ts_value)
    except Exception:
        pass
    try:
        s = str(ts_value)
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def _backfill_table(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if "timestamp_epoch" not in cols or "timestamp_iso" not in cols:
        raise RuntimeError(f"{table} missing timestamp_epoch/timestamp_iso columns")

    rows = conn.execute(
        f"SELECT rowid, timestamp, timestamp_epoch FROM {table} WHERE timestamp_epoch IS NULL"
    ).fetchall()
    if not rows:
        return 0

    now = datetime.now(timezone.utc).timestamp()
    updated = 0
    for i, (rowid, ts, _) in enumerate(rows):
        epoch = _parse_ts(ts)
        if epoch is None:
            epoch = now - (i * 0.001)
        ts_iso = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        conn.execute(
            f"UPDATE {table} SET timestamp_epoch=?, timestamp_iso=? WHERE rowid=?",
            (epoch, ts_iso, rowid),
        )
        updated += 1
    return updated


def main():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    with sqlite3.connect(db) as conn:
        ticks_updated = _backfill_table(conn, "ticks")
        depth_updated = _backfill_table(conn, "depth_snapshots")
    print(f"Backfill complete: ticks={ticks_updated}, depth_snapshots={depth_updated}")


if __name__ == "__main__":
    main()
