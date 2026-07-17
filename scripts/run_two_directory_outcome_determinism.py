import os
import subprocess
import hashlib
import json
import tempfile
import shutil
from pathlib import Path
import sys

def hash_file(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def hash_fingerprints(out_path):
    if not os.path.exists(out_path):
        return None
    with open(out_path) as f:
        data = json.load(f)
    fps = [d.get("outcome_fingerprint", "") for d in data]
    return hashlib.sha256(",".join(fps).encode()).hexdigest()

def extract_portable_hashes(outdir):
    p = Path(outdir)
    return {
        "development_outcome_labels.json": hash_file(p / "development_outcome_labels.json"),
        "development_outcome_reconciliation.json": hash_file(p / "development_outcome_reconciliation.json"),
        "outcome_contract.json": hash_file(p / "outcome_contract.json"),
        "fingerprints": hash_fingerprints(p / "development_outcome_labels.json")
    }

def main():
    repo_root = Path(__file__).parent.parent
    reviews_dir = repo_root / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "research_partition.json") as f:
        part = json.load(f)
    manifest_path = repo_root / "docs" / "agent_reviews" / "opening_state_momentum" / "source_manifest.json"
    with open(manifest_path) as mf:
        manifest_hash = json.load(mf).get("portable_dataset_hash", "")
    decisions = reviews_dir / "candidate_decisions.json"
    partition = reviews_dir / "research_partition.json"
    
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        cmd1 = ["python", str(repo_root / "scripts" / "label_opening_state_development_outcomes.py"), 
                "--decisions", str(decisions),
                "--partition", str(partition),
                "--manifest", str(manifest_path),
                "--manifest-hash", manifest_hash,
                "--output-dir", d1]
                
        cmd2 = ["python", str(repo_root / "scripts" / "label_opening_state_development_outcomes.py"), 
                "--decisions", str(decisions),
                "--partition", str(partition),
                "--manifest", str(manifest_path),
                "--manifest-hash", manifest_hash,
                "--output-dir", d2]
                
        subprocess.run(cmd1, check=True)
        subprocess.run(cmd2, check=True)
        
        hashes_a = extract_portable_hashes(d1)
        hashes_b = extract_portable_hashes(d2)
        
        match = hashes_a == hashes_b
        
        res = {
            "match": match,
            "run_a_hashes": hashes_a,
            "run_b_hashes": hashes_b
        }
        
        with open(reviews_dir / "outcome_label_determinism.json", "w") as f:
            json.dump(res, f, indent=2)
            
if __name__ == "__main__":
    main()
