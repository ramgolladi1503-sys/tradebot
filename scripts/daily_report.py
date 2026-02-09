from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import sys
import json
import pandas as pd
from core.time_utils import now_ist
from pathlib import Path
import smtplib
from email.mime.text import MIMEText

from config import config as cfg
from core.telegram_alerts import send_telegram_message

LOG_PATH = Path("data/trade_log.json")
OUT_DIR = Path("logs")
OUT_DIR.mkdir(exist_ok=True)

if not LOG_PATH.exists():
    print("No trade_log.json found.")
    raise SystemExit(1)

rows = []
with open(LOG_PATH, "r") as f:
    for line in f:
        if not line.strip():
            continue
        rows.append(json.loads(line))

df = pd.DataFrame(rows)
if df.empty:
    print("No trades to report.")
    raise SystemExit(0)
if "timestamp" not in df.columns:
    print("Trade log missing timestamp field.")
    raise SystemExit(1)

df["timestamp"] = pd.to_datetime(df["timestamp"])
df["date"] = df["timestamp"].dt.date

df["pnl"] = (df["exit_price"].fillna(df["entry"]) - df["entry"]) * df["qty"]
df.loc[df["side"] == "SELL", "pnl"] *= -1

today = now_ist().date()
daily = df[df["date"] == today]

report = {
    "date": str(today),
    "trades": int(len(daily)),
    "win_rate": float((daily["pnl"] > 0).mean()) if len(daily) else 0,
    "profit_factor": float(daily.loc[daily["pnl"] > 0, "pnl"].sum() / abs(daily.loc[daily["pnl"] <= 0, "pnl"].sum())) if (daily["pnl"] <= 0).any() else "inf",
    "total_pnl": float(daily["pnl"].sum())
}

out_json = OUT_DIR / f"daily_report_{today}.json"
out_csv = OUT_DIR / f"daily_report_{today}.csv"
pd.DataFrame([report]).to_json(out_json, orient="records")
daily.to_csv(out_csv, index=False)
print(f"Saved {out_json} and {out_csv}")

# Telegram delivery
try:
    send_telegram_message(f"Daily Report {today}\nTrades: {report['trades']}\nPnL: {report['total_pnl']}\nWin Rate: {report['win_rate']:.2f}\nPF: {report['profit_factor']}")
except Exception:
    pass

# Email delivery
if cfg.EMAIL_REPORTS and cfg.SMTP_HOST and cfg.SMTP_USER and cfg.SMTP_PASSWORD and cfg.SMTP_TO:
    body = f"Daily Report {today}\nTrades: {report['trades']}\nPnL: {report['total_pnl']}\nWin Rate: {report['win_rate']:.2f}\nPF: {report['profit_factor']}"
    msg = MIMEText(body)
    msg["Subject"] = f"Trading Bot Daily Report {today}"
    msg["From"] = cfg.SMTP_USER
    msg["To"] = cfg.SMTP_TO
    try:
        with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT) as server:
            server.starttls()
            server.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
            server.send_message(msg)
        print("Email report sent.")
    except Exception as e:
        print(f"Email send failed: {e}")
