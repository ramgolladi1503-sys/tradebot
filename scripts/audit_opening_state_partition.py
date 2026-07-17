import json
import argparse
from pathlib import Path

# Adjust Python path if needed or just copy the logic
def partition_sessions(session_dates):
    import hashlib
    sorted_dates = sorted(session_dates)
    total = len(sorted_dates)
    if total == 0:
        return [], [], {}
        
    dev_count = int(total * 0.8)
    development = sorted_dates[:dev_count]
    holdout = sorted_dates[dev_count:]
    
    ordered_hash = hashlib.sha256(json.dumps(sorted_dates).encode("utf-8")).hexdigest()
    dev_hash = hashlib.sha256(json.dumps(development).encode("utf-8")).hexdigest()
    holdout_hash = hashlib.sha256(json.dumps(holdout).encode("utf-8")).hexdigest()
    
    partition_metadata = {
        "ordered_session_list_hash": ordered_hash,
        "development_session_list_hash": dev_hash,
        "holdout_session_list_hash": holdout_hash,
        "total_sessions": total,
        "dev_sessions_count": len(development),
        "holdout_sessions_count": len(holdout),
    }
    
    return development, holdout, partition_metadata

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    
    with open(args.audit) as f:
        audit = json.load(f)
        
    eligible_dates = audit["eligible_dates"]
    
    dev, holdout, meta = partition_sessions(eligible_dates)
    
    partition_file = {
        "metadata": meta,
        "development": dev,
        "holdout": holdout
    }
    
    out_path = Path(args.outdir) / "research_partition.json"
    with open(out_path, "w") as f:
        json.dump(partition_file, f, indent=2)
        
    print(f"Partition written to {out_path}")
    print(f"Total: {meta['total_sessions']}, Dev: {meta['dev_sessions_count']}, Holdout: {meta['holdout_sessions_count']}")

if __name__ == "__main__":
    main()
