#!/usr/bin/env python3
import argparse
import gzip
import json
import urllib.request
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", required=True)
    args = parser.parse_args()
    
    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    runtime_instr_dir = Path("runtime/upstox_instruments")
    runtime_instr_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "classification": "UPSTOX_INSTRUMENT_KEYS_BLOCKED",
        "source": "official_upstox_instrument_json",
        "symbols_requested": args.symbols,
        "resolved": {},
        "unresolved": list(args.symbols),
        "blockers": [],
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }
    
    url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
    instruments: list[dict] = []

    try:
        req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req) as response:
            if response.info().get("Content-Encoding") == "gzip":
                f = gzip.GzipFile(fileobj=response)
                data = f.read()
            else:
                data = response.read()
            data = json.loads(data.decode("utf-8"))

            if isinstance(data, dict):
                values = list(data.values())
                if values and all(isinstance(item, dict) for item in values):
                    instruments = values
            elif isinstance(data, list):
                if all(isinstance(item, dict) for item in data):
                    instruments = data
    except Exception:
        report["blockers"].append("UPSTOX_INSTRUMENT_MASTER_DOWNLOAD_FAILED")

    if not instruments:
        report["classification"] = "UPSTOX_INSTRUMENT_KEYS_BLOCKED"
        if "UPSTOX_INSTRUMENT_MASTER_DOWNLOAD_FAILED" not in report["blockers"]:
            report["blockers"].append("UPSTOX_INSTRUMENT_MASTER_MALFORMED")
        write_report(out_dir, report)
        return

    # Filter rules for index
    def is_index(item):
        return isinstance(item, dict) and item.get("instrument_type") == "INDEX" and item.get("segment") == "NSE_INDEX"
    
    for sym in args.symbols:
        candidates = []
        for item in instruments:
            # Match rules:
            if is_index(item):
                tsym = item.get("trading_symbol", "")
                name = item.get("name", "")
                
                if sym == "NIFTY":
                    if tsym == "NIFTY" or name == "Nifty 50":
                        candidates.append(item)
                elif sym == "BANKNIFTY":
                    if tsym == "BANKNIFTY" or name == "Nifty Bank":
                        candidates.append(item)
        
        # Exact match logic
        if not candidates:
            report["blockers"].append(f"UPSTOX_{sym}_KEY_NOT_FOUND")
        elif len(candidates) == 1:
            report["resolved"][sym] = {
                "instrument_key": candidates[0].get("instrument_key"),
                "trading_symbol": candidates[0].get("tradingsymbol"),
                "name": candidates[0].get("name"),
                "exchange": candidates[0].get("exchange"),
                "segment": candidates[0].get("segment")
            }
            report["unresolved"].remove(sym)
        else:
            report["blockers"].append("UPSTOX_INSTRUMENT_KEY_AMBIGUOUS")
            report["classification"] = "UPSTOX_INSTRUMENT_KEYS_BLOCKED"
            write_report(out_dir, report)
            return
    
    if len(report["resolved"]) == len(args.symbols):
        report["classification"] = "UPSTOX_INSTRUMENT_KEYS_RESOLVED"
    elif len(report["resolved"]) > 0:
        report["classification"] = "UPSTOX_INSTRUMENT_KEYS_PARTIAL"
        
    write_report(out_dir, report)

def write_report(out_dir, report):
    with open(out_dir / "upstox_instrument_resolution.json", "w") as f:
        json.dump(report, f, indent=2)
        
    with open(out_dir / "upstox_instrument_resolution.md", "w") as f:
        f.write("# Upstox Instrument Resolution\n\n")
        for k, v in report.items():
            f.write(f"- **{k}**: {v}\n")
    print(f"Resolver complete. Classification: {report['classification']}")

if __name__ == "__main__":
    main()
