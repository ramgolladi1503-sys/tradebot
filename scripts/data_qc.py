from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sqlite3
from pathlib import Path
import json
import pandas as pd
import sys

from config import config as cfg

OUT = Path("logs/data_qc.json")

def _qc_table(conn, table, ts_col="timestamp"):
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    except Exception:
        return {"table": table, "rows": 0, "error": "missing"}
    if df.empty:
        return {"table": table, "rows": 0}
    res = {"table": table, "rows": int(len(df))}
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        res["null_ts"] = int(df[ts_col].isna().sum())
        res["min_ts"] = str(df[ts_col].min())
        res["max_ts"] = str(df[ts_col].max())
    # null rate (focus on timestamp for ticks/trades)
    if table in ("ticks", "trades"):
        null_rate = float(df[ts_col].isna().mean()) if ts_col in df.columns else 0.0
    else:
        null_rate = float(df.isna().mean().max())
    res["max_null_rate"] = null_rate
    res["null_rate_ok"] = null_rate <= getattr(cfg, "QC_MAX_NULL_RATE", 0.1)
    return res

if __name__ == "__main__":
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    qc = [
        _qc_table(conn, "ticks"),
        _qc_table(conn, "depth_snapshots"),
        _qc_table(conn, "trades"),
        _qc_table(conn, "broker_fills"),
    ]
    conn.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(qc, indent=2))
    print(qc)
