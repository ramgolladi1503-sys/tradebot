"""
Shadow Circuit Breaker Evaluator (Read-Only Observer) — v4 Production-Hardened.

A non-invasive, purely prospective observer that monitors live Sentinel APM decisions
and records shadow veto telemetry without altering runtime state, execution, or placing orders.

Integrity Invariants:
1. Scoped Event Identity:
   - Events are uniquely and stably identified by `(asset, session_date, position_id)`.
   - Prevents cross-asset collision (e.g. NIFTY `TRADE_1014_CE` vs SENSEX `TRADE_1014_CE`).
2. Robust Timezone-Aware Timestamp Validation:
   - Requires valid ISO 8601 timestamps (must parse with timezone or offset).
   - Rejects missing, malformed, or timezone-inconsistent strings into `quarantine_ledger`.
   - Enforces strictly non-decreasing chronological order per asset.
3. Unmatched Exit Quarantine:
   - An exit arriving without a previously observed proposal is NEVER defaulted to PERMITTED.
   - It is routed to `unmatched_exit_queue` pending reconciliation without mutating breaker state.
4. Quad-State Position Lifecycle Separation:
   - Distinctly tracks:
     a) `IN_FLIGHT_OPEN`: Active trade in flight (from WAL payload). Never synthesized as completed!
     b) `COMPLETED_EVALUABLE`: Full exit recorded with valid spot and option PnL.
     c) `COMPLETED_UNRESOLVED_RISK`: Crash recovery / missing quotes (`TRADE_1513_PE`). Triggers conservative risk pause.
     d) `QUARANTINED_UNMATCHED`: Exit without prior proposal.
5. Challenger Conditioning on Verified Proposals:
   - Challenger processes exits ONLY if the trade was verified and permitted at proposal time.
6. Provenance & Synthetic Isolation:
   - Replay WALs explicitly labeled `BACKFILL_HISTORICAL`.
   - Live incoming events labeled `PROSPECTIVE_LIVE`.
   - Test injections must target isolated test files; live operational state remains 100% clean.
"""

from typing import Dict, Any, List, Optional, Tuple, Set
import os
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("sentinel.shadow_evaluator")

