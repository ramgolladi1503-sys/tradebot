import json
import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import config as cfg

def _read_trades_db():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query("SELECT * FROM trades", conn)
    finally:
        conn.close()
    return df

def _read_execution_stats():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query("SELECT * FROM execution_stats", conn)
    finally:
        conn.close()
    return df

def _read_broker_fills():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query("SELECT * FROM broker_fills", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def compute_execution_analytics():
    trades = _read_trades_db()
    exec_stats = _read_execution_stats()
    broker_fills = _read_broker_fills()

    summary = {
        "timestamp": datetime.now().isoformat(),
        "fill_ratio": None,
        "avg_latency_ms": None,
        "avg_slippage": None,
        "instrument": {},
    }

    # Guard: no broker fills available
    if broker_fills.empty:
        summary["note"] = "No broker fills found; skipping execution analytics."
        return summary, []

    if not trades.empty:
        if "fill_price" in trades.columns and trades["fill_price"].notna().any():
            summary["fill_ratio"] = float(trades["fill_price"].notna().mean())
        if "latency_ms" in trades.columns and trades["latency_ms"].notna().any():
            summary["avg_latency_ms"] = float(trades["latency_ms"].dropna().mean())
        if "slippage" in trades.columns and trades["slippage"].notna().any():
            summary["avg_slippage"] = float(trades["slippage"].dropna().mean())

        if "instrument" in trades.columns:
            for inst, sub in trades.groupby("instrument"):
                inst_summary = {
                    "fill_ratio": float(sub["fill_price"].notna().mean()) if "fill_price" in sub.columns and sub["fill_price"].notna().any() else None,
                    "avg_latency_ms": float(sub["latency_ms"].dropna().mean()) if "latency_ms" in sub.columns and sub["latency_ms"].notna().any() else None,
                    "avg_slippage": float(sub["slippage"].dropna().mean()) if "slippage" in sub.columns and sub["slippage"].notna().any() else None,
                }
                summary["instrument"][inst] = inst_summary

    # Daily execution stats
    daily = []
    if not exec_stats.empty and "timestamp" in exec_stats.columns:
        exec_stats["timestamp"] = pd.to_datetime(exec_stats["timestamp"])
        exec_stats["date"] = exec_stats["timestamp"].dt.date
        daily_df = exec_stats.groupby(["date", "instrument"]).agg(
            slippage_bps=("slippage_bps", "mean"),
            latency_ms=("latency_ms", "mean"),
            fill_ratio=("fill_ratio", "mean")
        ).reset_index()
        daily = daily_df.to_dict(orient="records")

    return summary, daily

def write_execution_analytics(json_path="logs/execution_analytics.json", csv_path="logs/execution_analytics_daily.csv"):
    summary, daily = compute_execution_analytics()
    out = Path(json_path)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    if daily:
        df = pd.DataFrame(daily)
        df.to_csv(csv_path, index=False)
    return summary, daily
