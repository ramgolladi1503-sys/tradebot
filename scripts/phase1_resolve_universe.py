import json
import urllib.request
import hashlib
from datetime import datetime, timezone
import csv
from pathlib import Path

def get_sha256(data: bytes):
    return hashlib.sha256(data).hexdigest()

def fetch_nse_csv(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/csv,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def main():
    indices = [
        {"symbol": "NIFTY", "url": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"},
        {"symbol": "BANKNIFTY", "url": "https://nsearchives.nseindia.com/content/indices/ind_niftybanklist.csv"}
    ]
    
    out_dir = Path("runtime/constituent_lead_lag/upstox_v1/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    records = []
    
    for idx in indices:
        print(f"Fetching {idx['symbol']} constituents...")
        raw_data = fetch_nse_csv(idx["url"])
        if not raw_data:
            continue
            
        sha = get_sha256(raw_data)
        lines = raw_data.decode('utf-8-sig', errors='ignore').splitlines()
        reader = csv.DictReader(lines)
        constituents = []
        for row in reader:
            if "Symbol" in row:
                constituents.append(row["Symbol"].strip())
                
        records.append({
            "source_url": idx["url"],
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            "sha256": sha,
            "index": idx["symbol"],
            "constituents": constituents,
            "effective_as_of": "CURRENT_BASKET_PROSPECTIVE_ONLY",
            "weight_available": False,
            "classification": [
                "CURRENT_CONSTITUENT_SNAPSHOT_ONLY",
                "NOT_VALID_FOR_HISTORICAL_WEIGHTED_BACKTEST"
            ]
        })
        
    with open(out_dir / "source_authority.json", "w") as f:
        json.dump(records, f, indent=2)
        
    print("Phase 1 complete. Saved source_authority.json")

if __name__ == "__main__":
    main()
