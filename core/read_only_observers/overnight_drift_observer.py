#!/usr/bin/env python3
"""
READ_ONLY_PROSPECTIVE_OBSERVER: Overnight Drift Family
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Production-Grade Prospective Observer adhering strictly to AGENTS.md:
- read_only = True
- broker_write_authority = False
- order_authority = False
- paper_authorized = False
- live_authorized = False
- allowed_for_live_execution = False
- append_only_ledger = True
- tamper_evident_hash_chain = True
- cross_process_file_locking = True
- persistent_state_authority = True (Reconstructed directly from ledger on disk)
- crash_atomic_commits = True (Atomic rename + fsync + crash recovery)
- internal_freshness_derivation = True (source_ts vs receipt_ts)
- frozen_arrival_pricing = True (Midpoint / Best Ask crossing rule)
"""

from __future__ import annotations
import os
import fcntl
import json
import hashlib
from enum import Enum
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

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
    OBSERVATION_INVALID = "OBSERVATION_INVALID"


ALLOWED_TRANSITIONS: Dict[ObserverLifecycleState, List[ObserverLifecycleState]] = {
    ObserverLifecycleState.PRE_SESSION: [
        ObserverLifecycleState.MACRO_STATE_FROZEN,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.MACRO_STATE_FROZEN: [
        ObserverLifecycleState.SIGNAL_SEALED_1520,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.SIGNAL_SEALED_1520: [
        ObserverLifecycleState.QUALIFIED,
        ObserverLifecycleState.NOT_QUALIFIED,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.QUALIFIED: [
        ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.ARRIVAL_CAPTURED_1521: [
        ObserverLifecycleState.OVERNIGHT_PENDING,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.OVERNIGHT_PENDING: [
        ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED: [
        ObserverLifecycleState.OBSERVATION_FINALIZED,
        ObserverLifecycleState.OBSERVATION_INVALID,
    ],
    ObserverLifecycleState.NOT_QUALIFIED: [],
    ObserverLifecycleState.OBSERVATION_FINALIZED: [],
    ObserverLifecycleState.OBSERVATION_INVALID: [],
}


@dataclass(frozen=True)
class TamperEvidentObservationEntry:
    sequence_number: int
    previous_record_hash: str
    record_hash: str
    lifecycle_state: str
    observation_id: str
    sub_ledger: str
    candidate_id: str
    spec_digest: str
    schedule_sha256: str
    session_date: str
    decision_timestamp_ist: str
    macro_uptrend: bool
    day_gain_pct: float
    is_monday: bool
    qualified: bool
    quote_source_timestamp_ist: Optional[str]
    quote_receipt_timestamp_ist: Optional[str]
    quote_freshness_ms: Optional[int]
    best_bid: Optional[float]
    best_ask: Optional[float]
    midpoint: Optional[float]
    spread_pts: Optional[float]
    frozen_arrival_price: Optional[float]
    market_buy_arrival_estimate: Optional[float]
    passive_limit_tracked_price: Optional[float]
    next_session_open: Optional[float]
    gross_pnl_pts: Optional[float]
    deterministic_cost_pts: float
    net_pnl_pts: Optional[float]
    feed_healthy: bool
    validation_notes: str


def compute_canonical_record_hash(previous_hash: str, entry_dict_without_hash: Dict[str, Any]) -> str:
    """Computes cryptographic SHA-256 over 100% of record fields plus previous hash."""
    payload_to_hash = dict(entry_dict_without_hash)
    if "record_hash" in payload_to_hash:
        del payload_to_hash["record_hash"]

    serialized = json.dumps(payload_to_hash, sort_keys=True)
    raw = f"{previous_hash}|{serialized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calculate_internal_quote_freshness(source_ts_str: Optional[str], receipt_ts_str: Optional[str]) -> Optional[int]:
    """
    Computes quote freshness internally from exchange/source timestamp vs local receipt timestamp.
    Returns delta in milliseconds. Fails closed (returns None) if unparseable or missing.
    """
    if not source_ts_str or not receipt_ts_str:
        return None
    try:
        s_dt = datetime.fromisoformat(source_ts_str)
        r_dt = datetime.fromisoformat(receipt_ts_str)
        delta = (r_dt - s_dt).total_seconds() * 1000.0
        return int(max(0, delta))
    except Exception:
        return None


class TamperEvidentLedgerManager:
    """
    Persistent state authority: Reconstructs state from ledger on disk under cross-process file locks.
    Implements atomic crash-recovery and external head-anchor sealing.
    """

    def __init__(self, ledger_dir: str = OBSERVER_DIR):
        self.ledger_dir = ledger_dir
        os.makedirs(self.ledger_dir, exist_ok=True)

    def _get_lock_file(self, sub_ledger: str):
        lock_path = os.path.join(self.ledger_dir, f".{sub_ledger.lower()}.lock")
        return open(lock_path, "w")

    def _get_ledger_path(self, sub_ledger: str) -> str:
        return os.path.join(self.ledger_dir, f"{sub_ledger.lower()}_ledger.jsonl")

    def _get_head_anchor_path(self, sub_ledger: str) -> str:
        return os.path.join(self.ledger_dir, f"{sub_ledger.lower()}_head_anchor.json")

    def get_persisted_session_state(self, sub_ledger: str, session_key: str) -> ObserverLifecycleState:
        """
        Reconstructs the authoritative lifecycle state for a session directly from the persisted disk ledger.
        Zero reliance on transient process memory. Survives complete process restarts.
        """
        ledger_path = self._get_ledger_path(sub_ledger)
        if not os.path.exists(ledger_path):
            return ObserverLifecycleState.PRE_SESSION

        last_state = ObserverLifecycleState.PRE_SESSION
        with open(ledger_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line.strip())
                entry_key = f"{entry['sub_ledger']}|{entry['candidate_id']}|{entry['session_date']}"
                if entry_key == session_key:
                    last_state = ObserverLifecycleState(entry["lifecycle_state"])

        return last_state

    def get_latest_entry_info(self, sub_ledger: str) -> Tuple[int, str]:
        """Returns (sequence_number, record_hash) of the latest entry or (0, 'GENESIS_HASH')."""
        ledger_path = self._get_ledger_path(sub_ledger)
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

    def _sync_head_anchor_atomically(self, sub_ledger: str, new_seq: int, rec_hash: str) -> None:
        """
        Writes external head-anchor via temp file + atomic rename + fsync,
        preventing corruption during mid-write process crashes.
        """
        anchor_path = self._get_head_anchor_path(sub_ledger)
        temp_anchor_path = f"{anchor_path}.tmp.{os.getpid()}"

        payload = {
            "sub_ledger": sub_ledger,
            "total_records": new_seq,
            "latest_sequence": new_seq,
            "latest_record_hash": rec_hash,
            "anchor_updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(temp_anchor_path, "w") as tf:
            json.dump(payload, tf, indent=2, sort_keys=True)
            tf.flush()
            os.fsync(tf.fileno())

        os.replace(temp_anchor_path, anchor_path)

    def recover_crash_consistency(self, sub_ledger: str) -> None:
        """
        Detects if process died between ledger append and head anchor update.
        Re-synchronizes head anchor if ledger contains verified, fully fsynced records.
        """
        seq, last_hash = self.get_latest_entry_info(sub_ledger)
        anchor_path = self._get_head_anchor_path(sub_ledger)

        if seq > 0 and (not os.path.exists(anchor_path)):
            self._sync_head_anchor_atomically(sub_ledger, seq, last_hash)
            return

        if os.path.exists(anchor_path):
            with open(anchor_path, "r") as af:
                anchor_data = json.load(af)
            if anchor_data["total_records"] < seq:
                # Ledger progressed ahead of anchor before crash -> recover
                self._sync_head_anchor_atomically(sub_ledger, seq, last_hash)

    def append_observation(
        self,
        sub_ledger: str,
        target_state: ObserverLifecycleState,
        candidate_spec: FrozenCandidateSpec,
        schedule_sha256: str,
        session_date: str,
        decision_ts: str,
        macro_uptrend: bool,
        day_gain_pct: float,
        is_monday: bool,
        qualified: bool,
        quote_source_ts: Optional[str] = None,
        quote_receipt_ts: Optional[str] = None,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        next_session_open: Optional[float] = None,
        validation_notes: str = "",
    ) -> TamperEvidentObservationEntry:
        """
        Cross-process locked, persistent-state validated append to immutable ledger.
        """
        lock_fd = self._get_lock_file(sub_ledger)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # 1. Crash recovery check
            self.recover_crash_consistency(sub_ledger)

            session_key = f"{sub_ledger}|{candidate_spec.candidate_id}|{session_date}"

            # 2. PERSISTENT STATE AUTHORITY: Read authoritative current state directly from disk
            current_persisted_state = self.get_persisted_session_state(sub_ledger, session_key)

            # 3. Calculate quote freshness internally from timestamps
            quote_freshness_ms = calculate_internal_quote_freshness(quote_source_ts, quote_receipt_ts)

            # 4. Enforce Quote Fail-Closed Contract & Frozen Arrival Pricing
            feed_healthy = True
            notes = validation_notes
            effective_state = target_state

            if target_state == ObserverLifecycleState.ARRIVAL_CAPTURED_1521:
                if quote_freshness_ms is None:
                    feed_healthy = False
                    notes += " [QUOTE_FAIL_CLOSED: quote_freshness unparseable or missing]"
                elif quote_freshness_ms > MAX_ALLOWED_QUOTE_AGE_MS:
                    feed_healthy = False
                    notes += f" [QUOTE_FAIL_CLOSED: stale quote {quote_freshness_ms}ms > {MAX_ALLOWED_QUOTE_AGE_MS}ms]"

                if best_bid is None or best_ask is None or quote_source_ts is None:
                    feed_healthy = False
                    notes += " [QUOTE_FAIL_CLOSED: missing bid/ask quote]"
                elif best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
                    feed_healthy = False
                    notes += " [QUOTE_FAIL_CLOSED: inverted or non-positive spread]"

                if not feed_healthy:
                    effective_state = ObserverLifecycleState.OBSERVATION_INVALID

            # 5. Enforce transition graph against PERSISTED state
            allowed = ALLOWED_TRANSITIONS.get(current_persisted_state, [])
            if effective_state not in allowed:
                raise ValueError(
                    f"ILLEGAL_PERSISTED_STATE_TRANSITION: Session '{session_key}' on disk is in state "
                    f"{current_persisted_state}, cannot transition to {effective_state}!"
                )

            # 6. Frozen Arrival Pricing Rules:
            # - Primary theoretical entry = Midpoint
            # - Conservative crossing estimate = Best Ask
            midpoint = None
            spread_pts = None
            market_buy_estimate = None
            frozen_arrival_price = None

            if best_bid is not None and best_ask is not None and feed_healthy:
                midpoint = round((best_bid + best_ask) / 2.0, 2)
                spread_pts = round(best_ask - best_bid, 2)
                market_buy_estimate = best_ask
                frozen_arrival_price = midpoint  # Standard frozen benchmark arrival

            gross_pnl = None
            net_pnl = None
            det_cost = candidate_spec.deterministic_friction_pts
            if frozen_arrival_price is not None and next_session_open is not None and feed_healthy:
                if frozen_arrival_price > 0 and next_session_open > 0:
                    gross_pnl = round(next_session_open - frozen_arrival_price, 2)
                    net_pnl = round(gross_pnl - det_cost, 2)

            seq, prev_hash = self.get_latest_entry_info(sub_ledger)
            new_seq = seq + 1
            obs_id = f"OBS-{session_date}-{candidate_spec.candidate_id[:2]}-{new_seq:04d}"

            raw_dict = {
                "sequence_number": new_seq,
                "previous_record_hash": prev_hash,
                "lifecycle_state": effective_state.value,
                "observation_id": obs_id,
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
                "quote_source_timestamp_ist": quote_source_ts,
                "quote_receipt_timestamp_ist": quote_receipt_ts,
                "quote_freshness_ms": quote_freshness_ms,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "midpoint": midpoint,
                "spread_pts": spread_pts,
                "frozen_arrival_price": frozen_arrival_price,
                "market_buy_arrival_estimate": market_buy_estimate,
                "passive_limit_tracked_price": best_bid if feed_healthy else None,
                "next_session_open": next_session_open,
                "gross_pnl_pts": gross_pnl,
                "deterministic_cost_pts": det_cost,
                "net_pnl_pts": net_pnl,
                "feed_healthy": feed_healthy,
                "validation_notes": notes,
            }

            rec_hash = compute_canonical_record_hash(prev_hash, raw_dict)
            raw_dict["record_hash"] = rec_hash

            entry = TamperEvidentObservationEntry(**raw_dict)

            # Atomic ledger append + fsync
            ledger_file = self._get_ledger_path(sub_ledger)
            with open(ledger_file, "a") as f:
                f.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())

            # Atomic head anchor sync
            self._sync_head_anchor_atomically(sub_ledger, new_seq, rec_hash)

            return entry

        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def verify_ledger_integrity(self, sub_ledger: str) -> Tuple[bool, str]:
        """Verifies full cryptographic chain integrity and external head-anchor agreement."""
        ledger_path = self._get_ledger_path(sub_ledger)
        anchor_path = self._get_head_anchor_path(sub_ledger)

        if not os.path.exists(ledger_path):
            return True, "EMPTY_LEDGER_VALID"

        if not os.path.exists(anchor_path):
            return False, "MISSING_EXTERNAL_HEAD_ANCHOR"

        with open(anchor_path, "r") as af:
            anchor = json.load(af)

        prev_hash = "GENESIS_OVERNIGHT_DRIFT_0000000000000000000000000000000000000000"
        expected_seq = 1
        last_hash_seen = None

        with open(ledger_path, "r") as f:
            for line_idx, line in enumerate(f):
                if not line.strip():
                    continue
                entry = json.loads(line.strip())

                if entry["sequence_number"] != expected_seq:
                    return False, f"SEQUENCE_BROKEN_AT_LINE_{line_idx+1}"
                if entry["previous_record_hash"] != prev_hash:
                    return False, f"PREV_HASH_MISMATCH_AT_LINE_{line_idx+1}"

                computed = compute_canonical_record_hash(prev_hash, entry)
                if computed != entry["record_hash"]:
                    return False, f"TAMPERED_RECORD_PAYLOAD_AT_LINE_{line_idx+1}"

                prev_hash = entry["record_hash"]
                last_hash_seen = entry["record_hash"]
                expected_seq += 1

        actual_records = expected_seq - 1

        if actual_records != anchor["total_records"]:
            return False, f"TAIL_TRUNCATION_DETECTED: Ledger has {actual_records} rows, anchor specifies {anchor['total_records']}"

        if last_hash_seen != anchor["latest_record_hash"]:
            return False, f"HEAD_ANCHOR_HASH_MISMATCH: Last hash {last_hash_seen} != anchor {anchor['latest_record_hash']}"

        return True, "CHAIN_AND_ANCHOR_VERIFIED_PERFECT"
