import json
import hashlib
from typing import Dict, Any

def compute_outcome_fingerprint(outcome: Dict[str, Any]) -> str:
    keys = [
        "strategy_id",
        "strategy_version",
        "strategy_contract_hash",
        "outcome_contract_id",
        "outcome_contract_version",
        "outcome_contract_hash",
        "source_manifest_hash",
        "dataset_group_hash",
        "partition_hash",
        "session_date",
        "direction",
        "candidate_fingerprint",
        "feature_cutoff_timestamp",
        "entry_timestamp",
        "entry_price",
        "exit_timestamp",
        "exit_price",
        "holding_seconds",
        "gross_return",
        "net_return_0bps",
        "net_return_2bps",
        "net_return_5bps",
        "net_return_10bps",
        "status",
        "source_logical_identity",
        "source_provenance_status"
    ]
    
    stable_dict = {}
    for k in keys:
        if k in outcome:
            val = outcome[k]
            if isinstance(val, float):
                # Deterministic float serialization (scientific notation 10 digits)
                stable_dict[k] = f"{val:.10e}"
            else:
                stable_dict[k] = val
                
    serialized = json.dumps(stable_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
