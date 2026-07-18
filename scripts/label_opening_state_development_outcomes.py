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
from research.opening_state_momentum.outcome_contract import VALID_STATUSES

reviews_dir = os.path.join(repo_root, "docs", "agent_reviews", "opening_state_momentum")
partition_path = os.path.join(reviews_dir, "research_partition.json")
decisions_path = os.path.join(reviews_dir, "candidate_decisions.json")
manifest_path = os.path.join(reviews_dir, "source_manifest.json")

def main():
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
            "source_logical_identity": logical_id,
            "source_provenance_status": "CANDIDATE_SOURCE_NOT_RECORDED"
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
        
    with open(os.path.join(out_dir, "development_outcome_labels.json"), "w") as f:
        json.dump(outcomes, f, indent=2)
        
    recon = {
        "accepted_development_candidates": len(decisions.accepted_development_candidates),
        "rejected_development_candidates": len(decisions.rejected_decision_dates)
    }
    
    total_failures = 0
    for st in VALID_STATUSES:
        key = "total_" + st.lower()
        cnt = sum(1 for x in outcomes if x["status"] == st)
        recon[key] = cnt
        if st != "OUTCOME_LABELLED":
            total_failures += cnt
            
    recon["unexplained_count"] = recon["accepted_development_candidates"] - (recon["total_outcome_labelled"] + total_failures)
    
    with open(os.path.join(out_dir, "development_outcome_reconciliation.json"), "w") as f:
        json.dump(recon, f, indent=2)
        
    # Generate fingerprint aggregate
    fingerprints = sorted([x["outcome_fingerprint"] for x in outcomes])
    with open(os.path.join(out_dir, "outcome_fingerprint_aggregate.json"), "w") as f:
        json.dump(fingerprints, f, indent=2)
        
    # Generate evidence summary
    summary = {
        "total_records": len(outcomes),
        "success_rate": recon["total_outcome_labelled"] / max(1, len(outcomes)),
        "contract_hash": out_contract_hash
    }
    with open(os.path.join(out_dir, "outcome_evidence_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()
