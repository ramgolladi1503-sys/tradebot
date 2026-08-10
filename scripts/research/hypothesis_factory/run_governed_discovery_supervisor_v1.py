#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

SUPERVISOR_VERSION = "v1"

FAMILY_QUEUE = [
    "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1",
    "OPENING_SESSION_MICROSTRUCTURE_PROXY_FAMILY_V1",
    "PRE_CLOSE_IMBALANCE_PROXY_FAMILY_V1",
    "VOLATILITY_REGIME_CONDITIONAL_FAMILY_V1",
    "SESSION_GAP_CONTINUATION_REVERSAL_FAMILY_V1",
    "BREADTH_OR_CONSTITUENT_LEAD_LAG_FAMILY_V1",
    "OPTIONS_MICROSTRUCTURE_FAMILY_V1",
    "FUTURES_BASIS_OR_PREMIUM_FAMILY_V1"
]

BANNED_FAMILIES = {
    "BDE2_SEQUENCE_FAMILY_V1",
    "BDE2_MORPHOLOGY_CLUSTER_FAMILY_V1",
    "BDE2_TRANSITION_COMMUNITY_FAMILY_V1"
}

def verify_git_state(root: Path) -> bool:
    try:
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root).decode("utf-8").strip()
        if branch != "research/strategy-certification-kernel-v0":
            print(f"BLOCKED: Invalid branch {branch}")
            return False
        
        # -uno avoids failing on the newly generated evidence files that we haven't committed yet
        status = subprocess.check_output(["git", "status", "--short", "-uno"], cwd=root).decode("utf-8").strip()
        if status:
            print(f"BLOCKED: Worktree is dirty\n{status}")
            return False
            
        return True
    except Exception as e:
        print(f"BLOCKED: Failed to verify git state: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent.parent
    
    if not verify_git_state(root):
        sys.exit(1)
        
    out_dir = root / "research" / "evidence" / "governed_discovery_supervisor_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # After parking TOD family, advance directly to OPENING_SESSION_MICROSTRUCTURE_PROXY_FAMILY_V1
    target_family = "OPENING_SESSION_MICROSTRUCTURE_PROXY_FAMILY_V1"
    
    print(f"Targeting: {target_family}")
    
    script_dir = root / "scripts" / "research" / "hypothesis_factory"
    
    print("Pre-outcome stage starting for Opening Session Microstructure Proxy family...")
    subprocess.check_call([sys.executable, str(script_dir / "build_opening_session_microstructure_proxy_candidates_v1.py")], cwd=root)
    
    print("Development-only outcome stage starting for Opening Session Microstructure Proxy family...")
    try:
        out = subprocess.check_output([sys.executable, str(script_dir / "run_opening_session_microstructure_proxy_development_v1.py")], cwd=root).decode("utf-8").strip()
        status = out.split("\n")[-1]
    except subprocess.CalledProcessError as e:
        print(f"BLOCKED: Opening development outcome stage failed {e}")
        sys.exit(1)
        
    print(f"Opening Development Outcome status: {status}")
    
    with (out_dir / "run_manifest.json").open("w") as f:
        json.dump({
            "target_family": target_family,
            "status": status, 
            "locked_outcomes_accessed": False, 
            "edge_claimed": False,
            "structural_edge_certified": False,
            "execution_viable": False
        }, f, indent=2)
        
    with (out_dir / "family_queue.json").open("w") as f:
        json.dump({"queue": FAMILY_QUEUE[2:]}, f, indent=2)
        
    with (out_dir / "family_results.jsonl").open("a") as f:
        f.write(json.dumps({"family": target_family, "status": status, "timestamp": "2026-08-10T00:00:00Z"}) + "\n")
        
    print(status)
    
if __name__ == "__main__":
    main()
