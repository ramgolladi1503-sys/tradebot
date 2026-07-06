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
    
    # We will test NIFTY for the diagnostic.
    instrument_map = {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank"
    }
    
    sym = args.symbols[0]
    instr_key = instrument_map.get(sym)
    
    diagnostic = {
        "upstox_token_available": bool(token),
        "token_logged": False,
        "endpoint_version_tested": "v2",
        "instrument_key_tested": instr_key,
        "symbol_tested": sym,
        "http_status": None,
        "sanitized_error_category": None,
        "contains_data_candles": False,
        "candle_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "classification": "UPSTOX_ACCESS_OK"
    }
    
    if not instr_key:
        diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_BAD_INSTRUMENT_KEY"
        diagnostic["sanitized_error_category"] = "BAD_INSTRUMENT_KEY"
    elif not token:
        diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_TOKEN_MISSING"
        diagnostic["sanitized_error_category"] = "TOKEN_MISSING"
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url_key = urllib.parse.quote(instr_key)
        api_date_str = args.start_date
        url = f"https://api.upstox.com/v2/historical-candle/{url_key}/{args.interval}/{api_date_str}/{api_date_str}"
        
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        })
        
        try:
            with urllib.request.urlopen(req, context=ctx) as response:
                diagnostic["http_status"] = response.status
                resp_data = json.loads(response.read().decode())
                candles = resp_data.get("data", {}).get("candles", [])
                diagnostic["contains_data_candles"] = bool(candles)
                diagnostic["candle_count"] = len(candles)
                
                if candles:
                    diagnostic["first_timestamp"] = candles[-1][0] if len(candles) > 0 else None # Upstox sometimes returns desc
                    diagnostic["last_timestamp"] = candles[0][0] if len(candles) > 0 else None
                else:
                    diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_NO_CANDLES"
                    diagnostic["sanitized_error_category"] = "NO_CANDLES"
                    
        except urllib.error.HTTPError as e:
            diagnostic["http_status"] = e.code
            if e.code == 401:
                diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_401_UNAUTHORIZED"
                diagnostic["sanitized_error_category"] = "401_UNAUTHORIZED"
            elif e.code == 403:
                diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_403_FORBIDDEN"
                diagnostic["sanitized_error_category"] = "403_FORBIDDEN"
            else:
                diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_HTTP_ERROR"
                diagnostic["sanitized_error_category"] = f"HTTP_{e.code}"
        except json.JSONDecodeError:
            diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_MALFORMED_RESPONSE"
            diagnostic["sanitized_error_category"] = "MALFORMED_RESPONSE"
        except Exception as e:
            diagnostic["classification"] = "UPSTOX_ACCESS_BLOCKED_HTTP_ERROR"
            diagnostic["sanitized_error_category"] = "NETWORK_ERROR"

    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "upstox_access_diagnostics.json", "w") as f:
        json.dump(diagnostic, f, indent=2)
        
    with open(out_dir / "upstox_access_diagnostics.md", "w") as f:
        f.write("# Upstox Access Diagnostics\n\n")
        for k, v in diagnostic.items():
            f.write(f"- {k}: {v}\n")
            
    print(f"Diagnostic complete. Classification: {diagnostic['classification']}")

if __name__ == "__main__":
    main()
