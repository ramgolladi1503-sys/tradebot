from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
from pathlib import Path
import pandas as pd
import sys

from core.trade_store import insert_daily_stats
from config import config as cfg
from core.telegram_alerts import send_telegram_message

LOG_PATH = Path("data/trade_log.json")
UPDATES_PATH = Path("data/trade_updates.json")

def load_log():
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
                for col in ["exit_price", "exit_time", "actual", "r_multiple", "r_label", "fill_price", "latency_ms", "slippage"]:
                    if f"{col}_upd" in df.columns:
                        df[col] = df[col].fillna(df[f"{col}_upd"])
                        df.drop(columns=[f"{col}_upd"], inplace=True)
        except Exception:
            pass
    return df

def compute_daily(df):
    if df.empty or "timestamp" not in df.columns:
        return []
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["exit_price"] = df["exit_price"].fillna(df["entry"])
    df["pnl"] = (df["exit_price"] - df["entry"]) * df["qty"]
    df.loc[df["side"] == "SELL", "pnl"] *= -1
    daily = []
    for date, sub in df.groupby("date"):
        pnl = sub["pnl"].sum()
        wins = (sub["pnl"] > 0).sum()
        losses = (sub["pnl"] < 0).sum()
        win_rate = wins / max(1, len(sub))
        gains = sub[sub["pnl"] > 0]["pnl"].sum()
        loss = abs(sub[sub["pnl"] < 0]["pnl"].sum())
        pf = gains / loss if loss > 0 else None
        # daily sharpe on trade pnl
        sharpe = None
        if sub["pnl"].std() and len(sub) > 2:
            sharpe = sub["pnl"].mean() / sub["pnl"].std()
        # drawdown
        cum = sub["pnl"].cumsum()
        dd = (cum - cum.cummax()).min() if len(cum) > 0 else 0
        daily.append({
            "date": str(date),
            "trades": int(len(sub)),
            "pnl": float(pnl),
            "win_rate": float(win_rate),
            "profit_factor": float(pf) if pf is not None else None,
            "sharpe": float(sharpe) if sharpe is not None else None,
            "max_drawdown": float(dd),
        })
    return daily

if __name__ == "__main__":
    df = load_log()
    daily = compute_daily(df)
    for row in daily:
        insert_daily_stats(row)
    if daily:
        latest = daily[-1]
        pf = latest.get("profit_factor")
        sh = latest.get("sharpe")
        alerts = []
        if pf is not None and pf < getattr(cfg, "MIN_DAILY_PF", 1.1):
            alerts.append(f"PF {pf:.2f} below {cfg.MIN_DAILY_PF}")
        if sh is not None and sh < getattr(cfg, "MIN_DAILY_SHARPE", 0.2):
            alerts.append(f"Sharpe {sh:.2f} below {cfg.MIN_DAILY_SHARPE}")
        if alerts:
            send_telegram_message("Daily performance alert: " + ", ".join(alerts))

        # Soft-kill if PF/Sharpe below thresholds N consecutive days
        n = getattr(cfg, "PERF_ALERT_DAYS", 3)
        recent = daily[-n:] if len(daily) >= n else []
        if recent and len(recent) == n:
            bad = True
            for r in recent:
                pf_r = r.get("profit_factor")
                sh_r = r.get("sharpe")
                if pf_r is None or pf_r >= getattr(cfg, "MIN_DAILY_PF", 1.1):
                    bad = False
                if sh_r is None or sh_r >= getattr(cfg, "MIN_DAILY_SHARPE", 0.2):
                    bad = False
            if bad:
                from core import risk_halt
                payload = risk_halt.set_halt("Soft-kill: PF/Sharpe below thresholds", {"days": n})
                send_telegram_message(f"Soft-kill triggered for {n} days of poor PF/Sharpe.")
    print(f"Daily rollup rows: {len(daily)}")
