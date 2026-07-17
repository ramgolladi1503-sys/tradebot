import os
import subprocess
import hashlib
import json
from pathlib import Path

def hash_file(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def extract_portable_hashes(outdir):
    p = Path(outdir)
    return {
        "candidate_decisions.json": hash_file(p / "candidate_decisions.json"),
        "development_session_reconciliation.json": hash_file(p / "development_session_reconciliation.json"),
        "threshold_replay_audit.json": hash_file(p / "threshold_replay_audit.json"),
        "threshold_oracle_comparison.json": hash_file(p / "threshold_oracle_comparison.json"),
        # Extract fingerprints manually
        "fingerprints": hash_fingerprints(p / "candidate_decisions.json")
    }
    
def hash_fingerprints(decisions_path):
    if not os.path.exists(decisions_path):
        return None
    with open(decisions_path) as f:
        data = json.load(f)
    fps = [d.get("candidate_fingerprint", "") for d in data]
    return hashlib.sha256(",".join(fps).encode()).hexdigest()

def main():
    repo_root = Path(__file__).parent.parent
    docs_dir = repo_root / "docs" / "agent_reviews" / "opening_state_momentum"
    
    run_a = Path("/tmp/opening_momentum_run_a")
    run_b = Path("/tmp/opening_momentum_run_b")
    
    subprocess.run(["rm", "-rf", str(run_a)])
    subprocess.run(["rm", "-rf", str(run_b)])
    
    universe = docs_dir / "session_universe_audit.json"
    partition = docs_dir / "research_partition.json"
    manifest = docs_dir / "source_manifest_full.json"
    
    # Run A
    subprocess.run([
        "python", "scripts/audit_opening_state_causal_replay.py",
        "--universe", str(universe),
        "--partition", str(partition),
        "--manifest", str(manifest),
        "--outdir", str(run_a)
    ], cwd=str(repo_root), check=True)
    
    subprocess.run([
        "python", "scripts/audit_threshold_oracle.py",
        "--universe", str(universe),
        "--partition", str(partition),
        "--manifest", str(manifest),
        "--outdir", str(run_a)
    ], cwd=str(repo_root), check=True)
    
    # Run B
    subprocess.run([
        "python", "scripts/audit_opening_state_causal_replay.py",
        "--universe", str(universe),
        "--partition", str(partition),
        "--manifest", str(manifest),
        "--outdir", str(run_b)
    ], cwd=str(repo_root), check=True)
    
    subprocess.run([
        "python", "scripts/audit_threshold_oracle.py",
        "--universe", str(universe),
        "--partition", str(partition),
        "--manifest", str(manifest),
        "--outdir", str(run_b)
    ], cwd=str(repo_root), check=True)
    
    hashes_a = extract_portable_hashes(run_a)
    hashes_b = extract_portable_hashes(run_b)
    
    determinism = {
        "run_a_hashes": hashes_a,
        "run_b_hashes": hashes_b,
        "match": hashes_a == hashes_b
    }
    
    with open(docs_dir / "candidate_replay_determinism.json", "w") as f:
        json.dump(determinism, f, indent=2)
        
    print(f"Determinism Check: {'PASS' if determinism['match'] else 'FAIL'}")

if __name__ == "__main__":
    main()
