#!/usr/bin/env python3
import json
import hashlib
import os
import glob
from collections import defaultdict
from pathlib import Path
import datetime

def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", required=True)
    parser.add_argument("--out-manifest", required=True)
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    out_manifest = Path(args.out_manifest)

    records = []
    manifest = {
        "source_manifest_version": "v2",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_authority_root": str(corpus_dir),
        "special_session_policies": [],
        "records": []
    }
    
    local_files = []
    for root, _, files in os.walk(corpus_dir):
        if "underlying" not in root.split(os.sep):
            continue
        for file in files:
            if file.endswith(".parquet"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, corpus_dir)
                logical_path = f"runtime/upstox_candidate_replay/{rel_path}"
                file_sz = os.path.getsize(full_path)
                sha = _hash_file(full_path)
                
                base = file.split(".")[0]
                if "_" not in base:
                    continue
                symbol, raw_date = base.rsplit("_", 1)
                
                import pandas as pd
                row_count = len(pd.read_parquet(full_path))
                
                # Format raw_date (e.g. 20240719 -> 2024-07-19)
                session_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                
                if row_count != 375:
                    if session_date == "2024-11-01":
                        # Explicit policy for Muhurat trading
                        manifest["special_session_policies"].append({
                            "policy": "EXCLUDE_SPECIAL_SESSION_WITH_RECORDED_REASON",
                            "session_date": session_date,
                            "symbol": symbol,
                            "expected_rows": 375,
                            "actual_rows": row_count,
                            "reason": "Muhurat trading day"
                        })
                    else:
                        manifest["special_session_policies"].append({
                            "policy": "EXCLUDE_SPECIAL_SESSION_WITH_RECORDED_REASON",
                            "session_date": session_date,
                            "symbol": symbol,
                            "expected_rows": 375,
                            "actual_rows": row_count,
                            "reason": "Unknown short session"
                        })
                    continue
                
                records.append({
                    "logical_path": logical_path,
                    "symbol": symbol,
                    "session_date": session_date,
                    "actual_sha256": sha,
                    "byte_size": file_sz,
                    "source_record_id": f"{symbol}_{session_date}",
                    "inventory_record_identity": {
                        "actual_sha256": sha,
                        "byte_size": file_sz,
                        "logical_path": logical_path
                    }
                })

    records.sort(key=lambda r: (r["session_date"], r["logical_path"]))
    manifest["records"] = records

    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    with open(out_manifest, "w") as f:
        json.dump(manifest, f, separators=(',', ':'))
        
    sidecar_path = Path(str(out_manifest) + ".sha256")
    manifest_sha = _hash_file(out_manifest)
    with open(sidecar_path, "w") as f:
        f.write(f"{manifest_sha}  {out_manifest.name}\n")

if __name__ == "__main__":
    main()
