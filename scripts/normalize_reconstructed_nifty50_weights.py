import pandas as pd
import json
from pathlib import Path
import hashlib
from datetime import timedelta

def normalize():
    print("Normalizing proxy weights...")
    base_dir = Path("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/reconstructed_nifty50_weights")
    raw_csv = base_dir / "raw/weights.csv"
    out_dir = base_dir / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(raw_csv, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
        
    df = pd.read_csv(raw_csv)
    df['DATE'] = pd.to_datetime(df['DATE'])
    df = df.sort_values('DATE')
    dates = df['DATE'].unique()
    
    normalized_rows = []
    
    for i, date in enumerate(dates):
        current_date = pd.to_datetime(date)
        if i < len(dates) - 1:
            next_date = pd.to_datetime(dates[i+1])
            effective_to = (next_date - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            effective_to = '2099-12-31'
            
        row = df[df['DATE'] == date].iloc[0]
        
        sum_weights = 0
        snapshot_rows = []
        for col in df.columns:
            if col == 'DATE': continue
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
                "commercial_use_allowed": False
            })
            
        if not (0.9999 <= sum_weights <= 1.0001):
            print(f"Warning: sum weights out of bounds on {date}: {sum_weights}")
            # The dataset may have up to 1.001 tolerance, adjust logic if necessary
            
        normalized_rows.extend(snapshot_rows)
        
    out_df = pd.DataFrame(normalized_rows)
    out_csv = out_dir / "point_in_time_weights_proxy.csv"
    out_df.to_csv(out_csv, index=False)
    
    # Generate mapping
    symbols = out_df['constituent_symbol'].unique().tolist()
    ticker_mapping = {s: s for s in symbols} # preserves historical
    with open(out_dir / "ticker_mapping.json", "w") as f:
        json.dump(ticker_mapping, f, indent=2)
        
    with open(out_dir / "source_manifest.json", "w") as f:
        json.dump({"source_authority": "COMMUNITY_RECONSTRUCTION", "commercial_use_allowed": False}, f)
        
    with open(out_dir / "snapshot_conservation.json", "w") as f:
        json.dump({"total_snapshots": len(dates), "total_rows": len(out_df)}, f)

if __name__ == "__main__":
    normalize()
