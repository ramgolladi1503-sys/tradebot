import json
import hashlib
from typing import Dict, Any

STRATEGY_ID = "REGIME_CONDITIONED_OPENING_STATE_MOMENTUM_V1"
STRATEGY_VERSION = "1.0.0"

# Freeze the contract parameters in a dictionary for deterministic hashing
CONTRACT_PARAMS = {
    "strategy_id": STRATEGY_ID,
    "strategy_version": STRATEGY_VERSION,
    "primary_instrument": "NIFTY",
    "confirmation_instrument": "BANKNIFTY",
    "excluded_instruments": ["SENSEX"],
    "opening_window_start_time": "09:15",
    "opening_window_end_time": "09:45",
    "decision_cutoff_time": "14:45",
    "mandatory_exit_time": "15:15",
    "max_holding_period_min": 30,
    "canonical_percentile": 80,
    "close_location_long_threshold": 0.75,
    "close_location_short_threshold": 0.25,
    "retained_move_fraction_threshold": 0.50,
    "anchor_type": "SESSION_TYPICAL_PRICE_MEAN",
    "bar_timestamp_semantics": "bar_open"
}

def get_contract_hash() -> str:
    serialized = json.dumps(CONTRACT_PARAMS, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
