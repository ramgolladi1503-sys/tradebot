#!/usr/bin/env python3
import os
import json
import gzip
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

def main():
    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "classification": "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_FILE_MISSING",
        "source": "manual_official_upstox_download",
        "imported_at": None,
        "file_hash": None,
        "row_count": 0,
        "certification_eligible": False
    }
    
    input_paths = [
        Path("data/manual/upstox_instruments/complete.json.gz"),
        Path("data/manual/upstox_instruments/complete.json"),
        Path("runtime/manual/upstox_instruments/complete.json.gz"),
        Path("runtime/manual/upstox_instruments/complete.json")
    ]
    
    found_path = None
    for p in input_paths:
        if p.exists():
            found_path = p
            break
            
    if not found_path:
        write_report(out_dir, report)
        return
        
    try:
        # Check empty
        if found_path.stat().st_size == 0:
            report["classification"] = "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_MALFORMED"
            write_report(out_dir, report)
            return
            
        if found_path.suffix == ".gz":
            with gzip.open(found_path, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(found_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        # Handle dict vs list format from Upstox
        if isinstance(data, dict):
            if len(data) > 0 and isinstance(list(data.values())[0], dict):
                data = list(data.values())
            else:
                data = [] # Malformed
                
        if not isinstance(data, list) or len(data) == 0:
            report["classification"] = "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_MALFORMED"
            write_report(out_dir, report)
            return
            
        # Check instrument_key exists in at least one item
        has_key = any("instrument_key" in item for item in data if isinstance(item, dict))
        if not has_key:
            report["classification"] = "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_NO_INSTRUMENT_KEYS"
            write_report(out_dir, report)
            return
            
        # File is valid, compute hash and save
        with open(found_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            
        dest_dir = Path("runtime/upstox_instruments")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / "complete.json"
        
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            
        report["classification"] = "UPSTOX_INSTRUMENT_MASTER_IMPORTED"
        report["imported_at"] = datetime.now().isoformat()
        report["file_hash"] = file_hash
        report["row_count"] = len(data)
        report["certification_eligible"] = True
        
    except json.JSONDecodeError:
        report["classification"] = "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_MALFORMED"
    except Exception as e:
        report["classification"] = "UPSTOX_INSTRUMENT_MASTER_IMPORT_BLOCKED_MALFORMED"
        
    write_report(out_dir, report)

def write_report(out_dir, report):
    with open(out_dir / "upstox_instrument_master_import.json", "w") as f:
        json.dump(report, f, indent=2)
        
    with open(out_dir / "upstox_instrument_master_import.md", "w") as f:
        f.write("# Upstox Instrument Master Import\n\n")
        for k, v in report.items():
            f.write(f"- **{k}**: {v}\n")
    print(f"Import complete. Classification: {report['classification']}")

if __name__ == "__main__":
    main()
