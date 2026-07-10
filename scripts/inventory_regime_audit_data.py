import os
import sys
import json
import glob
import pandas as pd
import sqlite3
from pathlib import Path

def inspect_file(filepath):
    info = {
        "path": filepath,
        "type": Path(filepath).suffix,
        "size": os.path.getsize(filepath),
        "row_count": 0,
        "columns": [],
        "min_timestamp": None,
        "max_timestamp": None,
        "symbols": [],
        "has_ohlc": False,
        "has_tick_ltp": False,
        "has_depth": False,
        "classification": "UNKNOWN",
        "dates": set()
    }
    
    try:
        if info["type"] == ".parquet":
            df = pd.read_parquet(filepath)
            info["columns"] = list(df.columns)
            info["row_count"] = len(df)
            
            # Timestamp processing
            ts_col = None
            if "ts" in df.columns: ts_col = "ts"
            elif "timestamp" in df.columns: ts_col = "timestamp"
            elif "date" in df.columns: ts_col = "date"
            
            if ts_col:
                try:
                    ts_series = pd.to_datetime(df[ts_col])
                    info["min_timestamp"] = str(ts_series.min())
                    info["max_timestamp"] = str(ts_series.max())
                    info["dates"] = set(ts_series.dt.strftime('%Y-%m-%d').unique())
                except:
                    pass
            
            # Symbols
            if "symbol" in df.columns:
                info["symbols"] = list(df["symbol"].dropna().unique())
            
            # Features
            cols = set(df.columns)
            info["has_ohlc"] = {"open", "high", "low", "close"}.issubset(cols)
            info["has_tick_ltp"] = "ltp" in cols or "last_price" in cols or "tick" in cols or "bid" in cols or "close" in cols
            info["has_depth"] = "bid" in cols and "ask" in cols
            
            if info["has_ohlc"]:
                info["classification"] = "USABLE_OHLC"
            elif info["has_depth"]:
                info["classification"] = "USABLE_QUOTE_DEPTH"
            elif info["has_tick_ltp"]:
                info["classification"] = "USABLE_TICK_LTP"
            else:
                info["classification"] = "INSUFFICIENT_SCHEMA"
                
            # Quick check if it's options only or underlying only
            if info["symbols"]:
                is_opt = any("PE" in s or "CE" in s for s in info["symbols"])
                if is_opt and not any(s in ["NIFTY", "BANKNIFTY", "SENSEX"] for s in info["symbols"]):
                    info["classification"] = "OPTION_ONLY"
                elif not is_opt:
                    info["classification"] = "UNDERLYING_ONLY" if info["classification"] not in ["USABLE_OHLC", "USABLE_QUOTE_DEPTH", "USABLE_TICK_LTP"] else info["classification"]

        elif info["type"] == ".csv":
            df = pd.read_csv(filepath, nrows=1000)
            info["columns"] = list(df.columns)
            cols = set(df.columns)
            info["has_ohlc"] = {"open", "high", "low", "close"}.issubset(cols)
            info["has_tick_ltp"] = "ltp" in cols or "last_price" in cols or "tick" in cols or "bid" in cols or "close" in cols
            info["has_depth"] = "bid" in cols and "ask" in cols
            
            if info["has_ohlc"]:
                info["classification"] = "USABLE_OHLC"
            else:
                info["classification"] = "INSUFFICIENT_SCHEMA"
                
    except Exception as e:
        info["classification"] = "UNKNOWN"
        info["error"] = str(e)
        
    return info

def main():
    patterns = [
        "**/*truth*.parquet", "**/*tick*.parquet", "**/*ohlc*.parquet", "**/*candle*.parquet",
        "**/*market*.parquet", "**/*quote*.parquet", "**/*depth*.parquet",
        "**/*nifty*.parquet", "**/*banknifty*.parquet", "**/*sensex*.parquet",
        "**/*upstox*.parquet", "**/*kite*.parquet", "**/*zerodha*.parquet",
        "**/*replay*.parquet", "**/*historical*.parquet"
    ]
    
    files = []
    import subprocess
    cmd = 'find . runtime data .runtime logs -type f 2>/dev/null | grep -Ei "truth|tick|ohlc|candle|market|quote|depth|nifty|banknifty|sensex|upstox|kite|zerodha|replay|historical" | grep -E "\.parquet$|\.csv$|\.jsonl$|\.json$|\.db$|\.sqlite$"'
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        files = [f.strip() for f in output.split('\n') if f.strip()]
    except Exception:
        pass
    
    inventory = []
    all_dates = set()
    
    # Process files
    for f in files:
        # Ignore huge files just in case, only process parquets for regime data as requested
        if f.endswith('.parquet') or f.endswith('.csv'):
            res = inspect_file(f)
            inventory.append(res)
            all_dates.update(res.get("dates", set()))
        else:
            inventory.append({"path": f, "classification": "UNKNOWN"})
            
    dates_list = sorted(list(all_dates))
    
    target_dates = {"2026-07-06", "2026-06-10", "2026-06-29"}
    found_targets = {d: (d in dates_list) for d in target_dates}
    
    # Find best date
    best_date = None
    for d in sorted(target_dates, reverse=True):
        if d in dates_list:
            # Check if there is OHLC or Tick data for this date
            has_good_data = any(d in item.get("dates", set()) and item["classification"] in ["USABLE_OHLC", "USABLE_TICK_LTP", "USABLE_QUOTE_DEPTH"] for item in inventory)
            if has_good_data:
                best_date = d
                break
                
    if not best_date and dates_list:
        # Fallback to any date with good data
        for d in reversed(dates_list):
            has_good_data = any(d in item.get("dates", set()) and item["classification"] in ["USABLE_OHLC", "USABLE_TICK_LTP", "USABLE_QUOTE_DEPTH"] for item in inventory)
            if has_good_data:
                best_date = d
                break
    
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = out_dir / "regime_audit_data_inventory.json"
    md_path = out_dir / "regime_audit_data_inventory.md"
    
    report = {
        "inventory": inventory,
        "available_dates": dates_list,
        "target_dates_found": found_targets,
        "best_date": best_date
    }
    
    with open(json_path, "w") as f:
        json.dump(report, f, indent=4, default=list)
        
    md = "# Regime Audit Data Inventory\n\n"
    md += f"**Available Dates:** {dates_list}\n"
    md += f"**Best Date for Audit:** {best_date}\n\n"
    md += "### Target Dates Check\n"
    for d, found in found_targets.items():
        md += f"- {d}: {'FOUND' if found else 'MISSING'}\n"
        
    md += "\n### Files Inventory\n"
    for item in inventory:
        md += f"- **{item['path']}** -> `{item['classification']}`\n"
        
    with open(md_path, "w") as f:
        f.write(md)
        
    print("=== INVENTORY COMPLETE ===")
    print(f"Available Dates: {dates_list}")
    print(f"Best Date: {best_date}")
    print("Target Dates Check:")
    for k,v in found_targets.items():
        print(f"  {k}: {v}")
    
    # Also print some stats
    print("\nData classifications found:")
    classes = {}
    for item in inventory:
        c = item['classification']
        classes[c] = classes.get(c, 0) + 1
    for k,v in classes.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
