from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "1.0"
CAMPAIGN_ID = "keltner-hilega-initiation-confirmation-v1"
RESEARCH_CONTRACT_SHA256 = "a372c2083485236348f66594ac7ae7f195c5bcb17e0747fde13aa12190ea0e02"
SOURCE_ARCHIVE_SHA256 = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
RETROSPECTIVE_LEDGER_SEMANTIC_SHA256 = "1e2cc7665698e377c4a4bf80676c2c2635d8ee535c23723d74895dfaeb11c5c8"

CONTRACT: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "campaign": CAMPAIGN_ID,
    "research_contract_sha256": RESEARCH_CONTRACT_SHA256,
    "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
    "symbols": ["NIFTY", "BANKNIFTY", "SENSEX"],
    "source_bar_minutes": 5,
    "signal_bar_minutes": 15,
    "higher_timeframe_minutes": 75,
    "keltner": {
        "ema_length": 20,
        "atr_length": 10,
        "multiplier": 2.0,
        "atr_method": "wilder_adjust_false",
    },
    "hilega": {
        "rsi_length": 9,
        "wma_length": 21,
        "ema_length": 3,
        "rsi_method": "wilder_adjust_false",
    },
    "signal_quality": {
        "body_over_atr_min": 0.35,
        "long_close_location_min": 0.75,
        "short_close_location_max": 0.25,
        "prior_extension_atr_max": 1.5,
    },
    "event_window_ist": {"earliest": "10:15", "latest": "14:15"},
    "confirmation": {
        "bars": 1,
        "minutes": 5,
        "long": "close_above_event_high_and_frozen_upper",
        "short": "close_below_event_low_and_frozen_lower",
    },
    "entry": "next_completed_source_bar_open_after_confirmation",
    "outcome_minutes": 60,
    "research_hurdle_bps": 5.0,
    "one_active_position_per_symbol": True,
    "research_only": True,
    "execution_eligibility": False,
    "allowed_for_live_execution": False,
    "broker_api_called": False,
    "is_order_action": False,
}


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def semantic_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


IMPLEMENTATION_CONTRACT_SHA256 = semantic_sha256(CONTRACT)

SAFETY_FLAGS = {
    "research_only": True,
    "execution_eligibility": False,
    "rankable": False,
    "executable": False,
    "execution_allowed": False,
    "top_opportunity": False,
    "allowed_for_live_execution": False,
    "broker_api_called": False,
    "is_order_action": False,
}
