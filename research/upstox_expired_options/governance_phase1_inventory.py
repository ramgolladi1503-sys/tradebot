import os
import json
import hashlib
import pandas as pd
from pathlib import Path
from datetime import datetime

EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")
MANIFESTS_DIR = EVIDENCE_ROOT / "manifests"

def get_sha256(filepath):
    sha = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha.update(chunk)
    return sha.hexdigest()

def classify_file(rel_path):
    p = str(rel_path)
    if p.startswith("raw/responses/") and p.endswith("/contracts.json"):
        return "RAW_CONTRACT_INVENTORY"
    if p.startswith("raw/responses/") and p.endswith("candles_1minute.json"):
        return "RAW_CANDLE_RESPONSE"
    if p.startswith("raw/") and p.endswith(".sha256"):
        return "CHECKSUM_SIDECAR"
    if p == "raw/expiries.json":
        return "RAW_EXPIRY_INVENTORY"
    if p.startswith("normalized/candles_1minute/") and p.endswith(".parquet"):
        return "NORMALIZED_1MIN"
    if p.startswith("normalized/candles_5minute/") and p.endswith(".parquet"):
        return "NORMALIZED_5MIN"
    if p.startswith("manifests/") and p.endswith((".json", ".jsonl", ".parquet")):
        return "MANIFEST"
    if p.startswith("reports/") and p.endswith((".md", ".json", ".parquet")):
        return "REPORT"
    if p.startswith("quarantine/"):
        return "QUARANTINE"
    return "UNKNOWN"

def extract_metadata_from_path(rel_path):
    parts = str(rel_path).split('/')
    expiry = None
    option_type = None
    strike = None
    inst_key = None
    for part in parts:
        if part.startswith("expiry="):
            expiry = part.split("=")[1]
        elif part.startswith("option_type="):
            option_type = part.split("=")[1]
        elif part.startswith("strike="):
            strike = part.split("=")[1]
        elif part.startswith("instrument="):
            # upstox raw response format: instrument=NSE_FO_... 
            # We don't have strike/option_type directly in path for raw responses!
            # It must be looked up from contracts.json
            inst_key = part.split("=")[1]
            
    return expiry, option_type, strike, inst_key

def process_file(filepath, rel_path, artifact_class):
    size_bytes = os.path.getsize(filepath)
    sha256 = get_sha256(filepath)
    expiry, option_type, strike, inst_key_from_path = extract_metadata_from_path(rel_path)
    
    row_count = None
    first_ts = None
    last_ts = None
    trading_symbol = None
    inst_key = inst_key_from_path
    status = "UNCLASSIFIED"
    schema_fingerprint = None
    
    if artifact_class in ["NORMALIZED_1MIN", "NORMALIZED_5MIN"]:
        try:
            df = pd.read_parquet(filepath)
            row_count = len(df)
            if row_count > 0:
                first_ts = df['timestamp'].min()
                last_ts = df['timestamp'].max()
                if 'trading_symbol' in df.columns:
                    trading_symbol = df['trading_symbol'].iloc[0]
                if 'expired_instrument_key' in df.columns:
                    inst_key = df['expired_instrument_key'].iloc[0]
                schema_fingerprint = hashlib.sha256(str(sorted(df.columns.tolist())).encode()).hexdigest()
                status = "VALID"
            else:
                status = "EMPTY"
        except Exception:
            status = "MALFORMED"
            
    elif artifact_class == "RAW_CANDLE_RESPONSE":
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            if data.get('status') == 'success' and 'data' in data and 'candles' in data['data']:
                candles = data['data']['candles']
                row_count = len(candles)
                if row_count > 0:
                    first_ts = candles[-1][0] 
                    last_ts = candles[0][0]
                    status = "VALID"
                else:
                    status = "EMPTY"
            else:
                status = "MALFORMED"
        except Exception:
            status = "MALFORMED"

    return {
        "relative_path": str(rel_path),
        "artifact_class": artifact_class,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "expiry": expiry,
        "option_type": option_type,
        "strike": strike,
        "trading_symbol": trading_symbol,
        "expired_instrument_key": inst_key,
        "row_count": row_count,
        "first_timestamp": str(first_ts) if first_ts else None,
        "last_timestamp": str(last_ts) if last_ts else None,
        "schema_fingerprint": schema_fingerprint,
        "status": status
    }

def main():
    print("Running Phase 1 Inventory...")
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    file_hashes = {}
    
    for root, _, files in os.walk(EVIDENCE_ROOT):
        if ".git" in root: continue
        
        for file in files:
            if file == ".DS_Store" or file.startswith("."): continue
            
            filepath = Path(root) / file
            rel_path = filepath.relative_to(EVIDENCE_ROOT)
            
            if str(rel_path) == "manifests/file_hashes.json":
                continue 
                
            artifact_class = classify_file(rel_path)
            record = process_file(filepath, rel_path, artifact_class)
            records.append(record)
            
            semantic = None
            if artifact_class in ["NORMALIZED_1MIN", "NORMALIZED_5MIN"] and record["status"] == "VALID":
                df = pd.read_parquet(filepath)
                semantic = hashlib.sha256(df.sort_values('timestamp').to_csv(index=False).encode()).hexdigest()
                
            file_hashes[str(rel_path)] = {
                "byte_hash": record["sha256"],
                "semantic_hash": semantic
            }
            
    df_inv = pd.DataFrame(records)
    df_inv.to_parquet(MANIFESTS_DIR / "file_inventory.parquet", index=False)
    
    sorted_hashes = {k: file_hashes[k] for k in sorted(file_hashes.keys())}
    out_hashes = {
        "hash_algorithm": "SHA-256",
        "manifest_version": "1.0",
        "files": sorted_hashes
    }
    with open(MANIFESTS_DIR / "file_hashes.json", "w") as f:
        json.dump(out_hashes, f, indent=2)
        
    print(f"Inventoried {len(records)} files.")

if __name__ == "__main__":
    main()
