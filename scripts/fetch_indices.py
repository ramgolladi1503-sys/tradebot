import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import gzip
import hashlib
from pathlib import Path
from datetime import datetime
import calendar

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
        if curr.month == 12:
            curr = datetime(curr.year + 1, 1, 1)
        else:
            curr = datetime(curr.year, curr.month + 1, 1)
            
    return chunks

def fetch_chunk(instrument_key, symbol, from_date, to_date, token, out_dir):
    url_key = urllib.parse.quote(instrument_key)
    url = f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/5/{to_date}/{from_date}"
    
    headers = {
        "Accept": "application/json",
        "Api-Version": "3.0",
        "Authorization": f"Bearer {token}",
        "User-Agent": "curl/8.4.0"
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

def main():
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Missing token")
        return
        
    out_dir = Path("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/upstox_v3/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    indices = [
        {"symbol": "NIFTY", "instrument_key": "NSE_INDEX|Nifty 50"},
        {"symbol": "BANKNIFTY", "instrument_key": "NSE_INDEX|Nifty Bank"}
    ]
    
    chunks = get_monthly_chunks("2025-12-01", "2026-07-23")
    manifest = []
    
    for item in indices:
        for c_start, c_end in chunks:
            print(f"Fetching {item['symbol']} {c_start} to {c_end}")
            res = fetch_chunk(item["instrument_key"], item["symbol"], c_start, c_end, token, out_dir)
            manifest.append({
                "instrument_key": item["instrument_key"],
                "symbol": item["symbol"],
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
            
    with open("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/upstox_v3/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    print("Done fetching.")

if __name__ == "__main__":
    main()
