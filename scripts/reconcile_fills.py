from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import sqlite3
from pathlib import Path
import pandas as pd
from datetime import timedelta
import sys
import argparse

from config import config as cfg

LOG_PATH = Path("data/trade_log.json")
UPDATES_PATH = Path("data/trade_updates.json")
OUT_CSV = Path("logs/reconciliation_report.csv")
OUT_JSON = Path("logs/reconciliation_summary.json")
OUT_HIST = Path("logs/reconciliation_history.json")

def load_trades():
    if not LOG_PATH.exists():
        return pd.DataFrame()
    rows = []
    with open(LOG_PATH, "r") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if UPDATES_PATH.exists():
        try:
            updates = []
            with open(UPDATES_PATH, "r") as f:
                for line in f:
                    if line.strip():
                        updates.append(json.loads(line))
            upd_df = pd.DataFrame(updates)
            if not upd_df.empty and "trade_id" in upd_df.columns:
                upd_df["timestamp"] = pd.to_datetime(upd_df["timestamp"])
                latest = upd_df.sort_values("timestamp").groupby("trade_id").tail(1)
                merge_cols = [c for c in latest.columns if c not in ("type", "timestamp")]
                df = df.merge(latest[merge_cols], on="trade_id", how="left", suffixes=("", "_upd"))
                for col in ["fill_price", "latency_ms", "slippage"]:
                    if f"{col}_upd" in df.columns:
                        df[col] = df[col].fillna(df[f"{col}_upd"])
                        df.drop(columns=[f"{col}_upd"], inplace=True)
        except Exception:
            pass
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df

def load_fills():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query("SELECT * FROM broker_fills", conn)
    finally:
        conn.close()
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df

def _confidence(match_type, time_diff_sec=None, price_diff=None):
    score = 0.4
    if match_type == "trade_id":
        score += 0.5
    elif match_type == "heuristic":
        score += 0.2
    if time_diff_sec is not None:
        if time_diff_sec <= 60:
            score += 0.1
        elif time_diff_sec <= 180:
            score += 0.05
        elif time_diff_sec > 600:
            score -= 0.1
    if price_diff is not None and abs(price_diff) <= 1:
        score += 0.05
    return max(0.0, min(1.0, score))

def reconcile(trades, fills, window_minutes=5):
    if trades.empty or fills.empty:
        return pd.DataFrame(), {"matched": 0, "unmatched_trades": len(trades), "unmatched_fills": len(fills)}

    fills = fills.sort_values("timestamp")
    trades = trades.sort_values("timestamp")
    results = []
    used_fills = set()

    for _, tr in trades.iterrows():
        match = None
        match_type = None
        if pd.notna(tr.get("trade_id")):
            mf = fills[fills["trade_id"] == tr["trade_id"]]
            if not mf.empty:
                match = mf.iloc[-1]
                match_type = "trade_id"
        if match is None:
            if pd.isna(tr["timestamp"]):
                continue
            start = tr["timestamp"] - timedelta(minutes=window_minutes)
            end = tr["timestamp"] + timedelta(minutes=window_minutes)
            cand = fills[
                (fills["timestamp"] >= start) &
                (fills["timestamp"] <= end) &
                (fills["symbol"] == tr.get("symbol")) &
                (fills["side"] == tr.get("side")) &
                (fills["qty"] == tr.get("qty"))
            ]
            if not cand.empty:
                match = cand.iloc[-1]
                match_type = "heuristic"
        if match is not None:
            used_fills.add(match.get("order_id") or match.get("trade_id"))
            time_diff = None
            if pd.notna(match.get("timestamp")) and pd.notna(tr.get("timestamp")):
                time_diff = abs((pd.to_datetime(match.get("timestamp")) - pd.to_datetime(tr.get("timestamp"))).total_seconds())
            results.append({
                "trade_id": tr.get("trade_id"),
                "symbol": tr.get("symbol"),
                "side": tr.get("side"),
                "qty": tr.get("qty"),
                "trade_ts": tr.get("timestamp"),
                "trade_entry": tr.get("entry"),
                "fill_price": match.get("price"),
                "fill_ts": match.get("timestamp"),
                "order_id": match.get("order_id"),
                "trade_match": True,
                "price_diff": (match.get("price") - tr.get("entry")) if pd.notna(match.get("price")) and pd.notna(tr.get("entry")) else None,
                "time_diff_sec": time_diff,
                "match_type": match_type,
                "confidence": _confidence(match_type, time_diff, (match.get("price") - tr.get("entry")) if pd.notna(match.get("price")) and pd.notna(tr.get("entry")) else None),
            })
        else:
            results.append({
                "trade_id": tr.get("trade_id"),
                "symbol": tr.get("symbol"),
                "side": tr.get("side"),
                "qty": tr.get("qty"),
                "trade_ts": tr.get("timestamp"),
                "trade_entry": tr.get("entry"),
                "fill_price": None,
                "fill_ts": None,
                "order_id": None,
                "trade_match": False,
                "price_diff": None,
                "time_diff_sec": None,
                "match_type": None,
                "confidence": 0.0,
            })

    matched = sum(1 for r in results if r["trade_match"])
    unmatched_trades = len(results) - matched
    unmatched_fills = len(fills) - len(used_fills)
    avg_conf = float(sum(r["confidence"] for r in results) / max(1, len(results)))
    summary = {
        "matched": matched,
        "unmatched_trades": unmatched_trades,
        "unmatched_fills": unmatched_fills,
        "match_rate": matched / max(1, len(results)),
        "avg_confidence": avg_conf,
    }
    return pd.DataFrame(results), summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tolerance-minutes", type=int, default=5)
    args = parser.parse_args()

    trades = load_trades()
    fills = load_fills()
    report, summary = reconcile(trades, fills, window_minutes=args.tolerance_minutes)
    OUT_CSV.parent.mkdir(exist_ok=True)
    report.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(summary, indent=2))
    # Append history
    history = []
    if OUT_HIST.exists():
        try:
            history = json.loads(OUT_HIST.read_text())
        except Exception:
            history = []
    history.append({"ts": pd.Timestamp.now().isoformat(), "match_rate": summary.get("match_rate", 0)})
    OUT_HIST.write_text(json.dumps(history[-1000:], indent=2))
    print(summary)
