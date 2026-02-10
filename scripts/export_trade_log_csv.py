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
required_cols = [
    "trade_id",
    "timestamp",
    "symbol",
    "underlying",
    "instrument",
    "instrument_type",
    "expiry",
    "strike",
    "right",
    "instrument_id",
    "side",
    "entry",
    "stop_loss",
    "target",
    "qty",
    "qty_lots",
    "qty_units",
    "validity_sec",
    "tradable",
    "tradable_reasons_blocking",
    "source_flags_json",
    "confidence",
    "strategy",
    "regime",
]
for col in required_cols:
    if col not in df.columns:
        df[col] = None
df = df[required_cols + [c for c in df.columns if c not in required_cols]]
df.to_csv(output_path, index=False)
print(f"Exported {len(df)} rows to {output_path}")
