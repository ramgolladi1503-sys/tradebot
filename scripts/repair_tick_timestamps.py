from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sqlite3
from pathlib import Path
from datetime import datetime
import sys

from config import config as cfg

if __name__ == "__main__":
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "SELECT COUNT(*) FROM ticks WHERE timestamp IS NULL OR timestamp = '' OR timestamp = 'None' OR timestamp = 'NaT' OR timestamp = 'nan'"
    )
    missing = cur.fetchone()[0]
    if missing == 0:
        print("No missing tick timestamps.")
        conn.close()
        raise SystemExit(0)
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE ticks SET timestamp=? WHERE timestamp IS NULL OR timestamp = '' OR timestamp = 'None' OR timestamp = 'NaT' OR timestamp = 'nan'",
        (now,),
    )
    conn.commit()
    conn.close()
    print(f"Updated {missing} tick rows with synthetic timestamp {now}")
