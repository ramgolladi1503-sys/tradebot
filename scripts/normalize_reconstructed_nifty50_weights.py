import argparse
import pandas as pd
import json
from pathlib import Path
import hashlib
from datetime import timedelta
import sys

def normalize():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dataset", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    
    raw_csv = Path(args.raw_dataset)
    manifest_path = Path(args.source_manifest)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    with open(raw_csv, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
        
    # verify SHA-256 against the manifest
    expected_hash = manifest.get("weights.csv") or manifest.get("sha256_by_file", {}).get("weights.csv")
    if expected_hash and file_hash != expected_hash:
        print(f"Hash mismatch! Expected {expected_hash}, got {file_hash}")
        sys.exit(1)
        
    df = pd.read_csv(raw_csv)
    df['DATE_parsed'] = pd.to_datetime(df['DATE'])
    
    if df['DATE_parsed'].duplicated().any():
        print("Duplicate dates found.")
        sys.exit(1)
        
    df = df.sort_values('DATE_parsed')
    dates = df['DATE_parsed'].tolist()
    date_strs = df['DATE'].tolist()
    
    normalized_rows = []
    
    for i, row in df.iterrows():
        current_date = row['DATE_parsed']
        current_date_str = row['DATE']
        
        idx = dates.index(current_date)
        if idx < len(dates) - 1:
            next_date = dates[idx+1]
            effective_to = (next_date - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            effective_to = '2099-12-31'
            
        sum_weights = 0
        snapshot_rows = []
        for col in df.columns:
            if col in ['DATE', 'DATE_parsed']: continue
            w_pct = row[col]
            if pd.isna(w_pct) or w_pct == 0:
                continue
                
            w_frac = w_pct / 100.0
            sum_weights += w_frac
            
            snapshot_rows.append({
                "index_symbol": "NIFTY",
                "constituent_symbol": col,
                "effective_from": current_date.strftime('%Y-%m-%d'),
                "effective_to": effective_to,
                "weight": w_frac,
                "source_name": "Historical Nifty 50 Constituent Weights (20Y)",
                "source_date": current_date.strftime('%Y-%m-%d'),
                "source_sha256": file_hash,
                "source_authority": "COMMUNITY_RECONSTRUCTION",
                "reconstruction_status": "inferred_or_extrapolated",
                "commercial_use_allowed": False,
                "official_weight_gate_passed": False
            })
            
        if not (0.9990 <= sum_weights <= 1.0010): # Documented tolerance
            print(f"Error: sum weights out of bounds on {current_date_str}: {sum_weights}")
            sys.exit(1)
            
        normalized_rows.extend(snapshot_rows)
        
    out_df = pd.DataFrame(normalized_rows)
    out_csv = out_dir / "point_in_time_weights_proxy.csv"
    out_df.to_csv(out_csv, index=False)
    
    # Generate mapping
    symbols = out_df['constituent_symbol'].unique().tolist()
    ticker_map = pd.DataFrame({"original_ticker": symbols, "mapped_ticker": symbols})
    ticker_map.to_csv(out_dir / "ticker_map.csv", index=False)
        
    with open(out_dir / "source_manifest.json", "w") as f:
        json.dump({"source_authority": "COMMUNITY_RECONSTRUCTION", "commercial_use_allowed": False}, f)
        
    with open(out_dir / "snapshot_conservation.json", "w") as f:
        json.dump({"total_snapshots": len(dates), "total_rows": len(out_df)}, f)
        
    print(f"Normalized proxy weights written to {out_dir}")

if __name__ == "__main__":
    normalize()
