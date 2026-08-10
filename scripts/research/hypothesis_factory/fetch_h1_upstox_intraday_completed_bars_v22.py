#!/usr/bin/env python3
"""
scripts/research/hypothesis_factory/fetch_h1_upstox_intraday_completed_bars_v22.py

Read-only Upstox 5-minute intraday candle fetcher for V22 H1 forward observation.
Strictly read-only data access. No order APIs, no broker writes, no live/paper routing.
Fails closed on missing token, missing instrument key, or API errors (e.g. 403 Forbidden).
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

BROKER_WRITE_AUTHORITY = False
ORDER_AUTHORITY = False
PAPER_AUTHORIZED = False
LIVE_AUTHORIZED = False

def main():
    parser = argparse.ArgumentParser(description="Read-only Upstox intraday 5-min candle fetcher.")
    parser.add_argument("--session-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--instrument-key", required=True, help="Upstox instrument key")
    parser.add_argument("--output-bars", required=True, help="CSV output path")
    parser.add_argument("--audit-output", required=True, help="JSON audit output path")
    parser.add_argument("--opening-start", default="09:15", help="HH:MM IST")
    parser.add_argument("--opening-end", default="11:30", help="HH:MM IST")
    args = parser.parse_args()

    token_sources = [
        os.environ.get("UPSTOX_ACCESS_TOKEN"),
        ".runtime/upstox_access_token",
        ".runtime/upstox_token",
        ".runtime/UPSTOX_ACCESS_TOKEN"
    ]
    token = None
    for src in token_sources:
        if src and os.path.isfile(src):
            try:
                with open(src) as f:
                    token = f.read().strip()
                if token:
                    break
            except Exception:
                pass
        elif src and not os.path.isfile(src) and len(src) > 20:
            token = src
            break

    audit = {
        "schema_version": "V22_UPSTOX_FETCH_AUDIT_V1",
        "candidate_id": "H1_TRAPPED_PUSH_SNAPBACK",
        "token_found": bool(token),
        "token_value_logged": False,
        "instrument_key_found": bool(args.instrument_key),
        "fetcher_used": "fetch_h1_upstox_intraday_completed_bars_v22.py",
        "fetch_attempted": False,
        "endpoint_family": "Intraday Candle Data V3",
        "fetch_command_redacted": f"python3 scripts/research/hypothesis_factory/fetch_h1_upstox_intraday_completed_bars_v22.py --session-date {args.session_date} --instrument-key <REDACTED> ...",
        "fetch_exit_code": None,
        "fetch_status": "UPSTOX_FETCH_BLOCKED_MISSING_TOKEN",
        "raw_candles_returned": 0,
        "bars_written": 0,
        "output_bars_path": None,
        "first_bar_ist": None,
        "last_bar_ist": None,
        "orders_created": 0,
        "broker_writes_created": 0,
        "authority_flags_all_false": True,
        "reason": "Token missing"
    }

    if not token:
        write_json(args.audit_output, audit)
        print("UPSTOX_FETCH_BLOCKED_MISSING_TOKEN")
        sys.exit(1)

    if not args.instrument_key:
        audit["fetch_status"] = "UPSTOX_FETCH_BLOCKED_MISSING_INSTRUMENT"
        audit["reason"] = "Instrument key missing"
        write_json(args.audit_output, audit)
        print("UPSTOX_FETCH_BLOCKED_MISSING_INSTRUMENT")
        sys.exit(1)

    encoded_key = urllib.parse.quote(args.instrument_key)
    url = f"https://api.upstox.com/v3/historical-candle/intraday/{encoded_key}/minutes/5"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    audit["fetch_attempted"] = True
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candles = data.get("data", {}).get("candles", [])
            audit["raw_candles_returned"] = len(candles)
            audit["fetch_exit_code"] = 0
            audit["fetch_status"] = "UPSTOX_FETCH_SUCCESS"
            audit["reason"] = f"Successfully fetched {len(candles)} candles"
            
            os.makedirs(os.path.dirname(args.output_bars), exist_ok=True)
            with open(args.output_bars, "w") as f:
                f.write("datetime,open,high,low,close,volume_optional,source,completed_bar,timezone\n")
                for c in candles:
                    dt, open_, high, low, close, vol = c[:6]
                    f.write(f"{dt},{open_},{high},{low},{close},{vol},UPSTOX_INTRADAY_V3,true,Asia/Kolkata\n")
            
            audit["bars_written"] = len(candles)
            audit["output_bars_path"] = args.output_bars
            if candles:
                audit["first_bar_ist"] = candles[0][0]
                audit["last_bar_ist"] = candles[-1][0]
                
            write_json(args.audit_output, audit)
            print("UPSTOX_FETCH_SUCCESS")
            sys.exit(0)
    except urllib.error.HTTPError as e:
        audit["fetch_exit_code"] = e.code
        audit["fetch_status"] = "UPSTOX_FETCH_BLOCKED_API_ERROR"
        audit["reason"] = f"HTTP Error {e.code}: {e.reason}"
        write_json(args.audit_output, audit)
        print(f"UPSTOX_FETCH_BLOCKED_API_ERROR (HTTP {e.code})")
        sys.exit(1)
    except Exception as e:
        audit["fetch_exit_code"] = 1
        audit["fetch_status"] = "UPSTOX_FETCH_BLOCKED_API_ERROR"
        audit["reason"] = str(e)
        write_json(args.audit_output, audit)
        print(f"UPSTOX_FETCH_BLOCKED_API_ERROR ({e})")
        sys.exit(1)

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    main()
