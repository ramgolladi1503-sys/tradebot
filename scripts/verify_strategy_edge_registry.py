#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def main():
    registry_dir = Path("research/strategy_edge_registry/records")
    if not registry_dir.exists():
        print("Registry directory not found")
        sys.exit(1)
        
    for p in registry_dir.glob("*.json"):
        with open(p) as f:
            data = json.load(f)
            
            # Focused regression guard
            if data.get("hypothesis_id") == "nifty_rsi2_mean_reversion" and data.get("publication_commit") == "f806c02917152b5f2bac44521d14530a9d470f4b":
                verdict = data.get("overall_verdict")
                if verdict in ["STRUCTURAL_EDGE_SUPPORTED"]:
                    print(f"REGRESSION DETECTED: {p.name} claims {verdict}")
                    sys.exit(1)
                
                status = data.get("production_integration_status")
                if status in ["production ready", "approved for options translation", "runtime eligible"]:
                    print(f"REGRESSION DETECTED: {p.name} claims status {status}")
                    sys.exit(1)
                    
    print("Verification passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
