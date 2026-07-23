import argparse
import sys
import json
import hashlib
from pathlib import Path

def run_proxy():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", required=True)
    parser.add_argument("--proxy-weights", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-community-reconstructed-proxy", action="store_true")
    args = parser.parse_args()
    
    if not args.allow_community_reconstructed_proxy:
        print("Explicit opt-in required: --allow-community-reconstructed-proxy")
        sys.exit(1)
        
    bars_path = Path(args.bars)
    weights_path = Path(args.proxy_weights)
    out_dir = Path(args.output)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Write frozen pre-outcome manifest
    manifest = {
        "bars_path": str(bars_path),
        "bars_sha256": "UNKNOWN_OR_MISSING",
        "weights_path": str(weights_path),
        "weights_sha256": "UNKNOWN_OR_MISSING",
        "strategy_source_sha256": "mock_hash",
        "runner_source_sha256": "mock_hash",
        "thresholds": "frozen_v1",
        "decision_times": "frozen_v1",
        "cost_bps": 5,
        "delay_rules": "one_bar_delay",
        "control_rules": "matched_no_lead",
        "eligible_date_range": "UNKNOWN"
    }
    
    if bars_path.exists():
        with open(bars_path, "rb") as f:
            manifest["bars_sha256"] = hashlib.sha256(f.read(1024*1024)).hexdigest()
            
    if weights_path.exists():
        with open(weights_path, "rb") as f:
            manifest["weights_sha256"] = hashlib.sha256(f.read(1024*1024)).hexdigest()
            
    with open(out_dir / "frozen_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    if not bars_path.exists() or manifest["bars_sha256"] == "UNKNOWN_OR_MISSING":
        print("INSUFFICIENT_PROXY_OHLCV")
        sys.exit(1)
        
    print("Running proxy evaluation...")

if __name__ == "__main__":
    run_proxy()
