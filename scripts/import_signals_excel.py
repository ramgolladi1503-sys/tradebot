from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import pandas as pd
from core.tv_queue import enqueue_alert

path = "logs/signals.xlsx"
df = pd.read_excel(path)
for _, row in df.iterrows():
    enqueue_alert(row.to_dict())
print(f"Imported {len(df)} signals from {path}")
