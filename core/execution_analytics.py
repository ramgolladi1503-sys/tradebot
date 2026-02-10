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
    fill_quality = _read_fill_quality_daily()

    summary = {
        "timestamp": datetime.now().isoformat(),
        "fill_ratio": None,
        "partial_fill_rate": None,
        "avg_latency_ms": None,
        "avg_slippage": None,
        "instrument": {},
        "execution_quality": {},
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

    # attach execution quality summary (from fill_quality)
    try:
        if fill_quality:
            latest_day = sorted(fill_quality.keys())[-1]
            summary["execution_quality"] = fill_quality.get(latest_day, {})
    except Exception:
        pass

    # Optional: derive partial fill rate from fill quality event log if present.
    try:
        fq_events = _read_fill_quality_events()
        if fq_events:
            total = len(fq_events)
            partial = sum(1 for ev in fq_events if str(ev.get("fill_status", "")).upper() == "PARTIAL")
            summary["partial_fill_rate"] = round(partial / max(total, 1), 4)
    except Exception:
        pass

    return summary, daily


def _read_fill_quality_daily():
    path = Path("logs/fill_quality_daily.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_fill_quality_events(max_rows=5000):
    path = Path("logs/fill_quality.jsonl")
    if not path.exists():
        return []
    rows = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if max_rows and len(rows) > max_rows:
            return rows[-max_rows:]
        return rows
    except Exception:
        return []

def write_execution_analytics(json_path="logs/execution_analytics.json", csv_path="logs/execution_analytics_daily.csv"):
    summary, daily = compute_execution_analytics()
    out = Path(json_path)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    if daily:
        df = pd.DataFrame(daily)
        df.to_csv(csv_path, index=False)
    return summary, daily
