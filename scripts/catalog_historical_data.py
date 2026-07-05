#!/usr/bin/env python3
import os
import json
from pathlib import Path

def main():
    base_dir = Path("runtime/upstox_candidate_replay")
    
    dates_found = []
    if base_dir.exists():
        for d in base_dir.iterdir():
            if d.is_dir() and d.name.isdigit() and len(d.name) == 8:
                dates_found.append(d.name)
                
    dates_found.sort()
    
    catalog = {
        "dates_available": dates_found,
        "earliest_date": dates_found[0] if dates_found else None,
        "latest_date": dates_found[-1] if dates_found else None,
        "symbols_available": ["NIFTY", "BANKNIFTY"],
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }

    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "historical_data_catalog.json", "w") as f:
        json.dump(catalog, f, indent=2)
        
    with open(out_dir / "historical_data_catalog.md", "w") as f:
        f.write("# Historical Data Catalog\n\n")
        f.write(f"- Dates Available: {len(dates_found)}\n")
        f.write(f"- Earliest: {catalog['earliest_date']}\n")
        f.write(f"- Latest: {catalog['latest_date']}\n")
        
    print(f"Catalogued {len(dates_found)} historical dates.")

if __name__ == "__main__":
    main()
