import pandas as pd
from pathlib import Path

def main():
    in_dir = Path("runtime/constituent_lead_lag/normalized")
    dfs = []
    for p in in_dir.glob("*_5m.parquet"):
        dfs.append(pd.read_parquet(p))
    
    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        # Sort by timestamp
        combined = combined.sort_values(["timestamp", "symbol"])
        out_path = in_dir / "all_bars.parquet"
        combined.to_parquet(out_path)
        print(f"Combined {len(dfs)} files into {out_path}")
    else:
        print("No normalized files found")

if __name__ == "__main__":
    main()
