#!/usr/bin/env python3
import os
import json
import argparse
import urllib.parse
import urllib.request
import ssl
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
    
    # Read instrument resolution
    res_path = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    instr_key = None
    res_blocker = "UPSTOX_INSTRUMENT_KEY_RESOLUTION_MISSING"
    
    if res_path.exists():
        with open(res_path, "r") as f:
            res_data = json.load(f)
            if res_data.get("classification") == "UPSTOX_INSTRUMENT_KEYS_RESOLVED":
                instr_key = res_data.get("resolved", {}).get(sym, {}).get("instrument_key")
            else:
                if res_data.get("blockers"):
                    res_blocker = res_data["blockers"][0]
    
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
            "classification": res_blocker,
            "candles_count": 0,
            "token_logged": False
        })
        report["endpoint_results"].append({
            "version": "v3",
            "endpoint_path": None,
            "http_status": None,
            "classification": res_blocker,
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
            with urllib.request.urlopen(req) as response:
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
            with urllib.request.urlopen(req) as response:
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
