import os
import json
import gzip
import pandas as pd
from pathlib import Path
from collections import defaultdict
import glob

def normalize_upstox():
    raw_dir = Path("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/upstox_v3/raw")
    out_dir = Path("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/upstox_v3/underlying")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    files = list(raw_dir.glob("*.json.gz"))
    if not files:
        print("No raw files found.")
        return
        
    symbol_to_files = defaultdict(list)
    for f in files:
        sym = f.stem.split("_")[0]
        symbol_to_files[sym].append(f)
        
    all_dfs = []
    for sym, f_list in symbol_to_files.items():
        all_candles = []
        for fpath in f_list:
            with gzip.open(fpath, "rt") as f:
                data = json.load(f)
                if data.get("status") == "success" and "data" in data and "candles" in data["data"]:
                    all_candles.extend(data["data"]["candles"])
        
        if not all_candles:
            continue
            
        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        # Upstox V3 historical API returns: ["2026-07-22T15:25:00+05:30", 24000.1, 24002.25, 23990.8, 23991.05, 0, 0]
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        df["session"] = df["timestamp"].dt.strftime("%Y-%m-%d")
        
        df["symbol"] = sym
        df["data_origin"] = "upstox_api"
        df["synthetic"] = False
        df["mock"] = False
        df["fallback"] = False
        df["provider"] = "upstox"
        df["source_endpoint"] = "v3/historical-candle"
        
        all_dfs.append(df)
        print(f"Normalized {sym} ({len(df)} rows)")

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        out_path = out_dir / "aggregated_bars.parquet"
        final_df.to_parquet(out_path, index=False)
        print(f"Saved aggregated bars to {out_path} ({len(final_df)} rows total)")

if __name__ == "__main__":
    normalize_upstox()
