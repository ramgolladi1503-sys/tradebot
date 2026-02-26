from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sqlite3
from datetime import datetime, timedelta
import pandas as pd

from config import config as cfg


def _is_bad(ts):
    if ts is None:
        return True
    if isinstance(ts, str) and ts.strip().lower() in ("", "none", "nat", "nan"):
        return True
    return False


def main() -> dict:
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        print("[repair_ticks][WARN] trades.db not found")
        return {"status": "skipped", "reason": "db_missing", "path": str(db)}
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query("SELECT rowid, timestamp FROM ticks", conn)
    except Exception as exc:
        conn.close()
        print(f"[repair_ticks][WARN] ticks table read failed: {exc}")
        return {"status": "skipped", "reason": "ticks_table_unreadable", "detail": str(exc), "path": str(db)}
    if df.empty:
        print("No ticks found.")
        conn.close()
        return {"status": "ok", "repaired": 0, "path": str(db)}
    try:
        # Prefer explicit mixed parsing to avoid noisy inference warnings.
        ts_parsed = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed", utc=True)
    except TypeError:
        ts_parsed = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    bad_mask = ts_parsed.isna() | df["timestamp"].apply(_is_bad)
    bad = df.loc[bad_mask, ["rowid", "timestamp"]].itertuples(index=False, name=None)
    bad = list(bad)
    if not bad:
        print("No bad tick timestamps found.")
        conn.close()
        return {"status": "ok", "repaired": 0, "path": str(db)}

    # Set missing timestamps to a recent sequence ending now
    now = datetime.now()
    step = timedelta(seconds=1)
    base = now - step * len(bad)
    updates = []
    for i, (rowid, _) in enumerate(bad):
        ts = (base + step * i).isoformat()
        updates.append((ts, rowid))
    try:
        conn.executemany("UPDATE ticks SET timestamp = ? WHERE rowid = ?", updates)
        conn.commit()
        print(f"Repaired {len(bad)} tick timestamps.")
        return {"status": "ok", "repaired": int(len(bad)), "path": str(db)}
    except sqlite3.OperationalError as exc:
        # Degraded mode: keep ops pipeline running on readonly DB snapshots.
        print(f"[repair_ticks][WARN] skipped update: {exc}")
        return {"status": "skipped", "reason": "update_failed", "detail": str(exc), "path": str(db)}
    finally:
        conn.close()


if __name__ == "__main__":
    main()
