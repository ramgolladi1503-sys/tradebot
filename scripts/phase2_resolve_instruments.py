import json
import urllib.request
import gzip
import csv
from pathlib import Path
import io

def main():
    reports_dir = Path("runtime/constituent_lead_lag/upstox_v1/reports")
    with open(reports_dir / "source_authority.json", "r") as f:
        authority = json.load(f)
        
    required_symbols = set()
    for auth in authority:
        required_symbols.update(auth["constituents"])
        
    print(f"Total equity constituents to resolve: {len(required_symbols)}")
    
    print("Downloading Upstox complete instrument list...")
    req = urllib.request.Request("https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz")
    with urllib.request.urlopen(req) as response:
        compressed_data = response.read()
        
    csv_data = gzip.decompress(compressed_data).decode('utf-8')
    reader = csv.DictReader(io.StringIO(csv_data))
    
    instrument_map = {}
    
    # We also need to map NIFTY and BANKNIFTY
    
    for row in reader:
        exchange = row.get("exchange", "")
        tradingsymbol = row.get("tradingsymbol", "")
        name = row.get("name", "")
        inst_key = row.get("instrument_key", "")
        
        if exchange == "NSE_EQ":
            if tradingsymbol in required_symbols:
                instrument_map[tradingsymbol] = {
                    "symbol": tradingsymbol,
                    "upstox_instrument_key": inst_key,
                    "upstox_exchange": exchange,
                    "upstox_name": name
                }
        elif exchange == "NSE_INDEX":
            if name.upper() in ["NIFTY 50", "NIFTY BANK"]:
                symbol = "NIFTY" if "50" in name else "BANKNIFTY"
                instrument_map[symbol] = {
                    "symbol": symbol,
                    "upstox_instrument_key": inst_key,
                    "upstox_exchange": exchange,
                    "upstox_name": name
                }
                
    results = list(instrument_map.values())
    
    print(f"Resolved {len(results)} instruments.")
    
    # Check for missing symbols
    missing = required_symbols - set([r["symbol"] for r in results])
    if missing:
        print(f"Warning: Could not resolve {len(missing)} symbols: {missing}")
        
    with open(reports_dir / "instrument_resolution.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
