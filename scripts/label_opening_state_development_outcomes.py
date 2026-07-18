import os
import sys
import json
import pandas as pd
from typing import Dict, Any

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

from research.opening_state_momentum.partition_authority import PartitionAuthority
from research.opening_state_momentum.decision_authority import DecisionAuthority
from research.opening_state_momentum.source_authority import SourceAuthority
from research.opening_state_momentum.outcome_labeler import label_outcome
from research.opening_state_momentum.outcome_fingerprints import compute_outcome_fingerprint

reviews_dir = os.path.join(repo_root, "docs", "agent_reviews", "opening_state_momentum")
partition_path = os.path.join(reviews_dir, "research_partition.json")
decisions_path = os.path.join(reviews_dir, "candidate_decisions.json")
manifest_path = os.path.join(reviews_dir, "source_manifest.json")

def main():
    # If the user sets different paths (e.g. for determinism test)
    p_path = os.environ.get("PARTITION_PATH", partition_path)
    d_path = os.environ.get("DECISIONS_PATH", decisions_path)
    m_path = os.environ.get("MANIFEST_PATH", manifest_path)
    out_dir = os.environ.get("OUTCOME_DIR", reviews_dir)
    
    partition = PartitionAuthority.load(p_path)
    decisions = DecisionAuthority.load(d_path, partition)
    source = SourceAuthority.load(m_path, repo_root)
    
    with open(os.path.join(reviews_dir, "strategy_contract.json")) as f:
        content = f.read(); strat_contract = json.loads(content); strat_contract_hash = __import__("hashlib").sha256(content.encode("utf-8")).hexdigest()
    with open(os.path.join(reviews_dir, "outcome_contract.json")) as f:
        content = f.read(); out_contract = json.loads(content); out_contract_hash = __import__("hashlib").sha256(content.encode("utf-8")).hexdigest()
        
    outcomes = []
    
    for cand in decisions.accepted_development_candidates:
        logical_id = f"NIFTY_{cand.session_date.replace('-', '')}"
        
        record = {
            "strategy_id": strat_contract["strategy_id"],
            "strategy_version": strat_contract["strategy_version"],
            "strategy_contract_hash": strat_contract_hash,
            "outcome_contract_id": out_contract["outcome_id"],
            "outcome_contract_version": out_contract["outcome_version"],
            "outcome_contract_hash": out_contract_hash,
            "source_manifest_hash": source.manifest_hash,
            "dataset_group_hash": cand.dataset_group_hash,
            "partition_hash": partition.partition_hash,
            "session_date": cand.session_date,
            "direction": cand.direction,
            "candidate_fingerprint": cand.fingerprint,
            "feature_cutoff_timestamp": cand.feature_cutoff_timestamp,
            "source_logical_identity": logical_id
        }
        
        try:
            full_path = source.resolve_source(logical_id)
            df = pd.read_parquet(full_path)
        except Exception as e:
            record["status"] = "SOURCE_RESOLUTION_FAILED"
            record["outcome_fingerprint"] = compute_outcome_fingerprint(record)
            outcomes.append(record)
            continue
            
        result = label_outcome(df, cand.direction, cand.session_date)
        record.update(result)
        
        record["outcome_fingerprint"] = compute_outcome_fingerprint(record)
        outcomes.append(record)
        
    # Write outcomes
    with open(os.path.join(out_dir, "development_outcome_labels.json"), "w") as f:
        json.dump(outcomes, f, indent=2)
        
    # Reconciliation
    recon = {
        "accepted_development_candidates": len(decisions.accepted_development_candidates),
        "rejected_development_candidates": len(decisions.rejected_decision_dates),
        "total_labelled_outcomes": sum(1 for x in outcomes if x["status"] == "OUTCOME_LABELLED"),
        "total_source_resolution_failed": sum(1 for x in outcomes if x["status"] == "SOURCE_RESOLUTION_FAILED"),
        "total_entry_bar_missing": sum(1 for x in outcomes if x["status"] == "ENTRY_BAR_MISSING"),
        "total_exit_bar_missing": sum(1 for x in outcomes if x["status"] == "EXIT_BAR_MISSING"),
        "total_entry_price_invalid": sum(1 for x in outcomes if x["status"] == "ENTRY_PRICE_INVALID"),
        "total_exit_price_invalid": sum(1 for x in outcomes if x["status"] == "EXIT_PRICE_INVALID"),
        "total_entry_exit_order_invalid": sum(1 for x in outcomes if x["status"] == "ENTRY_EXIT_ORDER_INVALID"),
        "total_invalid_holding_period": sum(1 for x in outcomes if x["status"] == "INVALID_HOLDING_PERIOD"),
    }
    
    total_failures = (
        recon["total_source_resolution_failed"] +
        recon["total_entry_bar_missing"] +
        recon["total_exit_bar_missing"] +
        recon["total_entry_price_invalid"] +
        recon["total_exit_price_invalid"] +
        recon["total_entry_exit_order_invalid"] +
        recon["total_invalid_holding_period"]
    )
    recon["unexplained_count"] = recon["accepted_development_candidates"] - (recon["total_labelled_outcomes"] + total_failures)
    
    with open(os.path.join(out_dir, "development_outcome_reconciliation.json"), "w") as f:
        json.dump(recon, f, indent=2)

if __name__ == "__main__":
    main()
