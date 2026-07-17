import json
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
import sys

def main():
    repo_root = Path(__file__).parent.parent
    reviews_dir = repo_root / "docs" / "agent_reviews" / "opening_state_momentum"
    
    with open(reviews_dir / "development_outcome_labels.json") as f:
        outcomes = json.load(f)
        
    data_dir = repo_root / "data" / "combined-upstox-20260716"
    
    comparisons = []
    mismatches = 0
    
    longs_checked = 0
    shorts_checked = 0
    
    for out in outcomes:
        if out["status"] != "OUTCOME_LABELLED":
            continue
            
        if out["direction"] > 0 and longs_checked >= 2:
            pass
        elif out["direction"] < 0 and shorts_checked >= 2:
            pass
        else:
            date = out["session_date"]
            rel_path = out["source_logical_identity"]
            pf = pq.ParquetFile(data_dir / rel_path)
            
            # Using independent loading logic
            df = pf.read(columns=["timestamp", "open"]).to_pandas()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata")
            
            entry_time = pd.Timestamp(f"{date} 14:45:00").tz_localize("Asia/Kolkata")
            exit_time = pd.Timestamp(f"{date} 15:15:00").tz_localize("Asia/Kolkata")
            
            entry_row = df[df["timestamp"] == entry_time]
            exit_row = df[df["timestamp"] == exit_time]
            
            if entry_row.empty or exit_row.empty:
                mismatches += 1
                continue
                
            entry_open = float(entry_row["open"].iloc[0])
            exit_open = float(exit_row["open"].iloc[0])
            
            if out["direction"] > 0:
                gross = (exit_open / entry_open) - 1.0
                longs_checked += 1
            else:
                gross = (entry_open / exit_open) - 1.0
                shorts_checked += 1
                
            net_0 = gross
            net_2 = gross - 0.0004
            net_5 = gross - 0.0010
            net_10 = gross - 0.0020
            
            comp = {
                "session_date": date,
                "direction": out["direction"],
                "oracle_entry_price": entry_open,
                "label_entry_price": out["entry_price"],
                "oracle_exit_price": exit_open,
                "label_exit_price": out["exit_price"],
                "oracle_gross": round(gross, 6),
                "label_gross": out["gross_return"],
                "oracle_net_10bps": round(net_10, 6),
                "label_net_10bps": out["net_return_10bps"]
            }
            
            if (abs(comp["oracle_entry_price"] - comp["label_entry_price"]) > 1e-5 or 
                abs(comp["oracle_exit_price"] - comp["label_exit_price"]) > 1e-5 or
                abs(comp["oracle_gross"] - comp["label_gross"]) > 1e-5 or
                abs(comp["oracle_net_10bps"] - comp["label_net_10bps"]) > 1e-5):
                mismatches += 1
                
            comparisons.append(comp)
            
    with open(reviews_dir / "outcome_oracle_comparison.json", "w") as f:
        json.dump({"mismatches": mismatches, "comparisons": comparisons}, f, indent=2)

if __name__ == "__main__":
    main()
