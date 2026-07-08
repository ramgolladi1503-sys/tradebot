import os
import json
import sqlite3
import pandas as pd
from pathlib import Path

def inspect_parquet(path):
    try:
        df = pd.read_parquet(path)
        cols = list(df.columns)
        count = len(df)
        ts_range = []
        if 'timestamp' in df.columns:
            ts_range = [str(df['timestamp'].min()), str(df['timestamp'].max())]
        elif 'date' in df.columns:
             ts_range = [str(df['date'].min()), str(df['date'].max())]
             
        syms = []
        if 'instrument_key' in df.columns:
            syms = df['instrument_key'].unique().tolist()
        elif 'symbol' in df.columns:
            syms = df['symbol'].unique().tolist()
            
        return {
            "columns": cols,
            "row_count": count,
            "timestamp_range": ts_range,
            "symbols": syms[:10]
        }
    except Exception as e:
        return {"error": str(e)}

def inspect_csv(path):
    try:
        df = pd.read_csv(path, nrows=100)
        cols = list(df.columns)
        with open(path, "rb") as f:
            count = sum(1 for _ in f) - 1
            
        return {
            "columns": cols,
            "row_count_estimate": count,
            "timestamp_range": [],
            "symbols": []
        }
    except Exception as e:
        return {"error": str(e)}

def inspect_jsonl(path):
    try:
        keys = set()
        count = 0
        with open(path, 'r') as f:
            for i, line in enumerate(f):
                count += 1
                if i < 3:
                    try:
                        d = json.loads(line)
                        keys.update(d.keys())
                    except:
                        pass
        return {
            "keys": list(keys),
            "row_count": count
        }
    except Exception as e:
        return {"error": str(e)}

def inspect_sqlite(path):
    try:
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in c.fetchall()]
        schemas = {}
        for t in tables:
            c.execute(f"PRAGMA table_info({t});")
            schemas[t] = [r[1] for r in c.fetchall()]
        return {
            "tables": tables,
            "schemas": schemas
        }
    except Exception as e:
        return {"error": str(e)}

def classify_data(info, file_type):
    cols = []
    if file_type == "parquet":
        cols = info.get("columns", [])
    elif file_type == "csv":
        cols = info.get("columns", [])
    elif file_type == "jsonl":
        cols = info.get("keys", [])
    elif file_type in ("db", "sqlite"):
        cols = []
        for t, s in info.get("schemas", {}).items():
            cols.extend(s)
            
    cols_lower = [c.lower() for c in cols]
    
    if 'bid' in cols_lower and 'ask' in cols_lower:
        if 'strike' in cols_lower or 'expiry' in cols_lower or 'option_type' in cols_lower or 'opt' in str(info):
             return "OPTION_BID_ASK"
        if any('opt' in str(sym).lower() for sym in info.get("symbols", [])):
             return "OPTION_BID_ASK"
        return "UNKNOWN_BID_ASK"
        
    if 'strike' in cols_lower or 'expiry' in cols_lower or 'option_type' in cols_lower:
        if 'ltp' in cols_lower or 'close' in cols_lower:
            return "OPTION_LTP"
    
    if any('opt' in str(sym).lower() for sym in info.get("symbols", [])):
        return "OPTION_LTP"
        
    if 'ltp' in cols_lower or 'close' in cols_lower:
        return "UNDERLYING_ONLY"
        
    return "UNKNOWN"

def main():
    import subprocess
    cmd = 'find data runtime .runtime logs -type f 2>/dev/null | grep -Ei "tick|option|opt|quote|depth|ltp|parquet|jsonl|sqlite|db"'
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        files = [f for f in output.split("\n") if f.strip()]
    except Exception as e:
        print(f"Find failed: {e}")
        return

    inventory = []
    for f in files:
        path = Path(f)
        if not path.exists(): continue
        
        ext = path.suffix.lower()
        size = path.stat().st_size
        
        info = {}
        if ext == '.parquet':
            info = inspect_parquet(f)
            ftype = "parquet"
        elif ext == '.csv':
            info = inspect_csv(f)
            ftype = "csv"
        elif ext == '.jsonl':
            info = inspect_jsonl(f)
            ftype = "jsonl"
        elif ext in ('.db', '.sqlite'):
            info = inspect_sqlite(f)
            ftype = "sqlite"
        else:
            ftype = "unknown"
            
        classification = classify_data(info, ftype)
        usable = classification in ("OPTION_BID_ASK", "OPTION_LTP", "OPTION_DEPTH")
        
        inventory.append({
            "path": f,
            "type": ftype,
            "size_bytes": size,
            "info": info,
            "classification": classification,
            "usable_for_blocker_replay": usable
        })
        
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "market_data_inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)
        
    md_lines = ["# Market Data Inventory Report", ""]
    md_lines.append("| Path | Type | Size | Classification | Usable | Details |")
    md_lines.append("|---|---|---|---|---|---|")
    
    for item in inventory:
        size_mb = f"{item['size_bytes'] / 1024 / 1024:.2f} MB"
        details = str(item['info'])[:100] + "..." if len(str(item['info'])) > 100 else str(item['info'])
        md_lines.append(f"| {item['path']} | {item['type']} | {size_mb} | {item['classification']} | {item['usable_for_blocker_replay']} | {details} |")
        
    with open(out_dir / "market_data_inventory.md", "w") as f:
        f.write("\n".join(md_lines))
        
    print(f"Inventory complete. Found {len(inventory)} files.")
    
if __name__ == "__main__":
    main()
