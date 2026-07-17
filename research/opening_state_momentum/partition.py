import json
import hashlib
from typing import List, Dict, Any, Tuple

class HoldoutLockedError(Exception):
    pass

def partition_sessions(session_dates: List[str]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    # Sort chronologically to preserve order
    sorted_dates = sorted(session_dates)
    total = len(sorted_dates)
    if total == 0:
        return [], [], {}
        
    dev_count = int(total * 0.8)
    development = sorted_dates[:dev_count]
    holdout = sorted_dates[dev_count:]
    
    # Calculate hashes for freezing the partition
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

class PartitionGuard:
    def __init__(self, holdout_dates: List[str]):
        self.holdout_dates = set(holdout_dates)
        
    def check_access(self, date_val, action: str):
        if hasattr(date_val, "strftime"):
            date_str = date_val.strftime("%Y-%m-%d")
        else:
            date_str = str(date_val)
            # handle pd.Timestamp string format if needed, but strftime covers it
            if " " in date_str:
                date_str = date_str.split(" ")[0]
            
        if date_str in self.holdout_dates and action in ["evaluate_outcome", "calculate_returns", "backtest"]:
            raise HoldoutLockedError(f"HOLDOUT_LOCKED: Accessing holdout session {date_str} for outcome evaluation is prohibited in V1.")
