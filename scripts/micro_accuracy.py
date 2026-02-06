from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import json
import pandas as pd
from config import config as cfg
from core.telegram_alerts import send_telegram_message

path = "data/trade_log.json"
rows = []
with open(path, "r") as f:
    for line in f:
        if not line.strip():
            continue
        rows.append(json.loads(line))

df = pd.DataFrame(rows)
df = df.dropna(subset=["micro_pred", "actual"])
if df.empty:
    print("No micro model outcomes to evaluate.")
    raise SystemExit(0)

df["micro_label"] = (df["micro_pred"] >= 0.5).astype(int)
acc = (df["micro_label"] == df["actual"]).mean()
print(f"Microstructure model accuracy: {acc:.3f}")
if acc < getattr(cfg, "MICRO_ALERT_THRESHOLD", 0.55):
    send_telegram_message(f"Micro accuracy below threshold: {acc:.3f}")
