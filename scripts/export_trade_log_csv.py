from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import pandas as pd

input_path = "data/trade_log.json"
output_path = "data/trade_log.csv"

rows = []
with open(input_path, "r") as f:
    for line in f:
        if not line.strip():
            continue
        rows.append(json.loads(line))

df = pd.DataFrame(rows)
df.to_csv(output_path, index=False)
print(f"Exported {len(df)} rows to {output_path}")
