#!/usr/bin/env python3
"""
READ_ONLY_PROSPECTIVE_OBSERVER: Overnight Drift Family
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Strictly read-only prospective observer adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- order_authority = False
- paper_authorized = False
- live_authorized = False
- allowed_for_live_execution = False
- append_only_ledger = True

Captures real-time market arrival prices, bid/ask quotes, and next-morning exits
across four distinct sub-ledgers:
1. S1_ONLY
2. S4_ONLY
3. S1_AND_S4_OVERLAP
4. OVERALL_OVERNIGHT_FAMILY
"""

from __future__ import annotations
import os
import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S1_SPEC_DIGEST,
    CANDIDATE_S1_SCHEDULE_SHA256,
    CANDIDATE_S4_ID,
    CANDIDATE_S4_SPEC_DIGEST,
    CANDIDATE_S4_SCHEDULE_SHA256,
    DETERMINISTIC_COST_PTS,
    evaluate_overnight_signal,
    OvernightSignalResult
)

OBSERVER_DIR = "runtime/prospective_observations/overnight_drift"


@dataclass(frozen=True)
class ProspectiveObservationRecord:
    observation_id: str
    sub_ledger: str  # S1_ONLY, S4_ONLY, S1_AND_S4_OVERLAP, OVERALL_OVERNIGHT_FAMILY
    candidate_id: str
    spec_digest: str
    schedule_sha256: str
    session_date: str
    decision_timestamp_ist: str
    macro_uptrend: bool
    day_gain_pct: float
    is_monday: bool
    qualified: bool
    arrival_timestamp_ist: str
    arrival_price: float
    best_bid: Optional[float]
    best_ask: Optional[float]
    spread_pts: Optional[float]
    next_session_open: Optional[float]
    gross_pnl_pts: Optional[float]
    net_pnl_pts: Optional[float]
    quote_freshness_ms: Optional[int]
    feed_healthy: bool


def record_prospective_observation(record: ProspectiveObservationRecord) -> str:
    """
    Appends observation record to immutable JSONL audit ledger.
    Fail-closed: Does not place, modify, or send any broker orders.
    """
    os.makedirs(OBSERVER_DIR, exist_ok=True)
    ledger_file = os.path.join(OBSERVER_DIR, f"{record.sub_ledger.lower()}_ledger.jsonl")
    
    serialized = json.dumps(asdict(record), sort_keys=True)
    with open(ledger_file, "a") as f:
        f.write(serialized + "\n")
        
    return ledger_file
