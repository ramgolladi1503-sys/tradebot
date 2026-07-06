#!/usr/bin/env python3
import os
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import urllib.parse
import urllib.request
import ssl
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, required=True, help="Start Date in YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, required=True, help="End Date in YYYY-MM-DD")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--interval", type=str, default="1minute")
    parser.add_argument("--max-days-per-chunk", type=int, default=7)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    
    instrument_map = {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank"
    }
    
    current = start
    days_fetched = 0
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    while current <= end:
        if current.weekday() < 5: # Only weekdays
            date_str = current.strftime("%Y%m%d")
            api_date_str = current.strftime("%Y-%m-%d")
            out_dir = Path(f"runtime/upstox_candidate_replay/{date_str}")
            
            # Resume check
            if (out_dir / "manifests" / f"upstox_fetch_manifest_{date_str}.json").exists():
                print(f"Skipping {date_str}, already fetched.")
                current += timedelta(days=1)
                continue
                
            (out_dir / "underlying").mkdir(parents=True, exist_ok=True)
            
            day_success = True
            
            for sym in args.symbols:
                instr_key = instrument_map.get(sym)
                if not instr_key:
                    print(f"Unknown instrument {sym}")
                    day_success = False
                    continue
                
                resp_data = None
                fetch_status = "UPSTOX_FETCH_SUCCEEDED_REAL_CANDLES"
                
                url_key = urllib.parse.quote(instr_key)
                endpoint = f"/v2/historical-candle/{url_key}/{args.interval}/{api_date_str}/{api_date_str}"
                url = f"https://api.upstox.com{endpoint}"
                
                if not token:
                    fetch_status = "UPSTOX_FETCH_FAILED_TOKEN_MISSING"
                else:
                    req = urllib.request.Request(url, headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}"
                    })
                    
                    retries = 3
                    for attempt in range(retries):
                        try:
                            with urllib.request.urlopen(req, context=ctx) as response:
                                if response.status == 429:
                                    print("Rate limit hit, backing off...")
                                    time.sleep(2 ** attempt)
                                    continue
                                resp_data = json.loads(response.read().decode())
                                break
                        except Exception as e:
                            print(f"Network fetch failed: {e}")
                            fetch_status = "UPSTOX_FETCH_FAILED_HTTP_ERROR"
                            break
                
                if resp_data:
                    candles = resp_data.get("data", {}).get("candles", [])
                    if candles:
                        records = []
                        for c in candles:
                            ts = datetime.fromisoformat(c[0].replace('+05:30', ''))
                            records.append({
                                "timestamp": ts,
                                "symbol": sym,
                                "open": float(c[1]),
                                "high": float(c[2]),
                                "low": float(c[3]),
                                "close": float(c[4]),
                                "volume": float(c[5]),
                                "oi": float(c[6]) if len(c) > 6 else 0.0,
                                "source": "upstox",
                                "interval": args.interval,
                                "fetch_timestamp": datetime.now(),
                                "fetch_start_date": api_date_str,
                                "fetch_end_date": api_date_str,
                                "data_origin": "upstox_api",
                                "synthetic": False,
                                "mock": False,
                                "fallback": False,
                                "provider": "upstox",
                                "source_endpoint": endpoint
                            })
                        df = pd.DataFrame(records)
                        df = df.sort_values("timestamp")
                        df.to_parquet(out_dir / "underlying" / f"{sym}_{date_str}.parquet")
                    else:
                        fetch_status = "UPSTOX_FETCH_FAILED_NO_CANDLES"
                        day_success = False
                else:
                    day_success = False
            
            # Manifests
            (out_dir / "manifests").mkdir(parents=True, exist_ok=True)
            manifest = {
                "date": date_str,
                "provider": "upstox",
                "capture_timestamp": datetime.now().isoformat(),
                "data_type": "UPSTOX_OPTION_CANDLE_ONLY",
                "fetch_status": fetch_status if not day_success else "UPSTOX_FETCH_SUCCEEDED_REAL_CANDLES",
                "data_origin": "upstox_api",
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "token_logged": False,
                "certification_eligible": day_success
            }
            with open(out_dir / "manifests" / f"upstox_fetch_manifest_{date_str}.json", "w") as f:
                json.dump(manifest, f, indent=2)
                
            if day_success:
                days_fetched += 1
                
        current += timedelta(days=1)

    print(f"Successfully generated Upstox data chunks for {days_fetched} trading days.")

if __name__ == "__main__":
    main()
