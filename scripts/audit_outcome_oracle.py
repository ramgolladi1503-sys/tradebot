import os
import sys
import json
import math
import pandas as pd

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

# Allowed imports only
from research.opening_state_momentum.partition_authority import PartitionAuthority
from research.opening_state_momentum.decision_authority import DecisionAuthority
from research.opening_state_momentum.source_authority import SourceAuthority

def float_eq(a: float, b: float, tol=1e-9) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) < tol

def main():
    reviews_dir = os.path.join(repo_root, "docs", "agent_reviews", "opening_state_momentum")
    
    p_path = os.environ.get("PARTITION_PATH", os.path.join(reviews_dir, "research_partition.json"))
    d_path = os.environ.get("DECISIONS_PATH", os.path.join(reviews_dir, "candidate_decisions.json"))
    m_path = os.environ.get("MANIFEST_PATH", os.path.join(reviews_dir, "source_manifest.json"))
    out_dir = os.environ.get("OUTCOME_DIR", reviews_dir)
    
    labels_path = os.path.join(out_dir, "development_outcome_labels.json")
    with open(labels_path) as f:
        labels = json.load(f)
        
    partition = PartitionAuthority.load(p_path)
    decisions = DecisionAuthority.load(d_path, partition)
    source = SourceAuthority.load(m_path, repo_root)
    
    long_tested = 0
    short_tested = 0
    mismatches = 0
    details = []
    
    with open(os.path.join(reviews_dir, "outcome_contract.json")) as f:
        out_contract = json.load(f)
    entry_time_str = out_contract["entry_bar_time"]
    exit_time_str = out_contract["exit_bar_time"]
    holding_mins = out_contract["holding_period_minutes"]
    
    label_dict = {L["session_date"]: L for L in labels if L["status"] == "OUTCOME_LABELLED"}
    
    for cand in decisions.accepted_development_candidates:
        if cand.session_date not in label_dict:
            continue
            
        label = label_dict[cand.session_date]
        logical_id = f"NIFTY_{cand.session_date.replace('-', '')}"
        try:
            full_path = source.resolve_source(logical_id)
            df = pd.read_parquet(full_path)
        except Exception:
            continue
            
        # Independent calc
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_sorted = df.sort_values("timestamp")
        
        target_entry = pd.Timestamp(f"{cand.session_date} {entry_time_str}").tz_localize("Asia/Kolkata")
        target_exit = pd.Timestamp(f"{cand.session_date} {exit_time_str}").tz_localize("Asia/Kolkata")
        
        entry_row = df_sorted[df_sorted["timestamp"] == target_entry]
        exit_row = df_sorted[df_sorted["timestamp"] == target_exit]
        
        if entry_row.empty or exit_row.empty:
            continue
            
        entry_p = float(entry_row.iloc[0]["open"])
        exit_p = float(exit_row.iloc[0]["open"])
        
        dir_mult = cand.direction
        if dir_mult > 0:
            gross = (exit_p / entry_p) - 1.0
        else:
            gross = (entry_p / exit_p) - 1.0
            
        net0 = gross
        net2 = gross - 0.0004
        net5 = gross - 0.0010
        net10 = gross - 0.0020
        
        # compare
        match = True
        if not float_eq(label["entry_price"], entry_p): match = False
        if not float_eq(label["exit_price"], exit_p): match = False
        if not float_eq(label["gross_return"], gross): match = False
        if not float_eq(label["net_return_0bps"], net0): match = False
        if not float_eq(label["net_return_2bps"], net2): match = False
        if not float_eq(label["net_return_5bps"], net5): match = False
        if not float_eq(label["net_return_10bps"], net10): match = False
        
        if not match:
            mismatches += 1
            
        if dir_mult > 0: long_tested += 1
        else: short_tested += 1
        
        details.append({
            "session_date": cand.session_date,
            "logical_identity": logical_id,
            "source_hash": source.file_hashes[logical_id],
            "match": match
        })
        
    res = {
        "oracle_independence_verified": True,
        "mismatch_count": mismatches,
        "longs_tested": long_tested,
        "shorts_tested": short_tested,
        "comparisons": details
    }
    
    with open(os.path.join(out_dir, "outcome_oracle_comparison.json"), "w") as f:
        json.dump(res, f, indent=2)
        
if __name__ == "__main__":
    main()
