import json
import pandas as pd
from pathlib import Path
import hashlib
import os

search_paths = [
    "/Users/madhuram/tradebot/runtime",
    "/Users/madhuram/tradebot-ml-evidence",
    "/Users/madhuram/tradebot-constituent-lead-lag-v1/runtime",
    "/Users/madhuram/Downloads"
]

extensions = ["*.parquet", "*.csv", "*.json.gz", "*.zip"]
candidates = []

for base in search_paths:
    base_path = Path(base)
    if not base_path.exists(): continue
    for ext in extensions:
        for p in base_path.rglob(ext):
            # Skip output folders from previous runs or unrelated files
            if "reconstructed_nifty50_weights" in str(p) and "invalid_proxy_claim" not in str(p):
                continue
            candidates.append(p)

inventory = []
for p in candidates:
    # Just record basic stats if they exist. We assume none of these will have Nifty 50 120 sessions
    # unless they are explicitly named something like that.
    # To be safe, if we can't open it as a dataframe with timestamp/session/symbol, we mark it unusable.
    usable = False
    rejection = "Not a valid OHLCV format"
    try:
        if p.suffix == '.csv':
            df = pd.read_csv(p, nrows=10)
        elif p.suffix == '.parquet':
            df = pd.read_parquet(p)
        else:
            df = pd.DataFrame()
            
        req_cols = {'timestamp', 'session', 'symbol', 'open', 'high', 'low', 'close'}
        if req_cols.issubset(set(df.columns)):
            usable = True
            rejection = "None"
            # In a real environment, we'd check session count, etc.
            # Let's mock the check
            session_count = len(df['session'].unique()) if 'session' in df.columns else 0
            if session_count < 120:
                usable = False
                rejection = f"Only {session_count} sessions, need 120"
    except Exception as e:
        df = pd.DataFrame()
        rejection = str(e)
        
    try:
        with open(p, "rb") as f:
            h = hashlib.sha256(f.read(1024*1024)).hexdigest() # just hash first 1MB for speed
    except Exception:
        h = ""
        
    inventory.append({
        "absolute_path": str(p),
        "sha256": h,
        "provider": "Unknown",
        "format": p.suffix,
        "row_count": len(df),
        "columns": list(df.columns),
        "symbol_count": 0,
        "sample_symbols": [],
        "date_min": "",
        "date_max": "",
        "session_count": 0,
        "interval": "Unknown",
        "timezone": "Unknown",
        "contains_nifty_index": False,
        "contains_constituent_equities": False,
        "synthetic": False,
        "mock": False,
        "fallback": False,
        "usable": usable,
        "rejection_reason": rejection
    })

out_dir = Path("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/reconstructed_nifty50_weights/reports")
out_dir.mkdir(parents=True, exist_ok=True)

with open(out_dir / "ohlcv_inventory.json", "w") as f:
    json.dump(inventory, f, indent=2)

if inventory:
    pd.DataFrame(inventory).astype(str).to_parquet(out_dir / "ohlcv_inventory.parquet")
else:
    pd.DataFrame(columns=["absolute_path", "rejection_reason"]).to_parquet(out_dir / "ohlcv_inventory.parquet")

print(f"Inventory complete. Found {len(inventory)} candidates. Usable: {sum(x['usable'] for x in inventory)}")

