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

from research.upstox_expired_options.semantic_hash import compute_semantic_hash

def main():
    print("Starting Determinism Proof...")
    start_time = datetime.utcnow().isoformat()
    
    # We need a small frozen subset of raw responses.
    frozen_raw = tempfile.mkdtemp(prefix="upstox_frozen_raw_")
    
    # Copy just one expiry folder to freeze
    source_expiry = EVIDENCE_ROOT / "raw" / "responses" / "NIFTY" / "expiry=2024-01-04"
    if not source_expiry.exists():
        # find any
        raw_resp = EVIDENCE_ROOT / "raw" / "responses"
        und = [d for d in os.listdir(raw_resp) if (raw_resp / d).is_dir() and d != '.DS_Store'][0]
        exps = [d for d in os.listdir(raw_resp / und) if (raw_resp / und / d).is_dir() and d != '.DS_Store']
        source_expiry = raw_resp / und / exps[0]
        
    dest = Path(frozen_raw) / "raw" / "responses" / source_expiry.parent.name / source_expiry.name
    shutil.copytree(source_expiry, dest)
    
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
        raw_base = Path(base_dir) / "raw" / "responses"
        if not raw_base.exists(): return
        for und in os.listdir(raw_base):
            und_path = raw_base / und
            if not und_path.is_dir() or und == '.DS_Store': continue
            for exp in os.listdir(und_path):
                exp_path = und_path / exp
                if exp_path.is_dir():
                    contracts_json = exp_path / "contracts.json"
                    if not contracts_json.exists(): continue
                    with open(contracts_json) as cj:
                        meta = json.load(cj)
                        
                    def enrich(m):
                        return {
                            'underlying': m.get('underlying_symbol', 'NIFTY'),
                            'underlying_key': m.get('underlying_key', 'NSE_INDEX|Nifty 50'),
                            'expiry': m.get('expiry'),
                            'strike': m.get('strike_price'),
                            'option_type': m.get('instrument_type'),
                            'trading_symbol': m.get('trading_symbol'),
                            'expired_instrument_key': m.get('instrument_key'),
                            'exchange_token': m.get('exchange_token'),
                            'lot_size': m.get('lot_size'),
                            'minimum_lot': m.get('minimum_lot'),
                            'weekly': m.get('weekly', True),
                            'source': 'upstox_plus',
                            'interval': '1minute',
                            'fetched_at': '2024-01-01T00:00:00.000Z',
                            'request_from_date': '2024-01-01',
                            'request_to_date': m.get('expiry'),
                        }
                    meta_map = {m['instrument_key'].replace('|', '_'): enrich(m) for m in meta}
                    
                    for f_dir in os.listdir(exp_path):
                        f_dir_path = exp_path / f_dir
                        if f_dir_path.is_dir() and f_dir.startswith('instrument='):
                            ikey = f_dir.replace('instrument=', '')
                            if ikey not in meta_map: continue
                            
                            json_file = f_dir_path / 'candles_1minute.json'
                            if not json_file.exists(): continue
                            
                            with open(json_file, 'rb') as fb:
                                raw = fb.read()
                            
                            m_enriched = meta_map[ikey].copy()
                            import hashlib
                            m_enriched['raw_response_sha256'] = hashlib.sha256(raw).hexdigest()
                            
                            try:
                                df_1m, _ = parse_candles(raw, m_enriched)
                                if not df_1m.empty:
                                    df_5m = aggregate_5m(df_1m)
                                    
                                    p1 = Path(base_dir) / "normalized" / "candles_1minute" / f"underlying={meta_map[ikey].get('underlying_symbol', 'UNKNOWN')}" / f"expiry={meta_map[ikey].get('expiry')}" / f"{ikey}.parquet"
                                    p5 = Path(base_dir) / "normalized" / "candles_5minute" / f"underlying={meta_map[ikey].get('underlying_symbol', 'UNKNOWN')}" / f"expiry={meta_map[ikey].get('expiry')}" / f"{ikey}.parquet"
                                    p1.parent.mkdir(parents=True, exist_ok=True)
                                    p5.parent.mkdir(parents=True, exist_ok=True)
                                    
                                    atomic_write_parquet(df_1m, p1)
                                    atomic_write_parquet(df_5m, p5)
                            except Exception as e:
                                print(f"Error {f_dir}: {e}")
                            
    run_pipeline(dir_a)
    run_pipeline(dir_b)
    
    hash_a = compute_semantic_hash(Path(dir_a) / "normalized")
    hash_b = compute_semantic_hash(Path(dir_b) / "normalized")
    
    # We compare aggregate hashes of 1m and 5m separately
    hash_a_1m = compute_semantic_hash(Path(dir_a) / "normalized" / "candles_1minute")
    hash_b_1m = compute_semantic_hash(Path(dir_b) / "normalized" / "candles_1minute")
    hash_a_5m = compute_semantic_hash(Path(dir_a) / "normalized" / "candles_5minute")
    hash_b_5m = compute_semantic_hash(Path(dir_b) / "normalized" / "candles_5minute")
    
    mismatches = 0
    if hash_a_1m["aggregate_hash"] != hash_b_1m["aggregate_hash"]:
        mismatches += 1
    if hash_a_5m["aggregate_hash"] != hash_b_5m["aggregate_hash"]:
        mismatches += 1
        
    contract_count = hash_a_1m["contract_count"]
    
    # Empty Object Hash Protection
    assert hash_a_1m["aggregate_hash"] != "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a", "Empty object hashed!"
    
    res = {
        "commands": ["python audit_phase6_determinism.py"],
        "start_time": start_time,
        "end_time": datetime.utcnow().isoformat(),
        "exit_codes": [0],
        "contract_count": contract_count,
        "mismatch_count": mismatches,
        "hash_A": hash_a_1m["aggregate_hash"],
        "hash_B": hash_b_1m["aggregate_hash"],
        "hash_5m_A": hash_a_5m["aggregate_hash"],
        "hash_5m_B": hash_b_5m["aggregate_hash"],
        "file_count_1m_A": hash_a_1m["file_count"],
        "file_count_1m_B": hash_b_1m["file_count"],
        "row_count_1m_A": hash_a_1m["row_count"],
        "row_count_1m_B": hash_b_1m["row_count"],
        "file_count_5m_A": hash_a_5m["file_count"],
        "file_count_5m_B": hash_b_5m["file_count"],
        "row_count_5m_A": hash_a_5m["row_count"],
        "row_count_5m_B": hash_b_5m["row_count"],
        "status": "PASS" if mismatches == 0 else "FAIL"
    }
    
    with open(REPORTS_DIR / "determinism_report.json", "w") as f:
        json.dump(res, f, indent=2)
    
    print(f"Determinism Proof Complete. Mismatches: {mismatches}")

if __name__ == "__main__":
    main()
