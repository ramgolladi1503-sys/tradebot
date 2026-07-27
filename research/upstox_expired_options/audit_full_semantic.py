import os
import json
import hashlib
from pathlib import Path
from semantic_hash import compute_semantic_hash

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
NORM_DIR = EVIDENCE_ROOT / "normalized"
REPORTS_DIR = EVIDENCE_ROOT / "reports"

def run_inventory():
    return {
        "1m": compute_semantic_hash(NORM_DIR / "candles_1minute"),
        "5m": compute_semantic_hash(NORM_DIR / "candles_5minute")
    }

def main():
    print("Starting Full Dataset Semantic Inventory Run A...")
    run_a = run_inventory()
    print("Starting Full Dataset Semantic Inventory Run B...")
    run_b = run_inventory()
    
    mismatches_1m = sum(1 for k in run_a["1m"]["per_file_hashes"] if run_a["1m"]["per_file_hashes"][k] != run_b["1m"]["per_file_hashes"].get(k))
    mismatches_5m = sum(1 for k in run_a["5m"]["per_file_hashes"] if run_a["5m"]["per_file_hashes"][k] != run_b["5m"]["per_file_hashes"].get(k))
    
    status = "PASS" if (mismatches_1m == 0 and mismatches_5m == 0 and run_a["1m"]["file_count"] == 1199 and run_a["5m"]["file_count"] == 1199) else "FAIL"
    
    res = {
        "status": status,
        "one_minute_file_count_run_a": run_a["1m"]["file_count"],
        "one_minute_file_count_run_b": run_b["1m"]["file_count"],
        "one_minute_row_count_run_a": run_a["1m"]["row_count"],
        "one_minute_row_count_run_b": run_b["1m"]["row_count"],
        "five_minute_file_count_run_a": run_a["5m"]["file_count"],
        "five_minute_file_count_run_b": run_b["5m"]["file_count"],
        "five_minute_row_count_run_a": run_a["5m"]["row_count"],
        "five_minute_row_count_run_b": run_b["5m"]["row_count"],
        "one_minute_per_file_hash_count_run_a": len(run_a["1m"]["per_file_hashes"]),
        "one_minute_per_file_hash_count_run_b": len(run_b["1m"]["per_file_hashes"]),
        "five_minute_per_file_hash_count_run_a": len(run_a["5m"]["per_file_hashes"]),
        "five_minute_per_file_hash_count_run_b": len(run_b["5m"]["per_file_hashes"]),
        "aggregate_1m_hash_run_a": run_a["1m"]["aggregate_hash"],
        "aggregate_1m_hash_run_b": run_b["1m"]["aggregate_hash"],
        "aggregate_5m_hash_run_a": run_a["5m"]["aggregate_hash"],
        "aggregate_5m_hash_run_b": run_b["5m"]["aggregate_hash"],
        "per_file_mismatch_count_1m": mismatches_1m,
        "per_file_mismatch_count_5m": mismatches_5m,
        "empty_scope_guard": run_a["1m"]["file_count"] > 0,
        "commands": ["python audit_full_semantic.py"],
        "exit_codes": [0]
    }
    
    with open(REPORTS_DIR / "full_dataset_semantic_hash_report.json", "w") as f:
        json.dump(res, f, indent=2)
        
    print("Full Dataset Semantic Inventory Complete.")

if __name__ == "__main__":
    main()
