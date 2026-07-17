import json
import hashlib
from typing import Dict, Any

def compute_candidate_fingerprint(candidate: Dict[str, Any]) -> str:
    # Use only stable semantic fields for deterministic hash
    keys = [
        "strategy_id",
        "strategy_version",
        "session_date",
        "primary_instrument",
        "confirmation_instrument",
        "direction",
        "nifty_opening_return",
        "bnifty_opening_return",
        "close_location",
        "decision_close",
        "session_anchor"
    ]
    # Ensure float formatting is stable (round to 6 decimals)
    stable_dict = {}
    for k in keys:
        val = candidate.get(k)
        if isinstance(val, float):
            stable_dict[k] = round(val, 6)
        else:
            stable_dict[k] = val
            
    serialized = json.dumps(stable_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
