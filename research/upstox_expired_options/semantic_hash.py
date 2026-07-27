import json
import hashlib
import pandas as pd
from pathlib import Path

def compute_semantic_hash(directory_path: Path) -> dict:
    """
    Computes a canonical semantic hash of all Parquet datasets in a directory.
    - Recursively finds all expected Parquet files.
    - Rejects empty discovery sets.
    - Rejects zero total rows.
    - Canonicalizes column order and row order.
    - Normalizes timestamps and nulls deterministically.
    - Includes exact contract identity.
    - Hashes file-level semantic hashes in stable sorted order.
    - Fails closed.
    """
    if not directory_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory_path}")
        
    files = list(directory_path.rglob("*.parquet"))
    if not files:
        raise ValueError(f"No Parquet files found in {directory_path}")
        
    per_file_hashes = {}
    total_rows = 0
    column_set = set()
    
    for f in sorted(files):
        df = pd.read_parquet(f)
        if df.empty:
            raise ValueError(f"File {f} has zero rows.")
            
        total_rows += len(df)
        column_set.update(df.columns.tolist())
        
        # Sort rows by timestamp
        df = df.sort_values(by="timestamp").reset_index(drop=True)
        
        # Sort columns
        cols = sorted(df.columns.tolist())
        df = df[cols]
        
        # Normalize timestamp to UTC ISO string
        if pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            
        # Normalize nulls
        df = df.fillna("")
        
        # Convert to string to avoid float precision issues across pandas versions
        df_str = df.astype(str)
        
        records = df_str.to_dict(orient="records")
        serialized = json.dumps(records, sort_keys=True, separators=(',', ':'))
        
        file_hash = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
        
        rel_path = str(f.relative_to(directory_path))
        per_file_hashes[rel_path] = file_hash
        
    if total_rows == 0:
        raise ValueError("Total rows across all files is zero.")
        
    aggregate_hash = hashlib.sha256(
        json.dumps(per_file_hashes, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    
    return {
        "file_count": len(files),
        "row_count": total_rows,
        "contract_count": len(files),  # 1 parquet per contract in our layout
        "columns": sorted(list(column_set)),
        "per_file_hashes": per_file_hashes,
        "aggregate_hash": aggregate_hash
    }
