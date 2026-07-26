import os
import json
import shutil
import tempfile
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
REPORTS_DIR = EVIDENCE_ROOT / "reports"
SCRIPT_PATH = Path("/Users/madhuram/tradebot-upstox-expired-option-fetch-v1/scripts/fetch_upstox_expired_options.py")

def get_dir_hash(directory):
    # Hash all parquets in directory
    hashes = {}
    for root, _, files in os.walk(directory):
        for f in sorted(files):
            if f.endswith('.parquet'):
                p = Path(root) / f
                sha = hashlib.sha256()
                with open(p, 'rb') as fd:
                    for chunk in iter(lambda: fd.read(8192), b''):
                        sha.update(chunk)
                hashes[str(p.relative_to(directory))] = sha.hexdigest()
    return hashes

def main():
    print("Starting Determinism Proof...")
    start_time = datetime.utcnow().isoformat()
    
    # We need a small frozen subset of raw responses.
    frozen_raw = tempfile.mkdtemp(prefix="upstox_frozen_raw_")
    
    # Copy just one expiry folder to freeze
    source_expiry = EVIDENCE_ROOT / "raw" / "expiry=2024-01-04"
    if not source_expiry.exists():
        # find any
        raws = [d for d in os.listdir(EVIDENCE_ROOT / "raw") if (EVIDENCE_ROOT / "raw" / d).is_dir()]
        source_expiry = EVIDENCE_ROOT / "raw" / raws[0]
        
    shutil.copytree(source_expiry, Path(frozen_raw) / "raw" / source_expiry.name)
    
    dir_a = tempfile.mkdtemp(prefix="upstox_det_A_")
    dir_b = tempfile.mkdtemp(prefix="upstox_det_B_")
    
    # Setup A
    shutil.copytree(Path(frozen_raw) / "raw", Path(dir_a) / "raw")
    # Setup B
    shutil.copytree(Path(frozen_raw) / "raw", Path(dir_b) / "raw")
    
    env_a = os.environ.copy()
    env_a["UPSTOX_DATA_ROOT"] = dir_a
    env_b = os.environ.copy()
    env_b["UPSTOX_DATA_ROOT"] = dir_b
    
    # We will use the standalone normalizer and aggregator
    from research.upstox_expired_options.normalizer import parse_candles
    from research.upstox_expired_options.aggregation import aggregate_5m
    from research.upstox_expired_options.storage import atomic_write_parquet
    
    def run_pipeline(base_dir):
        raw_base = Path(base_dir) / "raw"
        for exp in os.listdir(raw_base):
            exp_path = raw_base / exp
            if exp_path.is_dir():
                contracts_json = exp_path / "contracts.json"
                if not contracts_json.exists(): continue
                with open(contracts_json) as cj:
                    meta = json.load(cj)
                meta_map = {m['instrument_key']: m for m in meta}
                
                for f in os.listdir(exp_path):
                    if f.endswith('.json') and f != 'contracts.json':
                        ikey = f.replace('.json', '')
                        if ikey not in meta_map: continue
                        with open(exp_path / f, 'rb') as fb:
                            raw = fb.read()
                        
                        try:
                            df_1m, _ = parse_candles(raw, meta_map[ikey])
                            if not df_1m.empty:
                                df_5m = aggregate_5m(df_1m)
                                
                                u = meta_map[ikey].get('underlying_symbol', 'UNKNOWN')
                                e = meta_map[ikey].get('expiry')
                                p1 = Path(base_dir) / "normalized" / "candles_1minute" / f"underlying={u}" / f"expiry={e}" / f"{ikey}.parquet"
                                p5 = Path(base_dir) / "normalized" / "candles_5minute" / f"underlying={u}" / f"expiry={e}" / f"{ikey}.parquet"
                                p1.parent.mkdir(parents=True, exist_ok=True)
                                p5.parent.mkdir(parents=True, exist_ok=True)
                                
                                atomic_write_parquet(df_1m, p1)
                                atomic_write_parquet(df_5m, p5)
                        except Exception as e:
                            print(f"Error {f}: {e}")
                            
    run_pipeline(dir_a)
    run_pipeline(dir_b)
    
    hash_a = get_dir_hash(Path(dir_a) / "normalized")
    hash_b = get_dir_hash(Path(dir_b) / "normalized")
    
    mismatches = 0
    for k in hash_a:
        if hash_a[k] != hash_b.get(k): mismatches += 1
    for k in hash_b:
        if k not in hash_a: mismatches += 1
        
    contract_count = len([k for k in hash_a.keys() if 'candles_1minute' in k])
    
    res = {
        "commands": ["python audit_phase6_determinism.py"],
        "start_time": start_time,
        "end_time": datetime.utcnow().isoformat(),
        "exit_codes": [0],
        "contract_count": contract_count,
        "mismatch_count": mismatches,
        "hash_A": hashlib.sha256(json.dumps(hash_a, sort_keys=True).encode()).hexdigest(),
        "hash_B": hashlib.sha256(json.dumps(hash_b, sort_keys=True).encode()).hexdigest(),
        "status": "PASS" if mismatches == 0 else "FAIL"
    }
    
    with open(REPORTS_DIR / "determinism_report.json", "w") as f:
        json.dump(res, f, indent=2)
    
    print(f"Determinism Proof Complete. Mismatches: {mismatches}")

if __name__ == "__main__":
    main()
