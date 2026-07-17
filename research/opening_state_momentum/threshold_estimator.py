import numpy as np
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple

class InsufficientHistoryError(Exception):
    pass

def calculate_threshold(training_returns: List[float], percentile: int = 80) -> Tuple[float, Dict[str, Any]]:
    # Requires at least 60 sessions
    if len(training_returns) < 60:
        raise InsufficientHistoryError(f"INSUFFICIENT_PRIOR_HISTORY: Need at least 60 training sessions, got {len(training_returns)}")
        
    # Use deterministic linear interpolation (percentile method)
    # np.percentile standard is linear, but let's be explicit
    val = float(np.percentile(np.abs(training_returns), percentile, method="linear"))
    
    # Calculate hash of returns for audit
    returns_serialized = json.dumps(sorted(training_returns))
    returns_hash = hashlib.sha256(returns_serialized.encode("utf-8")).hexdigest()
    
    metadata = {
        "percentile": percentile,
        "estimator_version": "1.0.0",
        "sample_size": len(training_returns),
        "returns_hash": returns_hash,
        "computed_value": val
    }
    
    serialized_meta = json.dumps(metadata, sort_keys=True)
    metadata["threshold_hash"] = hashlib.sha256(serialized_meta.encode("utf-8")).hexdigest()
    
    return val, metadata
