#!/usr/bin/env python3
import json
import argparse
import urllib.request
import ssl
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
    
    instruments = []
    
    # Try reading from manual import
    local_master = runtime_instr_dir / "complete.json"
    if local_master.exists():
        report["source"] = "manual_imported_master"
        with open(local_master, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    if len(data) > 0 and isinstance(list(data.values())[0], dict):
                        instruments = list(data.values())
                elif isinstance(data, list):
                    instruments = data
            except Exception:
                pass
    
    if not instruments:
        # Fallback to download
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        try:
            import gzip
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, context=ctx) as response:
                if response.info().get('Content-Encoding') == 'gzip':
                    f = gzip.GzipFile(fileobj=response)
                    data = f.read()
                else:
                    data = response.read()
                data = json.loads(data.decode('utf-8'))
                
                if isinstance(data, dict):
                    if len(data) > 0 and isinstance(list(data.values())[0], dict):
                        instruments = list(data.values())
                elif isinstance(data, list):
                    instruments = data
        except Exception:
            report["blockers"].append("UPSTOX_INSTRUMENT_MASTER_DOWNLOAD_FAILED")
            
    if not instruments:
        report["classification"] = "UPSTOX_INSTRUMENT_KEYS_BLOCKED"
        if not report["blockers"]:
            report["blockers"].append("UPSTOX_INSTRUMENT_MASTER_MALFORMED")
        write_report(out_dir, report)
        return

    # Filter rules for index
    def is_index(item):
        return isinstance(item, dict) and item.get("instrument_type") == "INDEX" and item.get("exchange") == "NSE_INDEX"
    
    for sym in args.symbols:
        candidates = []
        for item in instruments:
            # Match rules:
            if is_index(item):
                tsym = item.get("tradingsymbol", "")
                name = item.get("name", "")
                
                if sym == "NIFTY":
                    if tsym == "NIFTY 50" or name == "Nifty 50":
                        candidates.append(item)
                elif sym == "BANKNIFTY":
                    if tsym == "NIFTY BANK" or name == "Nifty Bank":
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
            # Ambiguous
            report["blockers"].append("UPSTOX_INSTRUMENT_KEY_AMBIGUOUS")
    
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
