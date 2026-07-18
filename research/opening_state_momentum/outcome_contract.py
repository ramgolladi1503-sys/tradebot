import json
import hashlib

OUTCOME_ID = "OPENING_STATE_MOMENTUM_FIXED_30M_OUTCOME_V1"
OUTCOME_VERSION = "1.0.0"

CONTRACT_PARAMS = {
    "outcome_id": OUTCOME_ID,
    "outcome_version": OUTCOME_VERSION,
    "instrument": "NIFTY",
    "entry_bar_time": "14:45:00",
    "exit_bar_time": "15:15:00",
    "entry_price_field": "open",
    "exit_price_field": "open",
    "holding_period_minutes": 30,
    "friction_bps_tiers": [0, 2, 5, 10]
}

VALID_STATUSES = [
    "OUTCOME_LABELLED",
    "SOURCE_RESOLUTION_FAILED",
    "ENTRY_BAR_MISSING",
    "EXIT_BAR_MISSING",
    "DUPLICATE_TIMESTAMPS",
    "ENTRY_BAR_MULTIPLE_MATCHES",
    "EXIT_BAR_MULTIPLE_MATCHES",
    "ENTRY_PRICE_INVALID",
    "EXIT_PRICE_INVALID",
    "ENTRY_EXIT_ORDER_INVALID",
    "INVALID_HOLDING_PERIOD",
    "UNPARSABLE_TIMESTAMPS"
]

def get_outcome_contract_hash() -> str:
    serialized = json.dumps(CONTRACT_PARAMS, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
