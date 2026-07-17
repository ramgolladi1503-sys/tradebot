import json
import hashlib
from typing import Dict, Any

def compute_outcome_fingerprint(outcome: Dict[str, Any]) -> str:
    keys = [
        "strategy_id",
        "outcome_id",
        "session_date",
        "direction",
        "candidate_fingerprint",
        "feature_cutoff",
        "entry_timestamp",
        "entry_price",
        "exit_timestamp",
        "exit_price",
        "holding_minutes",
        "gross_return",
        "net_return_0bps",
        "net_return_2bps",
        "net_return_5bps",
        "net_return_10bps",
        "status"
    ]
    
    stable_dict = {}
    for k in keys:
        if k in outcome:
            val = outcome[k]
            if isinstance(val, float):
                stable_dict[k] = round(val, 6)
            else:
                stable_dict[k] = val
                
    serialized = json.dumps(stable_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
