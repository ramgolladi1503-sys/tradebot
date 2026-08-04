#!/usr/bin/env python3
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

def calculate_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("=== Sealing Premarket Artifacts ===")
    session_date = "20260804"
    evidence_root = Path(f"/Users/madhuram/tradebot-upstox-replay-quality-capture-v1/runtime/market_data/upstox/{session_date}/full_day_replay_v1")
    
    if not evidence_root.exists():
        print(f"ERROR: Evidence root {evidence_root} does not exist.", file=sys.stderr)
        sys.exit(1)
        
    premarket_files = []
    checksums = {}
    
    # Files to hash
    for sub in ["instrument_master", "constituents", "subscription"]:
        dir_path = evidence_root / sub
        if not dir_path.exists():
            continue
        for p in sorted(dir_path.rglob("*")):
            if p.is_file():
                rel = p.relative_to(evidence_root)
                sha = calculate_sha256(p)
                checksums[str(rel)] = sha
                premarket_files.append({
                    "path": str(rel),
                    "size_bytes": p.stat().st_size,
                    "sha256": sha
                })
                
    # Write SHA256SUMS
    with open(evidence_root / "SHA256SUMS", "w") as f:
        for item in premarket_files:
            f.write(f"{item['sha256']}  {item['path']}\n")
            
    # Load hashes
    master_hash = checksums.get("instrument_master/complete.json", "")
    constituent_hash = checksums.get("constituents/nifty50_constituents_20260804.json", "")
    plan_hash = checksums.get("subscription/subscription_plan_20260804.json", "")
    
    manifest = {
        "schema_version": 1,
        "session_date": session_date,
        "timezone": "Asia/Kolkata",
        "source_repository_sha": "ebf0c59dcc8fa8d9bb57572c5331282dd89e473b",
        "capture_implementation_sha": "ebf0c59dcc8fa8d9bb57572c5331282dd89e473b",
        "premarket_prepared_at": datetime.now().isoformat(),
        "instrument_master_hash": master_hash,
        "constituent_map_hash": constituent_hash,
        "subscription_plan_hash": plan_hash,
        "premarket_file_inventory": premarket_files,
        "status": "PREMARKET_PREPARED",
        "general_capture_verdict": "CAPTURE_BLOCKED_EXTERNAL",
        "meg_verdict": "CAPTURE_BLOCKED_EXTERNAL",
        "verdict_reason": "market session not yet available (waiting for 09:00:00 IST pre-open connection)"
    }
    
    with open(evidence_root / "artifact_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Premarket sealed successfully under {evidence_root}")

if __name__ == "__main__":
    main()
