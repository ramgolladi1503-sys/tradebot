from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import sqlite3
import json
import pandas as pd

from config import config as cfg
from core.telegram_alerts import send_telegram_message
from core.incidents import trigger_feed_stale
from core.time_utils import now_utc_epoch, now_ist, is_market_open_ist

OUT = Path("logs/sla_check.json")


def _last_ts_epoch(conn, table, col):
    try:
        df = pd.read_sql_query(f"SELECT {col} FROM {table}", conn)
    except Exception:
        return None
    if df.empty:
        return None
    ser = pd.to_numeric(df[col], errors="coerce")
    if ser.dropna().empty:
        return None
    return float(ser.dropna().max())


def _count_last_hour_epoch(conn, table, col):
    try:
        df = pd.read_sql_query(f"SELECT {col} FROM {table}", conn)
    except Exception:
        return 0
    if df.empty:
        return 0
    ser = pd.to_numeric(df[col], errors="coerce").dropna()
    if ser.empty:
        return 0
    last = float(ser.max())
    cutoff = last - 3600.0
    return int((ser >= cutoff).sum())


def _count_last_min_epoch(conn, table, col, now_epoch):
    try:
        df = pd.read_sql_query(f"SELECT {col} FROM {table}", conn)
    except Exception:
        return 0
    if df.empty:
        return 0
    ser = pd.to_numeric(df[col], errors="coerce").dropna()
    if ser.empty:
        return 0
    cutoff = float(now_epoch) - 60.0
    return int((ser >= cutoff).sum())


if __name__ == "__main__":
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    now_epoch = now_utc_epoch()
    now_ist_str = now_ist().isoformat()
    market_open = is_market_open_ist()
    tick_last_epoch = _last_ts_epoch(conn, "ticks", "timestamp_epoch")
    depth_last_epoch = _last_ts_epoch(conn, "depth_snapshots", "timestamp_epoch")
    tick_count = _count_last_hour_epoch(conn, "ticks", "timestamp_epoch")
    depth_count = _count_last_hour_epoch(conn, "depth_snapshots", "timestamp_epoch")
    tick_msgs_min = _count_last_min_epoch(conn, "ticks", "timestamp_epoch", now_epoch)
    depth_msgs_min = _count_last_min_epoch(conn, "depth_snapshots", "timestamp_epoch", now_epoch)
    conn.close()

    def _lag(epoch):
        if epoch is None:
            return None
        try:
            return float(now_epoch) - float(epoch)
        except Exception:
            return None

    tick_lag = _lag(tick_last_epoch)
    depth_lag = _lag(depth_last_epoch)

    payload = {
        "ts_epoch": now_epoch,
        "ts_ist": now_ist_str,
        "market_open": market_open,
        "tick_last": None,
        "depth_last": None,
        "tick_last_epoch": tick_last_epoch,
        "depth_last_epoch": depth_last_epoch,
        "tick_epoch_missing": tick_last_epoch is None,
        "depth_epoch_missing": depth_last_epoch is None,
        "tick_lag_sec": tick_lag,
        "depth_lag_sec": depth_lag,
        "ticks_last_hour": tick_count,
        "depth_last_hour": depth_count,
        "tick_msgs_last_min": tick_msgs_min,
        "depth_msgs_last_min": depth_msgs_min,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(payload)

    alerts = []
    if market_open:
        if tick_last_epoch is None:
            alerts.append("Tick epoch missing")
        if depth_last_epoch is None:
            alerts.append("Depth epoch missing")
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
            try:
                trigger_feed_stale({
                    "alerts": alerts,
                    "tick_lag_sec": tick_lag,
                    "depth_lag_sec": depth_lag,
                    "ts_ist": now_ist_str,
                })
            except Exception as exc:
                print(f"[INCIDENT_ERROR] feed_stale trigger err={exc}")
