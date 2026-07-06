import argparse
import json
import os
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--interval", required=True)
    args = parser.parse_args()
    
    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    
    res_path = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    resolved_keys = {}
    if res_path.exists():
        with open(res_path, "r") as f:
            res_data = json.load(f)
            if res_data.get("classification") == "UPSTOX_INSTRUMENT_KEYS_RESOLVED":
                resolved_keys = res_data.get("resolved", {})
                
    if not token:
        result = {
            "classification": "UPSTOX_HISTORY_BLOCKED_TOKEN_MISSING",
            "start_date": args.start_date,
            "end_date": args.end_date,
            "symbols": args.symbols,
            "interval": args.interval,
            "max_available_range": None,
            "failed_chunks": [],
            "api_status": "TOKEN_MISSING"
        }
    elif not resolved_keys or not all(sym in args.symbols for sym in resolved_keys):
        result = {
            "classification": "UPSTOX_HISTORY_BLOCKED_INSTRUMENT_KEY_FAILURE",
            "start_date": args.start_date,
            "end_date": args.end_date,
            "symbols": args.symbols,
            "interval": args.interval,
            "max_available_range": None,
            "failed_chunks": [],
            "api_status": "INSTRUMENT_KEYS_MISSING"
        }
    else:
        # Loop over all requested symbols and probe one chunk for each
        failed = False
        api_status = "OK"
        
        for sym in args.symbols:
            inst_key = resolved_keys[sym]["instrument_key"]
            url_key = urllib.parse.quote(inst_key)
            
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            req = urllib.request.Request(
                f"https://api.upstox.com/v2/historical-candle/{url_key}/1minute/{args.end_date}/{args.start_date}",
                headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    pass
            except urllib.error.HTTPError as e:
                failed = True
                api_status = f"{e.code}_{e.reason}".upper()
                break
                
        if failed:
            result = {
                "classification": "UPSTOX_HISTORY_BLOCKED_API_ERROR",
                "start_date": args.start_date,
                "end_date": args.end_date,
                "symbols": args.symbols,
                "interval": args.interval,
                "max_available_range": None,
                "failed_chunks": [f"{args.start_date}_to_{args.end_date}"],
                "api_status": api_status
            }
        else:
            result = {
                "classification": "UPSTOX_HISTORY_AVAILABLE",
                "start_date": args.start_date,
                "end_date": args.end_date,
                "symbols": args.symbols,
                "interval": args.interval,
                "max_available_range": [args.start_date, args.end_date],
                "failed_chunks": [],
                "api_status": "OK"
            }
            
    with open(out_dir / "upstox_availability_probe.json", "w") as f:
        json.dump(result, f, indent=2)
        
    with open(out_dir / "upstox_availability_probe.md", "w") as f:
        f.write("# Upstox Availability Probe\n\n")
        f.write(f"**Classification**: {result['classification']}\n")
        f.write(f"**API Status**: {result['api_status']}\n")

if __name__ == "__main__":
    main()