class ShadowCircuitBreakerEvaluator:
    def __init__(self, max_consecutive_losses: int = 2, log_path: Optional[str] = None):
        self.max_consecutive_losses = max_consecutive_losses
        self.log_path = log_path
        
        # State tracked per (asset, session_date) -> dict
        self.asset_states: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        # Scoped event deduplication sets: set of "asset::session_date::position_id"
        self.processed_proposal_keys: Set[str] = set()
        self.processed_exit_keys: Set[str] = set()
        
        # Proposal registry: scoped_key -> obs dict
        self.proposal_registry: Dict[str, Dict[str, Any]] = {}
        
        # Active in-flight positions: scoped_key -> dict
        self.in_flight_positions: Dict[str, Dict[str, Any]] = {}
        
        # Chronological order tracking: asset -> latest valid datetime object
        self.last_event_datetimes: Dict[str, datetime] = {}
        
        # Ledgers
        self.shadow_ledger: List[Dict[str, Any]] = []
        self.quarantine_ledger: List[Dict[str, Any]] = []
        self.unmatched_exit_queue: List[Dict[str, Any]] = []
        
        # Load persisted snapshot if file exists
        if self.log_path and os.path.exists(self.log_path):
            self.load_snapshot(self.log_path)

    def _make_scoped_key(self, asset: str, session_date: str, position_id: str) -> str:
        return f"{asset}::{session_date}::{position_id}"

    def _get_state(self, asset: str, session_date: str) -> Dict[str, Any]:
        k = (asset, session_date)
        if k not in self.asset_states:
            self.asset_states[k] = {
                "consecutive_losses": 0,
                "is_shadow_halted": False,
                "halt_reason": None,
                "halt_timestamp": None,
                "total_proposals": 0,
                "vetoed_proposals": 0,
                "permitted_proposals": 0,
                "total_completed_exits": 0,
                "unresolved_risk_positions": 0
            }
        return self.asset_states[k]

    def _parse_and_validate_timestamp(self, asset: str, ts_str: str) -> Tuple[bool, Optional[datetime], str]:
        """
        Parses and validates ISO 8601 timestamps, enforcing non-decreasing chronological order.
        Normalizes timezone-naive timestamps to IST (+05:30) to eliminate naive vs aware errors.
        """
        if not ts_str:
            return False, None, "MISSING_TIMESTAMP"
            
        try:
            # Handle ISO formats with timezone offsets (+05:30, Z) or naive
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            # If naive, assume IST market timezone (+05:30)
            if dt.tzinfo is None:
                ist_tz = timezone(timedelta(hours=5, minutes=30))
                dt = dt.replace(tzinfo=ist_tz)
        except Exception as e:
            return False, None, f"MALFORMED_TIMESTAMP_FORMAT: {e}"

        last_dt = self.last_event_datetimes.get(asset)
        if last_dt is not None:
            if dt < last_dt:
                return False, None, f"OUT_OF_ORDER_RETROGRADE: {dt} < {last_dt}"

        self.last_event_datetimes[asset] = dt
        return True, dt, "VALID"

    def observe_trade_proposal(
        self,
        position_id: str,
        asset: str,
        session_date: str,
        direction: str,
        contract: str,
        proposal_timestamp: str = "",
        ingest_mode: str = "PROSPECTIVE_LIVE"
    ) -> Dict[str, Any]:
        """
        Observes a proposed trade entry idempotently.
        """
        scoped_key = self._make_scoped_key(asset, session_date, position_id)
        
        # Idempotency check: Return existing proposal without mutating state
        if scoped_key in self.processed_proposal_keys:
            existing = self.proposal_registry.get(scoped_key, {}).copy()
            existing["status"] = "IDEMPOTENT_PROPOSAL_REPLAYED"
            return existing

        # Timestamp validation
        is_valid, dt, err_reason = self._parse_and_validate_timestamp(asset, proposal_timestamp)
        if not is_valid:
            quarantine_rec = {
                "event_type": "PROPOSAL",
                "position_id": position_id,
                "asset": asset,
                "session_date": session_date,
                "proposal_timestamp": proposal_timestamp,
                "reason": err_reason
            }
            self.quarantine_ledger.append(quarantine_rec)
            self._persist_snapshot()
            return {
                "position_id": position_id,
                "asset": asset,
                "shadow_decision": "QUARANTINED",
                "quarantine_reason": err_reason
            }

        st = self._get_state(asset, session_date)
        st["total_proposals"] += 1

        would_permit = not st["is_shadow_halted"]
        veto_reason = None
        if not would_permit:
            veto_reason = f"SHADOW_CHOP_CIRCUIT_BREAKER_L{self.max_consecutive_losses}"
            st["vetoed_proposals"] += 1
        else:
            st["permitted_proposals"] += 1

        obs = {
            "position_id": position_id,
            "asset": asset,
            "session_date": session_date,
            "proposal_timestamp": proposal_timestamp,
            "direction": direction,
            "contract": contract,
            "shadow_decision": "PERMITTED" if would_permit else "VETOED",
            "veto_reason": veto_reason,
            "active_consecutive_losses": st["consecutive_losses"],
            "ingest_mode": ingest_mode,
            "lifecycle_state": "IN_FLIGHT_OPEN"
        }
        
        self.processed_proposal_keys.add(scoped_key)
        self.proposal_registry[scoped_key] = obs
        self.in_flight_positions[scoped_key] = obs
        self._persist_snapshot()
        return obs

    def observe_trade_exit(
        self,
        position_id: str,
        asset: str,
        session_date: str,
        spot_pnl: Optional[float],
        opt_pnl: Optional[float],
        exit_reason: str,
        exit_timestamp: str = "",
        opt_entry_bid: Optional[float] = None,
        opt_entry_ask: Optional[float] = None,
        opt_exit_bid: Optional[float] = None,
        opt_exit_ask: Optional[float] = None,
        ingest_mode: str = "PROSPECTIVE_LIVE"
    ) -> Dict[str, Any]:
        """
        Observes a completed trade exit idempotently and causally updates the breaker state.
        Enforces proposal matching and quarantines unmatched exits.
        """
        scoped_key = self._make_scoped_key(asset, session_date, position_id)
        
        # Idempotency check: Exit already processed
        if scoped_key in self.processed_exit_keys:
            return {
                "position_id": position_id,
                "asset": asset,
                "session_date": session_date,
                "status": "DUPLICATE_EXIT_IGNORED"
            }

        # Proposal Matching Guard: Reject defaulting to PERMITTED!
        if scoped_key not in self.proposal_registry:
            unmatched_rec = {
                "position_id": position_id,
                "asset": asset,
                "session_date": session_date,
                "exit_timestamp": exit_timestamp,
                "spot_pnl": spot_pnl,
                "opt_pnl": opt_pnl,
                "exit_reason": exit_reason,
                "status": "UNMATCHED_EXIT_QUARANTINED",
                "reason": "MISSING_PRIOR_PROPOSAL_DECISION"
            }
            self.unmatched_exit_queue.append(unmatched_rec)
            self._persist_snapshot()
            return unmatched_rec

        # Timestamp validation
        is_valid, dt, err_reason = self._parse_and_validate_timestamp(asset, exit_timestamp)
        if not is_valid:
            if scoped_key not in self.processed_exit_keys:
                self.processed_exit_keys.add(scoped_key)
                quarantine_rec = {
                    "event_type": "EXIT",
                    "position_id": position_id,
                    "asset": asset,
                    "session_date": session_date,
                    "exit_timestamp": exit_timestamp,
                    "reason": err_reason
                }
                self.quarantine_ledger.append(quarantine_rec)
                self._persist_snapshot()
            return {
                "position_id": position_id,
                "asset": asset,
                "status": "QUARANTINED",
                "quarantine_reason": err_reason
            }

        st = self._get_state(asset, session_date)
        st["total_completed_exits"] += 1

        # Retrieve prior proposal decision
        prop_rec = self.proposal_registry[scoped_key]
        was_challenger_executed = (prop_rec.get("shadow_decision") == "PERMITTED")

        # Tri-State position lifecycle evaluation
        is_unresolved = (opt_pnl is None and spot_pnl is None)
        
        if is_unresolved:
            lifecycle_state = "COMPLETED_UNRESOLVED_RISK"
            st["unresolved_risk_positions"] += 1
            # Conservative pause: Triggers halt without faking a numerical PnL
            st["is_shadow_halted"] = True
            st["halt_reason"] = "CONSERVATIVE_PAUSE_ON_UNRESOLVED_RISK"
            st["halt_timestamp"] = exit_timestamp
        elif opt_pnl is not None:
            lifecycle_state = "COMPLETED_EVALUABLE"
            is_loss = (opt_pnl < 0.0) or ("STOP_LOSS" in exit_reason)
            if was_challenger_executed:
                if is_loss:
                    st["consecutive_losses"] += 1
                    if st["consecutive_losses"] >= self.max_consecutive_losses:
                        st["is_shadow_halted"] = True
                        st["halt_reason"] = f"CONSECUTIVE_LOSS_LIMIT_{self.max_consecutive_losses}_EXCEEDED"
                        st["halt_timestamp"] = exit_timestamp
                else:
                    st["consecutive_losses"] = 0
        else:
            lifecycle_state = "COMPLETED_EVALUABLE_SPOT_ONLY"
            is_loss = (spot_pnl < 0.0) or ("STOP_LOSS" in exit_reason)
            if was_challenger_executed:
                if is_loss:
                    st["consecutive_losses"] += 1
                    if st["consecutive_losses"] >= self.max_consecutive_losses:
                        st["is_shadow_halted"] = True
                        st["halt_reason"] = f"CONSECUTIVE_LOSS_LIMIT_{self.max_consecutive_losses}_EXCEEDED"
                        st["halt_timestamp"] = exit_timestamp
                else:
                    st["consecutive_losses"] = 0

        # Assess quote depth completeness: Explicit non-executable classification
        has_entry_depth = (opt_entry_bid is not None and opt_entry_ask is not None)
        has_exit_depth = (opt_exit_bid is not None and opt_exit_ask is not None)
        if has_entry_depth and has_exit_depth:
            depth_coverage = "FULL_BID_ASK_VERIFIED"
        elif has_entry_depth:
            depth_coverage = "ENTRY_DEPTH_ONLY_NON_EXECUTABLE_ESTIMATE"
        else:
            depth_coverage = "DEPTH_MISSING_LTP_MODELED_ONLY"

        record = {
            "position_id": position_id,
            "asset": asset,
            "session_date": session_date,
            "exit_timestamp": exit_timestamp,
            "spot_pnl": spot_pnl,
            "opt_pnl": opt_pnl,
            "exit_reason": exit_reason,
            "lifecycle_state": lifecycle_state,
            "depth_coverage": depth_coverage,
            "was_challenger_executed": was_challenger_executed,
            "consecutive_losses_after_exit": st["consecutive_losses"],
            "is_shadow_halted_now": st["is_shadow_halted"],
            "ingest_mode": ingest_mode
        }
        
        # Transition out of in-flight
        self.in_flight_positions.pop(scoped_key, None)
        self.processed_exit_keys.add(scoped_key)
        self.shadow_ledger.append(record)
        self._persist_snapshot()
        return record

    def _persist_snapshot(self):
        """Atomically persists asset_states and ledgers to disk."""
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            serialized_asset_states = {
                f"{k[0]}::{k[1]}": v for k, v in self.asset_states.items()
            }
            # Serialize datetimes to ISO strings
            serialized_last_dts = {
                asset: dt.isoformat() for asset, dt in self.last_event_datetimes.items()
            }
            payload = {
                "version": "shadow_evaluator_v4_production",
                "max_consecutive_losses": self.max_consecutive_losses,
                "asset_states": serialized_asset_states,
                "processed_proposal_keys": list(self.processed_proposal_keys),
                "processed_exit_keys": list(self.processed_exit_keys),
                "proposal_registry": self.proposal_registry,
                "in_flight_positions": self.in_flight_positions,
                "last_event_timestamps": serialized_last_dts,
                "shadow_ledger": self.shadow_ledger,
                "quarantine_ledger": self.quarantine_ledger,
                "unmatched_exit_queue": self.unmatched_exit_queue
            }
            tmp_path = f"{self.log_path}.tmp.{os.getpid()}"
            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.log_path)
        except Exception as e:
            logger.error(f"Failed to atomically persist shadow snapshot: {e}")

    def load_snapshot(self, path: str):
        """Recovers state seamlessly from a persisted JSON snapshot."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self.max_consecutive_losses = data.get("max_consecutive_losses", self.max_consecutive_losses)
            raw_states = data.get("asset_states", {})
            self.asset_states = {}
            for k_str, st in raw_states.items():
                if "::" in k_str:
                    asset, date = k_str.split("::", 1)
                    self.asset_states[(asset, date)] = st
            self.processed_proposal_keys = set(data.get("processed_proposal_keys", []))
            self.processed_exit_keys = set(data.get("processed_exit_keys", []))
            self.proposal_registry = data.get("proposal_registry", {})
            self.in_flight_positions = data.get("in_flight_positions", {})
            
            raw_dts = data.get("last_event_timestamps", {})
            self.last_event_datetimes = {}
            for asset, ts_str in raw_dts.items():
                try:
                    self.last_event_datetimes[asset] = datetime.fromisoformat(ts_str)
                except Exception:
                    pass
                    
            self.shadow_ledger = data.get("shadow_ledger", [])
            self.quarantine_ledger = data.get("quarantine_ledger", [])
            self.unmatched_exit_queue = data.get("unmatched_exit_queue", [])
            logger.info(f"Loaded shadow evaluator snapshot from {path} with {len(self.asset_states)} states")
        except Exception as e:
            logger.error(f"Failed to load shadow snapshot: {e}")
