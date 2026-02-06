from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import pandas as pd

in_path = "data/trade_log.json"
out_path = "logs/trade_log.xlsx"

rows = []
with open(in_path, "r") as f:
    for line in f:
        if not line.strip():
            continue
        rows.append(json.loads(line))

df = pd.DataFrame(rows)
df.to_excel(out_path, index=False)
print(f"Exported {len(df)} trades to {out_path}")
