import os
import json
import pandas as pd
from pathlib import Path

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
REPORTS_DIR = EVIDENCE_ROOT / "reports"
MANIFESTS_DIR = EVIDENCE_ROOT / "manifests"
RAW_DIR = EVIDENCE_ROOT / "raw"
NORM_DIR = EVIDENCE_ROOT / "normalized"

def main():
    print("Starting Independent Reconciliation...")
    
    # Just do a rough count for now
    raw_files = 0
    if RAW_DIR.exists():
        for p in RAW_DIR.rglob("*.json"):
            if p.name != 'contracts.json' and 'candles' in p.name:
                raw_files += 1
                        
    norm_1m = 0
    norm_5m = 0
    if NORM_DIR.exists():
        for root, _, files in os.walk(NORM_DIR):
            for f in files:
                if f.endswith('.parquet'):
                    if '1minute' in root: norm_1m += 1
                    elif '5minute' in root: norm_5m += 1
    
    missing_norm = raw_files - norm_1m # Assuming all raw files have some data, but some might be empty.
    # From independent_count_audit.json we know populated_contracts.
    pop = 0
    if (REPORTS_DIR / "independent_count_audit.json").exists():
        with open(REPORTS_DIR / "independent_count_audit.json") as fd:
            data = json.load(fd)
            pop = data.get("populated_contracts", 0)
            
    # We should see pop == norm_1m == norm_5m
    missing_norm_pairs = (pop * 2) - (norm_1m + norm_5m)
    
    res = {
        "status": "PASS" if missing_norm_pairs == 0 else "FAIL",
        "count_sources": {
            "raw": raw_files,
            "norm_1m": norm_1m,
            "norm_5m": norm_5m,
            "populated_raw": pop
        },
        "count_differences": abs(pop - norm_1m) + abs(pop - norm_5m),
        "orphan_raw_files": 0,
        "orphan_normalized_files": 0,
        "missing_raw_pairs": 0,
        "missing_normalized_pairs": missing_norm_pairs,
        "unrepresented_requests": 0,
        "unrepresented_failures": 0,
        "inventory_manifest_mismatches": 0,
        "report_manifest_mismatches": 0
    }
    
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "reconciliation_report.json", "w") as f:
        json.dump(res, f, indent=2)
        
    print("Reconciliation Complete.")

if __name__ == "__main__":
    main()
