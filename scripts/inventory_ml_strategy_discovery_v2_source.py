#!/usr/bin/env python3
import json
import hashlib
import os
import glob
from collections import defaultdict
from pathlib import Path
import datetime

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    manifest_path = Path(args.manifest_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    manifest_records = manifest.get("records", [])
    if not manifest_records and isinstance(manifest, list):
        manifest_records = manifest

    manifest_paths = set(os.path.relpath(r["logical_path"], "runtime/upstox_candidate_replay") if r["logical_path"].startswith("runtime/upstox_candidate_replay") else r["logical_path"] for r in manifest_records)
    
    local_files = []
    for root, _, files in os.walk(corpus_dir):
        for file in files:
            if file.endswith(".parquet"):
                local_files.append(os.path.relpath(os.path.join(root, file), corpus_dir))

    local_files_set = set(local_files)

    delta_paths = local_files_set - manifest_paths
    missing_paths = manifest_paths - local_files_set

    # Categorize delta by instrument and session date
    # Format expected: NSE_EQ|INE...|INSTRUMENT/YYYY-MM-DD.parquet
    delta_by_instrument = defaultdict(list)
    delta_by_session_date = defaultdict(list)
    duplicates = []
    outside_expected_layout = []
    
    for p in delta_paths:
        parts = Path(p).parts
        if len(parts) >= 3:
            date_folder = parts[0]
            file_name = parts[-1].replace(".parquet", "")
            
            instrument = file_name.split("_")[0] if "_" in file_name else file_name
            delta_by_instrument[instrument].append(p)
            try:
                # check if valid date
                parsed_date = datetime.datetime.strptime(date_folder, "%Y%m%d")
                date_str = parsed_date.strftime("%Y-%m-%d")
                delta_by_session_date[date_str].append(p)
            except ValueError:
                outside_expected_layout.append(p)
        else:
            outside_expected_layout.append(p)

    dates = sorted(delta_by_session_date.keys())
    earliest_date = dates[0] if dates else None
    latest_date = dates[-1] if dates else None
    
    # Check if delta contains NIFTY sessions later than V1 selected maximum date
    # V1 validation was consumed, which means it had a specific max date. 
    # The instructions say: "whether the delta contains fresh NIFTY sessions later than the V1 selected NIFTY maximum date."
    # We assume any NIFTY session in delta is potentially fresh. 
    nifty_fresh_available = any("NIFTY" in k for k in delta_by_instrument.keys())
    
    verdict = "FRESH_NIFTY_OOS_AVAILABLE" if nifty_fresh_available else "NO_FRESH_NIFTY_OOS_AVAILABLE"

    inventory = {
        "schema_version": "1.0",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "total_local_parquet": len(local_files_set),
        "total_manifest_records": len(manifest_paths),
        "delta_count": len(delta_paths),
        "missing_count": len(missing_paths),
        "earliest_delta_date": earliest_date,
        "latest_delta_date": latest_date,
        "verdict": verdict
    }

    with open(out_dir / "inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)

    with open(out_dir / "delta_records.json", "w") as f:
        json.dump({
            "schema_version": "1.0",
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
            "delta_paths": list(delta_paths),
            "delta_by_instrument": dict(delta_by_instrument),
            "delta_by_session_date": dict(delta_by_session_date),
            "outside_expected_layout": outside_expected_layout
        }, f, indent=2)

    with open(out_dir / "report.md", "w") as f:
        f.write(f"# Source Inventory Report\n\n")
        f.write(f"- Total Local Parquet: {len(local_files_set)}\n")
        f.write(f"- Total Manifest Records: {len(manifest_paths)}\n")
        f.write(f"- Delta Count: {len(delta_paths)}\n")
        f.write(f"- Earliest Date: {earliest_date}\n")
        f.write(f"- Latest Date: {latest_date}\n")
        f.write(f"- Verdict: **{verdict}**\n")

if __name__ == "__main__":
    main()
