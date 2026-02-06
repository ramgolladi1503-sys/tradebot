from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sqlite3
from pathlib import Path
import json
import pandas as pd
from datetime import datetime
import sys

from config import config as cfg
from core.telegram_alerts import send_telegram_message

OUT = Path("logs/sla_check.json")

def _last_ts(conn, table):
    try:
        df = pd.read_sql_query(f"SELECT timestamp FROM {table}", conn)
    except Exception:
        return None
    if df.empty:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    last = df["timestamp"].max()
    return last if pd.notna(last) else None

def _count_last_hour(conn, table):
    try:
        df = pd.read_sql_query(f"SELECT timestamp FROM {table}", conn)
    except Exception:
        return 0
    if df.empty:
        return 0
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    last = df["timestamp"].max()
    if pd.isna(last):
        return 0
    cutoff = last - pd.Timedelta(hours=1)
    return int((df["timestamp"] >= cutoff).sum())

if __name__ == "__main__":
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    now = datetime.now()
    tick_last = _last_ts(conn, "ticks")
    depth_last = _last_ts(conn, "depth_snapshots")
    tick_count = _count_last_hour(conn, "ticks")
    depth_count = _count_last_hour(conn, "depth_snapshots")
    conn.close()

    def _lag(ts):
        if not ts:
            return None
        try:
            t = pd.to_datetime(ts)
            return (now - t).total_seconds()
        except Exception:
            return None

    tick_lag = _lag(tick_last)
    depth_lag = _lag(depth_last)

    payload = {
        "tick_last": str(tick_last) if tick_last is not None else None,
        "depth_last": str(depth_last) if depth_last is not None else None,
        "tick_lag_sec": tick_lag,
        "depth_lag_sec": depth_lag,
        "ticks_last_hour": tick_count,
        "depth_last_hour": depth_count,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(payload)

    alerts = []
    if tick_lag is None or tick_lag > getattr(cfg, "SLA_MAX_TICK_LAG_SEC", 120):
        alerts.append("Tick feed lagging")
    if depth_lag is None or depth_lag > getattr(cfg, "SLA_MAX_DEPTH_LAG_SEC", 120):
        alerts.append("Depth feed lagging")
    if tick_count < getattr(cfg, "SLA_MIN_TICKS_PER_HOUR", 1000):
        alerts.append("Tick volume below SLA")
    if depth_count < getattr(cfg, "SLA_MIN_DEPTH_PER_HOUR", 200):
        alerts.append("Depth volume below SLA")
    if alerts:
        send_telegram_message("SLA alert: " + ", ".join(alerts))
