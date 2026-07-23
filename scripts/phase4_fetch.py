import json
import urllib.request
import urllib.parse
import os
import gzip
import time
from pathlib import Path

def load_env():
    env_path = Path("../tradebot/.env")
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v

def main():
    load_env()
    plan_path = Path("runtime/constituent_lead_lag/upstox_v1/manifests/historical_fetch_plan.json")
    with open(plan_path, "r") as f:
        plan = json.load(f)
        
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("Token missing.")
        return
        
    out_dir = Path("runtime/constituent_lead_lag/upstox_v1/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    headers = {
        "Accept": "application/json",
        "Api-Version": "3.0",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for item in plan:
        if item["status"] == "SUCCESS":
            continue
            
        sym = item["symbol"]
        instr_key = item["instrument_key"]
        start_date = item["start_date"]
        end_date = item["end_date"]
        
        # Upstox API expects to_date / from_date. to_date is end_date, from_date is start_date.
        url_key = urllib.parse.quote(instr_key)
        
        # STRICTLY V3
        url = f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/5/{end_date}/{start_date}"
        
        req = urllib.request.Request(url, headers=headers)
        print(f"Fetching {sym} (V3) ...")
        
        success = False
        resp_data = None
        
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req) as response:
                    resp_data = response.read()
                    success = True
                    break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(f"429 Rate limited on {sym}, retrying after {2 ** attempt}s...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    print(f"HTTP Error {e.code} for {sym}: {e}")
                    time.sleep(1)
                    break
            except Exception as e:
                print(f"V3 failed for {sym}: {e}")
                time.sleep(1)
                break
                    
        if success and resp_data:
            # Save raw gzip
            out_file = out_dir / f"{sym}_{start_date}_{end_date}.json.gz"
            with gzip.open(out_file, "wb") as f:
                f.write(resp_data)
                
            # Create checksum sidecar
            import hashlib
            sha256 = hashlib.sha256(resp_data).hexdigest()
            with open(str(out_file) + ".sha256", "w") as f:
                f.write(sha256)
                
            item["status"] = "SUCCESS"
        else:
            item["status"] = "FAILED"
            
        # Dynamically update plan
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)
            
        time.sleep(0.5) # rate limit respect
        
    print("Phase 4 fetch complete (V3 strict).")

if __name__ == "__main__":
    main()
