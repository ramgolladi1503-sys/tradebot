import json
import gzip
from pathlib import Path
import pandas as pd
from datetime import datetime, timezone

def main():
    reports_dir = Path("runtime/constituent_lead_lag/upstox_v1/reports")
    raw_dir = Path("runtime/constituent_lead_lag/upstox_v1/raw")
    out_dir = Path("runtime/constituent_lead_lag/normalized")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(reports_dir / "data_quality.json", "r") as f:
        validation_results = json.load(f)
        
    for res in validation_results:
        if not res["passed"]:
            continue
            
        filename = res["file"]
        sym = res["symbol"]
        
        with gzip.open(raw_dir / filename, "rt") as f:
            data = json.load(f)
            
        candles = data.get("data", {}).get("candles", [])
        
        records = []
        for c in candles:
            # c[0]: timestamp with offset like 2026-07-23T15:25:00+05:30
            ts_str = c[0]
            
            # Reject incomplete session
            if ts_str.startswith("2026-07-23"):
                continue
                
            # Convert to UTC
            dt = datetime.fromisoformat(ts_str).astimezone(timezone.utc)
            
            records.append({
                "timestamp": dt,
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "oi": float(c[6]) if len(c) > 6 else 0.0,
                "symbol": sym,
                "interval": "5m",
                "provider": "upstox"
            })
            
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_convert("UTC")
        df["open"] = df["open"].astype("float64")
        df["high"] = df["high"].astype("float64")
        df["low"] = df["low"].astype("float64")
        df["close"] = df["close"].astype("float64")
        df["volume"] = df["volume"].astype("float64")
        df["oi"] = df["oi"].astype("float64")
        df["symbol"] = df["symbol"].astype("str")
        df["interval"] = df["interval"].astype("str")
        df["provider"] = df["provider"].astype("str")
        
        # Ensure it is sorted chronologically
        df = df.sort_values("timestamp")
        
        out_file = out_dir / f"{sym}_5m.parquet"
        df.to_parquet(out_file)
        
    print(f"Normalization complete. Output written to {out_dir}")

if __name__ == "__main__":
    main()
