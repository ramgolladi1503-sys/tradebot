#!/usr/bin/env python3
import os
import json
import argparse
import urllib.parse
import urllib.request
import ssl
from datetime import datetime
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, required=True)
    parser.add_argument("--end-date", type=str, required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--interval", type=str, default="1minute")
    args = parser.parse_args()
    
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    sym = args.symbols[0]
    
    # Check for trusted instrument master
    master_path = Path("configs/upstox_instrument_master.json")
    instr_key = None
    if master_path.exists():
        with open(master_path, "r") as f:
            master = json.load(f)
            for item in master:
                if item.get("tradingsymbol") == sym:
                    instr_key = item.get("instrument_key")
                    break
    
    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "endpoint_results": []
    }
    
    if not instr_key:
        report["endpoint_results"].append({
            "version": "v2",
            "endpoint_path": None,
            "http_status": None,
            "classification": "UPSTOX_INSTRUMENT_KEY_RESOLUTION_MISSING",
            "candles_count": 0,
            "token_logged": False
        })
        report["endpoint_results"].append({
            "version": "v3",
            "endpoint_path": None,
            "http_status": None,
            "classification": "UPSTOX_INSTRUMENT_KEY_RESOLUTION_MISSING",
            "candles_count": 0,
            "token_logged": False
        })
    elif not token:
        report["endpoint_results"].append({
            "version": "v2",
            "endpoint_path": None,
            "http_status": None,
            "classification": "UPSTOX_ACCESS_BLOCKED_TOKEN_MISSING",
            "candles_count": 0,
            "token_logged": False
        })
        report["endpoint_results"].append({
            "version": "v3",
            "endpoint_path": None,
            "http_status": None,
            "classification": "UPSTOX_ACCESS_BLOCKED_TOKEN_MISSING",
            "candles_count": 0,
            "token_logged": False
        })
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url_key = urllib.parse.quote(instr_key)
        api_date_str = args.start_date
        
        # Test V2
        v2_path = f"/v2/historical-candle/{url_key}/1minute/{api_date_str}/{api_date_str}"
        v2_url = f"https://api.upstox.com{v2_path}"
        v2_result = {
            "version": "v2",
            "endpoint_path": v2_path,
            "http_status": None,
            "classification": "UPSTOX_ACCESS_OK",
            "candles_count": 0,
            "token_logged": False
        }
        try:
            req = urllib.request.Request(v2_url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, context=ctx) as response:
                v2_result["http_status"] = response.status
                resp_data = json.loads(response.read().decode())
                candles = resp_data.get("data", {}).get("candles", [])
                v2_result["candles_count"] = len(candles)
                if not candles:
                    v2_result["classification"] = "UPSTOX_ACCESS_BLOCKED_NO_CANDLES"
        except urllib.error.HTTPError as e:
            v2_result["http_status"] = e.code
            if e.code == 401:
                v2_result["classification"] = "UPSTOX_ACCESS_BLOCKED_401_UNAUTHORIZED"
            elif e.code == 403:
                v2_result["classification"] = "UPSTOX_ACCESS_BLOCKED_403_FORBIDDEN"
            else:
                v2_result["classification"] = "UPSTOX_ACCESS_BLOCKED_HTTP_ERROR"
        except json.JSONDecodeError:
            v2_result["classification"] = "UPSTOX_ACCESS_BLOCKED_MALFORMED_RESPONSE"
        except Exception:
            v2_result["classification"] = "UPSTOX_ACCESS_BLOCKED_HTTP_ERROR"
            
        report["endpoint_results"].append(v2_result)
        
        # Test V3
        v3_path = f"/v3/historical-candle/{url_key}/minutes/1/{api_date_str}/{api_date_str}"
        v3_url = f"https://api.upstox.com{v3_path}"
        v3_result = {
            "version": "v3",
            "endpoint_path": v3_path,
            "http_status": None,
            "classification": "UPSTOX_ACCESS_OK",
            "candles_count": 0,
            "token_logged": False
        }
        try:
            req = urllib.request.Request(v3_url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, context=ctx) as response:
                v3_result["http_status"] = response.status
                resp_data = json.loads(response.read().decode())
                candles = resp_data.get("data", {}).get("candles", [])
                v3_result["candles_count"] = len(candles)
                if not candles:
                    v3_result["classification"] = "UPSTOX_ACCESS_BLOCKED_NO_CANDLES"
        except urllib.error.HTTPError as e:
            v3_result["http_status"] = e.code
            if e.code == 401:
                v3_result["classification"] = "UPSTOX_ACCESS_BLOCKED_401_UNAUTHORIZED"
            elif e.code == 403:
                v3_result["classification"] = "UPSTOX_ACCESS_BLOCKED_403_FORBIDDEN"
            else:
                v3_result["classification"] = "UPSTOX_ACCESS_BLOCKED_HTTP_ERROR"
        except json.JSONDecodeError:
            v3_result["classification"] = "UPSTOX_ACCESS_BLOCKED_MALFORMED_RESPONSE"
        except Exception:
            v3_result["classification"] = "UPSTOX_ACCESS_BLOCKED_HTTP_ERROR"
            
        report["endpoint_results"].append(v3_result)
    
    with open(out_dir / "upstox_access_diagnostics.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print("Diagnostic complete.")

if __name__ == "__main__":
    main()
