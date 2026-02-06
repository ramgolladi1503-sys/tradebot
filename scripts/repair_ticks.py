from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import sys
import pandas as pd

from config import config as cfg

def _is_bad(ts):
    if ts is None:
        return True
    if isinstance(ts, str) and ts.strip().lower() in ("", "none", "nat", "nan"):
        return True
    return False

if __name__ == "__main__":
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    df = pd.read_sql_query("SELECT rowid, timestamp FROM ticks", conn)
    if df.empty:
        print("No ticks found.")
        conn.close()
        raise SystemExit(0)
    ts_parsed = pd.to_datetime(df["timestamp"], errors="coerce")
    bad_mask = ts_parsed.isna() | df["timestamp"].apply(_is_bad)
    bad = df.loc[bad_mask, ["rowid", "timestamp"]].itertuples(index=False, name=None)
    bad = list(bad)
    if not bad:
        print("No bad tick timestamps found.")
        conn.close()
        raise SystemExit(0)

    # Set missing timestamps to a recent sequence ending now
    now = datetime.now()
    step = timedelta(seconds=1)
    base = now - step * len(bad)
    updates = []
    for i, (rowid, _) in enumerate(bad):
        ts = (base + step * i).isoformat()
        updates.append((ts, rowid))
    conn.executemany("UPDATE ticks SET timestamp = ? WHERE rowid = ?", updates)
    conn.commit()
    conn.close()
    print(f"Repaired {len(bad)} tick timestamps.")
