#!/usr/bin/env python3
"""
READ_ONLY_PROSPECTIVE_OBSERVER: Overnight Drift Family
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Strictly read-only prospective state machine adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- order_authority = False
- paper_authorized = False
- live_authorized = False
- allowed_for_live_execution = False
- append_only_ledger = True
- tamper_evident_hash_chain = True

Prospective State Machine:
  PRE_SESSION
     ↓
  MACRO_STATE_FROZEN
     ↓
  SIGNAL_SEALED_1520
     ↓
  QUALIFIED / NOT_QUALIFIED
     ↓
  ARRIVAL_CAPTURED_1521
     ↓
  OVERNIGHT_PENDING
     ↓
  NEXT_SESSION_OPEN_CAPTURED
     ↓
  OBSERVATION_FINALIZED
"""

from __future__ import annotations
import os
import json
import hashlib
from enum import Enum
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S1_SCHEDULE_SHA256,
    CANDIDATE_S4_ID,
    CANDIDATE_S4_SCHEDULE_SHA256,
    FrozenCandidateSpec,
    load_and_validate_frozen_spec,
    evaluate_overnight_signal,
    OvernightSignalResult
)

OBSERVER_DIR = "runtime/prospective_observations/overnight_drift"
MAX_ALLOWED_QUOTE_AGE_MS = 5000  # Fail-closed staleness threshold (5 seconds)


class ObserverLifecycleState(str, Enum):
    PRE_SESSION = "PRE_SESSION"
    MACRO_STATE_FROZEN = "MACRO_STATE_FROZEN"
    SIGNAL_SEALED_1520 = "SIGNAL_SEALED_1520"
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    ARRIVAL_CAPTURED_1521 = "ARRIVAL_CAPTURED_1521"
    OVERNIGHT_PENDING = "OVERNIGHT_PENDING"
    NEXT_SESSION_OPEN_CAPTURED = "NEXT_SESSION_OPEN_CAPTURED"
    OBSERVATION_FINALIZED = "OBSERVATION_FINALIZED"
    OBSERVATION_INVALID_DATA_MISSING = "OBSERVATION_INVALID_DATA_MISSING"


@dataclass(frozen=True)
class TamperEvidentObservationEntry:
    sequence_number: int
    previous_record_hash: str
    record_hash: str
    lifecycle_state: str
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
    arrival_timestamp_ist: Optional[str]
    arrival_price: Optional[float]
    best_bid: Optional[float]
    best_ask: Optional[float]
    midpoint: Optional[float]
    spread_pts: Optional[float]
    market_buy_arrival_estimate: Optional[float]
    passive_limit_tracked_price: Optional[float]
    next_session_open: Optional[float]
    gross_pnl_pts: Optional[float]
    deterministic_cost_pts: float
    net_pnl_pts: Optional[float]
    quote_freshness_ms: Optional[int]
    feed_healthy: bool
    validation_notes: str


