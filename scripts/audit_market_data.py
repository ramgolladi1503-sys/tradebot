from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import sqlite3
from pathlib import Path
import sys

from config import config as cfg

OUT = Path("logs/data_audit.json")

def audit():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        return {"error": "no trades.db found"}
    conn = sqlite3.connect(db)
    res = {}
    try:
        res["ticks"] = conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
        res["depth"] = conn.execute("SELECT COUNT(*) FROM depth_snapshots").fetchone()[0]
        res["tick_min_ts"] = conn.execute("SELECT MIN(timestamp) FROM ticks").fetchone()[0]
        res["tick_max_ts"] = conn.execute("SELECT MAX(timestamp) FROM ticks").fetchone()[0]
        res["depth_min_ts"] = conn.execute("SELECT MIN(timestamp) FROM depth_snapshots").fetchone()[0]
        res["depth_max_ts"] = conn.execute("SELECT MAX(timestamp) FROM depth_snapshots").fetchone()[0]
    except Exception as e:
        res["error"] = str(e)
    conn.close()
    return res

if __name__ == "__main__":
    payload = audit()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(payload)
