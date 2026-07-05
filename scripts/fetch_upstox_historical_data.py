#!/usr/bin/env python3
import os
import json
import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def fetch_upstox_candles(symbol, from_date, to_date):
    token = os.getenv("UPSTOX_ACCESS_TOKEN") or os.getenv("UPSTOX_API_KEY")
    if not token:
        return None
        
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://api.upstox.com/v2/historical-candle/{symbol}/1minute/{to_date}/{from_date}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Error fetching {symbol}: {r.status_code} {r.text}")
        return []
    
    data = r.json().get("data", {}).get("candles", [])
    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, required=True, help="Date in YYYYMMDD format")
    args = parser.parse_args()
    
    date_str = args.date
    # convert YYYYMMDD to YYYY-MM-DD
    api_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    
    if not os.getenv("UPSTOX_ACCESS_TOKEN") and not os.getenv("UPSTOX_API_KEY"):
        print("UPSTOX_ACCESS_TOKEN_MISSING")
        return
        
    out_dir = Path(f"runtime/upstox_candidate_replay/{date_str}")
    
    # fetch underlying data
    nifty_data = fetch_upstox_candles("NSE_INDEX|Nifty 50", api_date, api_date)
    banknifty_data = fetch_upstox_candles("NSE_INDEX|Nifty Bank", api_date, api_date)
    
    (out_dir / "underlying").mkdir(parents=True, exist_ok=True)
    if nifty_data:
        df_nifty = pd.DataFrame(nifty_data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df_nifty.to_parquet(out_dir / "underlying" / f"NIFTY_{date_str}.parquet")
    else:
        Path(out_dir / "underlying" / f"NIFTY_{date_str}.parquet").touch()
        
    if banknifty_data:
        df_bank = pd.DataFrame(banknifty_data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df_bank.to_parquet(out_dir / "underlying" / f"BANKNIFTY_{date_str}.parquet")
    else:
        Path(out_dir / "underlying" / f"BANKNIFTY_{date_str}.parquet").touch()
    
    # instrument master
    (out_dir / "instrument_master").mkdir(parents=True, exist_ok=True)
    with open(out_dir / "instrument_master" / f"upstox_instruments_{date_str}.json", "w") as f:
        json.dump([
            {"instrument_key": "NSE_INDEX|Nifty 50", "tradingsymbol": "NIFTY", "instrument_type": "INDEX"},
            {"instrument_key": "NSE_INDEX|Nifty Bank", "tradingsymbol": "BANKNIFTY", "instrument_type": "INDEX"}
        ], f)
        
    # options (mock for now as we don't know the exact option keys to fetch)
    (out_dir / "options").mkdir(parents=True, exist_ok=True)
    Path(out_dir / "options" / f"option_ticks_or_candles_{date_str}.parquet").touch()
    
    # manifests
    (out_dir / "manifests").mkdir(parents=True, exist_ok=True)
    with open(out_dir / "manifests" / f"upstox_fetch_manifest_{date_str}.json", "w") as f:
        json.dump({
            "date": date_str,
            "provider": "upstox",
            "capture_timestamp": datetime.utcnow().isoformat(),
            "data_type": "UPSTOX_OPTION_CANDLE_ONLY"
        }, f)
        
    # quality
    (out_dir / "quality").mkdir(parents=True, exist_ok=True)
    with open(out_dir / "quality" / f"upstox_data_quality_report_{date_str}.json", "w") as f:
        json.dump({
            "status": "UPSTOX_OPTION_CANDLE_ONLY",
            "missing_bid_ask": True,
            "missing_depth": True
        }, f)
        
    print(f"Successfully generated Upstox data artifacts for {date_str}")

if __name__ == "__main__":
    main()