def compute_record_hash(previous_hash: str, record_payload: Dict[str, Any]) -> str:
    """Computes tamper-evident SHA256 hash over previous hash and canonical record payload."""
    serialized = json.dumps(record_payload, sort_keys=True)
    raw = f"{previous_hash}|{serialized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TamperEvidentLedgerManager:
    """Manages hash-chained, append-only JSONL files for prospective observations."""

    def __init__(self, ledger_dir: str = OBSERVER_DIR):
        self.ledger_dir = ledger_dir
        os.makedirs(self.ledger_dir, exist_ok=True)

    def get_latest_entry_info(self, sub_ledger: str) -> Tuple[int, str]:
        """Returns (sequence_number, record_hash) of the latest entry or (0, 'GENESIS_HASH')."""
        ledger_path = os.path.join(self.ledger_dir, f"{sub_ledger.lower()}_ledger.jsonl")
        if not os.path.exists(ledger_path):
            return 0, "GENESIS_OVERNIGHT_DRIFT_0000000000000000000000000000000000000000"

        last_line = None
        with open(ledger_path, "r") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()

        if not last_line:
            return 0, "GENESIS_OVERNIGHT_DRIFT_0000000000000000000000000000000000000000"

        data = json.loads(last_line)
        return int(data["sequence_number"]), str(data["record_hash"])

    def append_observation(
        self,
        sub_ledger: str,
        lifecycle_state: ObserverLifecycleState,
        candidate_spec: FrozenCandidateSpec,
        schedule_sha256: str,
        session_date: str,
        decision_ts: str,
        macro_uptrend: bool,
        day_gain_pct: float,
        is_monday: bool,
        qualified: bool,
        arrival_ts: Optional[str] = None,
        arrival_price: Optional[float] = None,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        quote_freshness_ms: Optional[int] = None,
        next_session_open: Optional[float] = None,
        validation_notes: str = "",
    ) -> TamperEvidentObservationEntry:
        """
        Executes strict fail-closed observation processing and persists to hash-chained ledger.
        """
        seq, prev_hash = self.get_latest_entry_info(sub_ledger)
        new_seq = seq + 1

        # Evaluate quote freshness & feed health
        feed_healthy = True
        notes = validation_notes
        if quote_freshness_ms is not None:
            if quote_freshness_ms > MAX_ALLOWED_QUOTE_AGE_MS:
                feed_healthy = False
                notes += f" [STALE_QUOTE: {quote_freshness_ms}ms > {MAX_ALLOWED_QUOTE_AGE_MS}ms]"

        if best_bid is not None and best_ask is not None:
            if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
                feed_healthy = False
                notes += " [INVALID_SPREAD: bid/ask inversion or non-positive]"

        midpoint = None
        spread_pts = None
        market_buy_estimate = None
        if best_bid is not None and best_ask is not None and feed_healthy:
            midpoint = round((best_bid + best_ask) / 2.0, 2)
            spread_pts = round(best_ask - best_bid, 2)
            market_buy_estimate = best_ask

        # Calculate PnL if arrival and exit exist and feed is healthy
        gross_pnl = None
        net_pnl = None
        det_cost = candidate_spec.deterministic_friction_pts
        if arrival_price is not None and next_session_open is not None and feed_healthy:
            if arrival_price > 0 and next_session_open > 0:
                gross_pnl = round(next_session_open - arrival_price, 2)
                net_pnl = round(gross_pnl - det_cost, 2)

        # Build raw payload for hashing
        payload_for_hashing = {
            "sequence_number": new_seq,
            "lifecycle_state": lifecycle_state.value,
            "sub_ledger": sub_ledger,
            "candidate_id": candidate_spec.candidate_id,
            "spec_digest": candidate_spec.spec_digest,
            "schedule_sha256": schedule_sha256,
            "session_date": session_date,
            "decision_timestamp_ist": decision_ts,
            "macro_uptrend": macro_uptrend,
            "day_gain_pct": round(day_gain_pct, 4),
            "is_monday": is_monday,
            "qualified": qualified,
            "arrival_timestamp_ist": arrival_ts,
            "arrival_price": arrival_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "midpoint": midpoint,
            "spread_pts": spread_pts,
            "next_session_open": next_session_open,
            "gross_pnl_pts": gross_pnl,
            "deterministic_cost_pts": det_cost,
            "net_pnl_pts": net_pnl,
            "feed_healthy": feed_healthy,
        }

        rec_hash = compute_record_hash(prev_hash, payload_for_hashing)
        obs_id = f"OBS-{session_date}-{candidate_spec.candidate_id[:2]}-{new_seq:04d}"

        entry = TamperEvidentObservationEntry(
            sequence_number=new_seq,
            previous_record_hash=prev_hash,
            record_hash=rec_hash,
            lifecycle_state=lifecycle_state.value,
            observation_id=obs_id,
            sub_ledger=sub_ledger,
            candidate_id=candidate_spec.candidate_id,
            spec_digest=candidate_spec.spec_digest,
            schedule_sha256=schedule_sha256,
            session_date=session_date,
            decision_timestamp_ist=decision_ts,
            macro_uptrend=macro_uptrend,
            day_gain_pct=day_gain_pct,
            is_monday=is_monday,
            qualified=qualified,
            arrival_timestamp_ist=arrival_ts,
            arrival_price=arrival_price,
            best_bid=best_bid,
            best_ask=best_ask,
            midpoint=midpoint,
            spread_pts=spread_pts,
            market_buy_arrival_estimate=market_buy_estimate,
            passive_limit_tracked_price=best_bid if feed_healthy else None,
            next_session_open=next_session_open,
            gross_pnl_pts=gross_pnl,
            deterministic_cost_pts=det_cost,
            net_pnl_pts=net_pnl,
            quote_freshness_ms=quote_freshness_ms,
            feed_healthy=feed_healthy,
            validation_notes=notes,
        )

        ledger_file = os.path.join(self.ledger_dir, f"{sub_ledger.lower()}_ledger.jsonl")
        serialized = json.dumps(asdict(entry), sort_keys=True)
        with open(ledger_file, "a") as f:
            f.write(serialized + "\n")

        return entry

    def verify_ledger_integrity(self, sub_ledger: str) -> bool:
        """Verifies the complete cryptographic hash-chain of a prospective sub-ledger."""
        ledger_path = os.path.join(self.ledger_dir, f"{sub_ledger.lower()}_ledger.jsonl")
        if not os.path.exists(ledger_path):
            return True  # Empty is valid

        prev_hash = "GENESIS_OVERNIGHT_DRIFT_0000000000000000000000000000000000000000"
        expected_seq = 1

        with open(ledger_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line.strip())

                if entry["sequence_number"] != expected_seq:
                    return False
                if entry["previous_record_hash"] != prev_hash:
                    return False

                # Reconstruct hashing payload
                payload = {
                    "sequence_number": entry["sequence_number"],
                    "lifecycle_state": entry["lifecycle_state"],
                    "sub_ledger": entry["sub_ledger"],
                    "candidate_id": entry["candidate_id"],
                    "spec_digest": entry["spec_digest"],
                    "schedule_sha256": entry["schedule_sha256"],
                    "session_date": entry["session_date"],
                    "decision_timestamp_ist": entry["decision_timestamp_ist"],
                    "macro_uptrend": entry["macro_uptrend"],
                    "day_gain_pct": round(entry["day_gain_pct"], 4),
                    "is_monday": entry["is_monday"],
                    "qualified": entry["qualified"],
                    "arrival_timestamp_ist": entry["arrival_timestamp_ist"],
                    "arrival_price": entry["arrival_price"],
                    "best_bid": entry["best_bid"],
                    "best_ask": entry["best_ask"],
                    "midpoint": entry["midpoint"],
                    "spread_pts": entry["spread_pts"],
                    "next_session_open": entry["next_session_open"],
                    "gross_pnl_pts": entry["gross_pnl_pts"],
                    "deterministic_cost_pts": entry["deterministic_cost_pts"],
                    "net_pnl_pts": entry["net_pnl_pts"],
                    "feed_healthy": entry["feed_healthy"],
                }
                computed = compute_record_hash(prev_hash, payload)
                if computed != entry["record_hash"]:
                    return False

                prev_hash = entry["record_hash"]
                expected_seq += 1

        return True
