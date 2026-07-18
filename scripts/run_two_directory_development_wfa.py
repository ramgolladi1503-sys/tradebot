import os
import shutil
import tempfile
import subprocess
import json
import hashlib
from pathlib import Path

def get_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def normalize_json(path):
    # Load and re-save to remove formatting differences or paths
    try:
        with open(path, "r") as f:
            data = json.load(f)
        with open(path, "w") as f:
            json.dump(data, f, sort_keys=True)
    except:
        pass

def run_in_dir(src_dir, target_dir):
    shutil.copytree(src_dir, target_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    
    # Run generator
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target_dir)
    
    subprocess.run(["python", "scripts/generate_opening_state_development_wfa.py"], cwd=target_dir, env=env, check=True)
    
    docs_dir = Path(target_dir) / "docs" / "agent_reviews" / "opening_state_momentum"
    
    files_to_hash = [
        "development_wfa_contract.json",
        "development_wfa_fold_assignments.json",
        "development_wfa_metrics.json",
        "development_wfa_temporal_stability.json",
        "development_wfa_negative_controls.json",
        "development_wfa_bootstrap.json",
        "development_wfa_holdout_access_audit.json"
    ]
    
    hashes = {}
    for f in files_to_hash:
        p = docs_dir / f
        normalize_json(p)
        hashes[f] = get_hash(p)
        
    return hashes

def main():
    src_dir = Path.cwd()
    
    with tempfile.TemporaryDirectory() as dir_a, tempfile.TemporaryDirectory() as dir_b:
        print("Running in Directory A...")
        hashes_a = run_in_dir(src_dir, dir_a)
        
        print("Running in Directory B...")
        hashes_b = run_in_dir(src_dir, dir_b)
        
        mismatch = False
        for k in hashes_a:
            if hashes_a[k] != hashes_b[k]:
                print(f"Mismatch in {k}: {hashes_a[k]} != {hashes_b[k]}")
                mismatch = True
                
        if mismatch:
            print("DETERMINISM FAILED")
            # Save determinism result
            out = {"determinism_verified": False, "hashes_a": hashes_a, "hashes_b": hashes_b}
        else:
            print("DETERMINISM VERIFIED")
            out = {"determinism_verified": True, "hashes_a": hashes_a, "hashes_b": hashes_b}
            
        with open("docs/agent_reviews/opening_state_momentum/development_wfa_determinism.json", "w") as f:
            json.dump(out, f, indent=2)

if __name__ == "__main__":
    main()
