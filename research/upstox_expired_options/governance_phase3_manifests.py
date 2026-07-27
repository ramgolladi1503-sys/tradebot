import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import uuid

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
MANIFESTS_DIR = EVIDENCE_ROOT / "manifests"

def main():
    print("Running Phase 3 Manifest Reconstruction...")
    
    contract_inv_path = MANIFESTS_DIR / "contract_inventory.parquet"
    if not contract_inv_path.exists():
        print("Missing contract_inventory.parquet")
        return
        
    df_contracts = pd.read_parquet(contract_inv_path)
    
    requests = []
    failures = []
    
    for idx, row in df_contracts.iterrows():
        # reconstruct a plausible request record
        req_id = f"reconstructed-{uuid.uuid4().hex[:8]}"
        
        status = "UNKNOWN"
        http_status = None
        reconstruction_conf = "DERIVED_HIGH"
        
        if row['final_status'] == "VALID_COMPLETE" or row['final_status'] == "VALID_1M_ONLY":
            status = "SUCCESS_POPULATED"
            http_status = 200
        elif row['final_status'] == "AUTHORITATIVE_NO_DATA":
            status = "SUCCESS_EMPTY"
            http_status = 200
        elif row['final_status'] == "MISSING_RAW":
            status = "NOT_ATTEMPTED"
            http_status = None
        else:
            status = "UNKNOWN"
            
        req = {
            "request_id": req_id,
            "endpoint_class": "historical_candle",
            "safe_parameters": {
                "instrument_key": row.get('expired_instrument_key'),
                "interval": "1minute",
                "to_date": row.get('request_to_date'),
                "from_date": row.get('request_from_date')
            },
            "expiry": row.get('expiry'),
            "option_type": row.get('option_type'),
            "strike": row.get('strike'),
            "trading_symbol": row.get('trading_symbol'),
            "expired_instrument_key": row.get('expired_instrument_key'),
            "requested_at": None, # Unknowable exactly, leaving null or derived
            "completed_at": None,
            "attempt_count": 1,
            "http_status": http_status,
            "upstox_error_code": None,
            "raw_json_path": row.get('raw_candle_path'),
            "raw_sha256": row.get('raw_candle_sha256'),
            "normalized_1m_path": row.get('normalized_1m_path'),
            "normalized_1m_row_count": row.get('one_minute_row_count'),
            "normalized_5m_path": row.get('normalized_5m_path'),
            "normalized_5m_row_count": row.get('five_minute_row_count'),
            "status": status,
            "reconstruction_source": "contract_inventory",
            "reconstruction_confidence": reconstruction_conf
        }
        
        requests.append(req)
        
        if status not in ["SUCCESS_POPULATED", "NOT_ATTEMPTED"] or row['final_status'] in ["QUARANTINED", "DATA_QUALITY_FAILED", "AUTHORITATIVE_NO_DATA"]:
            failures.append(req)

    with open(MANIFESTS_DIR / "request_manifest.jsonl", "w") as f:
        for r in requests:
            f.write(json.dumps(r) + "\n")
            
    with open(MANIFESTS_DIR / "failure_manifest.jsonl", "w") as f:
        for r in failures:
            f.write(json.dumps(r) + "\n")
            
    print(f"Generated request_manifest.jsonl ({len(requests)} rows) and failure_manifest.jsonl ({len(failures)} rows).")

if __name__ == "__main__":
    main()
