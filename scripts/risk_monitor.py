from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import json
from pathlib import Path
import pandas as pd
import sys

from config import config as cfg
from core.telegram_alerts import send_telegram_message

LOG_PATH = Path("data/trade_log.json")
OUT_PATH = Path("logs/risk_monitor.json")

def compute_daily_pnl():
    if not LOG_PATH.exists():
        return None
    rows = []
    with open(LOG_PATH, "r") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "timestamp" not in df.columns:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["pnl"] = (df["exit_price"].fillna(df["entry"]) - df["entry"]) * df["qty"]
    df.loc[df["side"] == "SELL", "pnl"] *= -1
    daily = df.groupby("date")["pnl"].sum().reset_index()
    return daily

if __name__ == "__main__":
    daily = compute_daily_pnl()
    if daily is None or daily.empty:
        print("No trade data to monitor.")
    else:
        latest = daily.iloc[-1]
        payload = {"date": str(latest["date"]), "pnl": float(latest["pnl"])}
        OUT_PATH.parent.mkdir(exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2))
        print(payload)
        if latest["pnl"] <= -abs(getattr(cfg, "DAILY_LOSS_LIMIT", cfg.CAPITAL * cfg.MAX_DAILY_LOSS)):
            send_telegram_message(f"Risk monitor alert: daily PnL {latest['pnl']:.2f} breached limit.")
