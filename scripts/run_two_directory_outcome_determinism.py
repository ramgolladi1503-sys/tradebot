import os
import sys
import shutil
import tempfile
import subprocess
import json
import hashlib

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def hash_file(path: str) -> str:
    if not os.path.exists(path):
        return None
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def main():
    script1 = os.path.join(repo_root, "scripts", "label_opening_state_development_outcomes.py")
    script2 = os.path.join(repo_root, "scripts", "audit_outcome_oracle.py")
    
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        env1 = os.environ.copy()
        env1["OUTCOME_DIR"] = d1
        
        env2 = os.environ.copy()
        env2["OUTCOME_DIR"] = d2
        
        # Run A
        subprocess.run([sys.executable, script1], env=env1, check=True)
        subprocess.run([sys.executable, script2], env=env1, check=True)
        
        # Run B
        subprocess.run([sys.executable, script1], env=env2, check=True)
        subprocess.run([sys.executable, script2], env=env2, check=True)
        
        files = [
            "development_outcome_labels.json",
            "development_outcome_reconciliation.json",
            "outcome_oracle_comparison.json"
        ]
        
        hashes1 = {}
        hashes2 = {}
        
        for f in files:
            hashes1[f] = hash_file(os.path.join(d1, f))
            hashes2[f] = hash_file(os.path.join(d2, f))
            
        res = {
            "run_a_dir": d1,
            "run_b_dir": d2,
            "hashes_a": hashes1,
            "hashes_b": hashes2,
            "determinism_verified": hashes1 == hashes2
        }
        
        out_path = os.path.join(repo_root, "docs", "agent_reviews", "opening_state_momentum", "outcome_label_determinism.json")
        with open(out_path, "w") as f:
            json.dump(res, f, indent=2)

if __name__ == "__main__":
    main()
