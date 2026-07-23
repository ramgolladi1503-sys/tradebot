import argparse
import json
import urllib.request
import urllib.error
import urllib.parse
import os
import gzip
import time
import hashlib
from pathlib import Path
import calendar
from datetime import datetime

def load_upstox_json_master():
    # Use official JSON instead of CSV
    url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req) as response:
        with gzip.GzipFile(fileobj=response) as uncompressed:
            data = json.loads(uncompressed.read())
            
    instruments = {}
    for item in data:
        # Check segment and instrument_type
        segment = item.get("segment", "")
        itype = item.get("instrument_type", "")
        tsym = item.get("trading_symbol", "")
        
        if (segment == "NSE_EQ" and itype == "EQ") or segment == "NSE_INDEX":
            if tsym in instruments:
                # Reject ambiguity by removing it entirely if duplicate
                instruments[tsym] = None
            else:
                instruments[tsym] = item
                
    # Remove ambigous entries
    return {k: v for k, v in instruments.items() if v is not None}

def fetch_chunk(instrument_key, symbol, from_date, to_date, token, out_dir):
    url_key = urllib.parse.quote(instrument_key)
    # Correct format: /v3/historical-candle/{instrument_key}/minutes/5/{to_date}/{from_date}
    url = f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/5/{to_date}/{from_date}"
    
    headers = {
        "Accept": "application/json",
        "Api-Version": "3.0",
        "Authorization": f"Bearer {token}"
    }
    
    req = urllib.request.Request(url, headers=headers)
    success = False
    resp_data = None
    http_status = None
    
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                http_status = response.status
                raw = response.read()
                resp_json = json.loads(raw)
                if resp_json.get("status") == "success" and isinstance(resp_json.get("data", {}).get("candles"), list):
                    resp_data = raw
                    success = True
                    break
        except urllib.error.HTTPError as e:
            http_status = e.code
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            elif e.code in (500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            elif e.code in (400, 401, 403):
                # Fail closed
                break
        except Exception:
            time.sleep(2 ** attempt)
            
    if success and resp_data:
        out_file = out_dir / f"{symbol}_{from_date}_{to_date}.json.gz"
        with gzip.open(out_file, "wb") as f:
            f.write(resp_data)
        
        # Calculate SHA256 of the stored file (the gzip file itself)
        sha256 = hashlib.sha256()
        with open(out_file, "rb") as f:
            for c in iter(lambda: f.read(1024*1024), b""):
                sha256.update(c)
        
        file_hash = sha256.hexdigest()
        with open(str(out_file) + ".sha256", "w") as f:
            f.write(file_hash)
            
        return {
            "status": "SUCCESS",
            "http_status": http_status,
            "candle_count": len(json.loads(resp_data)["data"]["candles"]),
            "file_sha256": file_hash
        }
    else:
        return {
            "status": "FAILED",
            "http_status": http_status,
            "candle_count": 0,
            "file_sha256": None
        }

def get_monthly_chunks(start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    chunks = []
    
    curr = start
    while curr <= end:
        last_day = calendar.monthrange(curr.year, curr.month)[1]
        month_end = datetime(curr.year, curr.month, last_day)
        
        chunk_start = curr.strftime("%Y-%m-%d")
        chunk_end = min(month_end, end).strftime("%Y-%m-%d")
        
        chunks.append((chunk_start, chunk_end))
        
        if month_end >= end:
            break
        curr = datetime(curr.year, curr.month + 1, 1)
        
    return chunks

def load_env(env_file):
    if not env_file: return
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    
    if args.env_file:
        load_env(args.env_file)
        
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Missing UPSTOX_ACCESS_TOKEN")
        sys.exit(1)
        
    out_dir = Path(args.output_root) / "upstox_v3" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("Loading official JSON master...")
    master = load_upstox_json_master()
    
    # Read weights to know which symbols to fetch
    try:
        import pandas as pd
        weights_df = pd.read_csv(args.weights)
        symbols = weights_df["constituent_symbol"].unique().tolist()
        symbols.append("NIFTY 50")
        symbols.append("NIFTY BANK")
    except Exception:
        # If weights file is missing/invalid, fail closed
        print("Valid weights file not found, failing closed.")
        sys.exit(1)
        
    manifest = []
    chunks = get_monthly_chunks(args.start_date, args.end_date)
    
    for sym in symbols:
        # Try to resolve symbol to instrument_key
        # Note: mapping logic requires exact matches based on trading_symbol
        instr = master.get(sym)
        if not instr:
            print(f"Skipping {sym}, not unambiguously found in master.")
            continue
            
        instr_key = instr["instrument_key"]
        
        for c_start, c_end in chunks:
            res = fetch_chunk(instr_key, sym, c_start, c_end, token, out_dir)
            manifest.append({
                "instrument_key": instr_key,
                "symbol": sym,
                "from_date": c_start,
                "to_date": c_end,
                "endpoint_version": "v3",
                "http_status": res["http_status"],
                "candle_count": res["candle_count"],
                "stored_file_sha256": res["file_sha256"],
                "classification": "SUCCESS" if res["status"] == "SUCCESS" else "FAILED",
                "token_logged": False
            })
            time.sleep(0.5)
            
    with open(Path(args.output_root) / "upstox_v3" / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

if __name__ == "__main__":
    main()
