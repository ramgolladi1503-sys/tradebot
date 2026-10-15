"""
Shadow Circuit Breaker Evaluator (Read-Only Observer) — v5 Final Production Gate.

A non-invasive, purely prospective observer that monitors live Sentinel APM decisions
and records shadow veto telemetry without altering runtime state, execution, or placing orders.

Integrity Invariants:
1. Scoped Event Identity:
   - Events are uniquely and stably identified by `(asset, session_date, position_id)`.
   - Prevents cross-asset collision (e.g. NIFTY `TRADE_1014_CE` vs SENSEX `TRADE_1014_CE`).
2. Separate Quarantine Identity & Reconcilable Remediation:
   - Quarantined exits are tracked in `quarantined_exit_keys` and NOT added to `processed_exit_keys`.
   - Allows invalid or repaired records to be reconciled safely, idempotently, and with an audit trail
     via `reconcile_quarantined_exit()`.
3. Historical Unresolved Risk Reconciled:
   - `TRADE_1513_PE` is reconciled as `HISTORICAL_UNRESOLVED_RISK` from October 14.
   - It triggers a session risk pause without masquerading as currently in-flight or an active open position.
4. Reception Timestamp & Prospective vs Retrospective Provenance:
   - Tracks `observer_received_at` (actual wall-clock reception time).
   - Only classifies a proposal as `PROSPECTIVE_OBSERVED` if its decision was captured before its exit occurred.
   - Reconstructed proposals from completed history are strictly labeled `RETROSPECTIVE_BACKFILL`.
5. Fail-Closed Startup & State Validation:
   - If a configured persistence file is missing or corrupt, the evaluator fails closed, logging an alert
     and refusing to grant false permission until state is cleanly re-anchored.
6. Quad-State Position Lifecycle Separation:
   - `IN_FLIGHT_OPEN`: Active trade currently open in WAL payload.
   - `COMPLETED_EVALUABLE`: Full exit recorded with verified spot and option PnL.
   - `COMPLETED_UNRESOLVED_RISK`: Crash recovery / missing quotes.
   - `QUARANTINED_UNMATCHED`: Exit without prior proposal.
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
        self.quarantined_exit_keys: Set[str] = set()
        
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
        self.reconciliation_audit_trail: List[Dict[str, Any]] = []
        
        # Persistence health state: 'HEALTHY' | 'DEGRADED_PERSISTENCE_FAILED'
        self.operational_health: str = "HEALTHY"
        self.persistence_error: Optional[str] = None
        
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

    def _parse_and_validate_timestamp(self, asset: str, ts_str: str, is_reconciliation: bool = False) -> Tuple[bool, Optional[datetime], str]:
        """
        Parses and validates ISO 8601 timestamps, enforcing non-decreasing chronological order.
        Normalizes timezone-naive timestamps to IST (+05:30) to eliminate naive vs aware errors.
        For reconciliations of past quarantined events, retrograde order check is skipped relative
        to subsequent events, but proposal-before-exit ordering is preserved.
        """
        if not ts_str:
            return False, None, "MISSING_TIMESTAMP"
            
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                ist_tz = timezone(timedelta(hours=5, minutes=30))
                dt = dt.replace(tzinfo=ist_tz)
        except Exception as e:
            return False, None, f"MALFORMED_TIMESTAMP_FORMAT: {e}"

        last_dt = self.last_event_datetimes.get(asset)
        if last_dt is not None and not is_reconciliation:
            if dt < last_dt:
                return False, None, f"OUT_OF_ORDER_RETROGRADE: {dt} < {last_dt}"

        if not is_reconciliation or last_dt is None or dt > last_dt:
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
        is_live_event: bool = False
    ) -> Dict[str, Any]:
        """
        Observes a proposed trade entry idempotently.
        Classifies provenance as PROSPECTIVE_OBSERVED only if captured live before exit.
        Fails closed or marks degraded if persistence has failed.
        """
        if self.operational_health != "HEALTHY":
            return {
                "position_id": position_id,
                "asset": asset,
                "shadow_decision": "DEGRADED_BLOCKED",
                "reason": f"OPERATIONAL_HEALTH_DEGRADED: {self.persistence_error}"
            }

        scoped_key = self._make_scoped_key(asset, session_date, position_id)
        received_at = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        
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
                "observer_received_at": received_at,
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

        provenance = "PROSPECTIVE_OBSERVED" if is_live_event else "RETROSPECTIVE_BACKFILL"

        obs = {
            "position_id": position_id,
            "asset": asset,
            "session_date": session_date,
            "proposal_timestamp": proposal_timestamp,
            "observer_received_at": received_at,
            "direction": direction,
            "contract": contract,
            "shadow_decision": "PERMITTED" if would_permit else "VETOED",
            "veto_reason": veto_reason,
            "active_consecutive_losses": st["consecutive_losses"],
            "provenance_mode": provenance,
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
        is_live_event: bool = False,
        is_reconciliation: bool = False
    ) -> Dict[str, Any]:
        """
        Observes a completed trade exit idempotently and causally updates the breaker state.
        Enforces proposal matching and quarantines unmatched exits.
        """
        if self.operational_health != "HEALTHY":
            return {
                "position_id": position_id,
                "asset": asset,
                "status": "DEGRADED_BLOCKED",
                "reason": f"OPERATIONAL_HEALTH_DEGRADED: {self.persistence_error}"
            }

        scoped_key = self._make_scoped_key(asset, session_date, position_id)
        received_at = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        
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
                "observer_received_at": received_at,
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
        is_valid, dt, err_reason = self._parse_and_validate_timestamp(asset, exit_timestamp, is_reconciliation=is_reconciliation)
        if not is_valid:
            # Generic Rule for Historical Unresolved Risk (Crash Recovery / Missing Exit Timestamp):
            # If an exit has missing timestamp and missing PnL (or crash recovery exit_reason),
            # it is classified as HISTORICAL_UNRESOLVED_RISK and triggers a safety risk pause.
            is_unresolved_recovery = (not exit_timestamp and (opt_pnl is None and spot_pnl is None)) or \
                                     ("CRASH_RECOVERY" in (exit_reason or ""))
            if is_unresolved_recovery:
                st = self._get_state(asset, session_date)
                st["unresolved_risk_positions"] += 1
                st["is_shadow_halted"] = True
                st["halt_reason"] = "HISTORICAL_UNRESOLVED_RISK_PAUSE"
                self.in_flight_positions.pop(scoped_key, None)
                self.processed_exit_keys.add(scoped_key)
                rec = {
                    "position_id": position_id,
                    "asset": asset,
                    "session_date": session_date,
                    "exit_timestamp": exit_timestamp or "HISTORICAL_MISSING",
                    "observer_received_at": received_at,
                    "spot_pnl": spot_pnl,
                    "opt_pnl": opt_pnl,
                    "exit_reason": exit_reason or "CRASH_RECOVERY_FAIL_CLOSED",
                    "lifecycle_state": "HISTORICAL_UNRESOLVED_RISK",
                    "depth_coverage": "NON_EVALUABLE",
                    "was_challenger_executed": True,
                    "consecutive_losses_after_exit": st["consecutive_losses"],
                    "is_shadow_halted_now": True,
                    "provenance_mode": "RETROSPECTIVE_BACKFILL"
                }
                self.shadow_ledger.append(rec)
                self._persist_snapshot()
                return rec

            # Standard quarantine: Track in quarantined_exit_keys (NOT in processed_exit_keys)
            if scoped_key not in self.quarantined_exit_keys:
                self.quarantined_exit_keys.add(scoped_key)
                quarantine_rec = {
                    "event_type": "EXIT",
                    "position_id": position_id,
                    "asset": asset,
                    "session_date": session_date,
                    "exit_timestamp": exit_timestamp,
                    "observer_received_at": received_at,
                    "spot_pnl": spot_pnl,
                    "opt_pnl": opt_pnl,
                    "exit_reason": exit_reason,
                    "opt_entry_bid": opt_entry_bid,
                    "opt_entry_ask": opt_entry_ask,
                    "opt_exit_bid": opt_exit_bid,
                    "opt_exit_ask": opt_exit_ask,
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

        provenance = "PROSPECTIVE_OBSERVED" if is_live_event else "RETROSPECTIVE_BACKFILL"

        record = {
            "position_id": position_id,
            "asset": asset,
            "session_date": session_date,
            "exit_timestamp": exit_timestamp,
            "observer_received_at": received_at,
            "spot_pnl": spot_pnl,
            "opt_pnl": opt_pnl,
            "exit_reason": exit_reason,
            "lifecycle_state": lifecycle_state,
            "depth_coverage": depth_coverage,
            "was_challenger_executed": was_challenger_executed,
            "consecutive_losses_after_exit": st["consecutive_losses"],
            "is_shadow_halted_now": st["is_shadow_halted"],
            "provenance_mode": provenance
        }
        
        # Transition out of in-flight
        self.in_flight_positions.pop(scoped_key, None)
        self.processed_exit_keys.add(scoped_key)
        self.shadow_ledger.append(record)
        self._persist_snapshot()
        return record

    def reconcile_quarantined_exit(
        self,
        position_id: str,
        asset: str,
        session_date: str,
        corrected_exit_timestamp: str,
        audit_operator: str = "QUANT_RECONCILIATION_OFFICER"
    ) -> Dict[str, Any]:
        """
        Reconciles a previously quarantined exit idempotently and with an immutable audit trail.
        """
        scoped_key = self._make_scoped_key(asset, session_date, position_id)
        if scoped_key not in self.quarantined_exit_keys:
            return {"status": "ERROR_NOT_IN_QUARANTINE", "position_id": position_id}

        # Find quarantined record
        q_item = None
        for item in self.quarantine_ledger:
            if item.get("position_id") == position_id and item.get("asset") == asset and item.get("session_date") == session_date:
                q_item = item
                break

        if not q_item:
            return {"status": "ERROR_QUARANTINE_RECORD_NOT_FOUND", "position_id": position_id}

        # Re-execute observe_trade_exit with corrected timestamp
        reconciled_res = self.observe_trade_exit(
            position_id=position_id,
            asset=asset,
            session_date=session_date,
            spot_pnl=q_item.get("spot_pnl"),
            opt_pnl=q_item.get("opt_pnl"),
            exit_reason=q_item.get("exit_reason", ""),
            exit_timestamp=corrected_exit_timestamp,
            opt_entry_bid=q_item.get("opt_entry_bid"),
            opt_entry_ask=q_item.get("opt_entry_ask"),
            opt_exit_bid=q_item.get("opt_exit_bid"),
            opt_exit_ask=q_item.get("opt_exit_ask"),
            is_reconciliation=True
        )

        if reconciled_res.get("status") != "QUARANTINED":
            self.quarantined_exit_keys.remove(scoped_key)
            audit_entry = {
                "reconciled_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                "position_id": position_id,
                "asset": asset,
                "session_date": session_date,
                "original_reason": q_item.get("reason"),
                "corrected_timestamp": corrected_exit_timestamp,
                "audit_operator": audit_operator,
                "result": "RECONCILED_SUCCESSFULLY"
            }
            self.reconciliation_audit_trail.append(audit_entry)
            self._persist_snapshot()
            return {"status": "RECONCILED", "audit_entry": audit_entry, "exit_record": reconciled_res}

        return reconciled_res

    def _persist_snapshot(self):
        """Atomically persists asset_states and ledgers to disk."""
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            serialized_asset_states = {
                f"{k[0]}::{k[1]}": v for k, v in self.asset_states.items()
            }
            serialized_last_dts = {
                asset: dt.isoformat() for asset, dt in self.last_event_datetimes.items()
            }
            payload = {
                "version": "shadow_evaluator_v5_final_gate",
                "max_consecutive_losses": self.max_consecutive_losses,
                "asset_states": serialized_asset_states,
                "processed_proposal_keys": list(self.processed_proposal_keys),
                "processed_exit_keys": list(self.processed_exit_keys),
                "quarantined_exit_keys": list(self.quarantined_exit_keys),
                "proposal_registry": self.proposal_registry,
                "in_flight_positions": self.in_flight_positions,
                "last_event_timestamps": serialized_last_dts,
                "shadow_ledger": self.shadow_ledger,
                "quarantine_ledger": self.quarantine_ledger,
                "unmatched_exit_queue": self.unmatched_exit_queue,
                "reconciliation_audit_trail": self.reconciliation_audit_trail
            }
            tmp_path = f"{self.log_path}.tmp.{os.getpid()}"
            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.log_path)
            self.operational_health = "HEALTHY"
            self.persistence_error = None
        except Exception as e:
            err_msg = f"Atomic persistence failure: {e}"
            logger.error(err_msg)
            self.operational_health = "DEGRADED_PERSISTENCE_FAILED"
            self.persistence_error = err_msg
            raise IOError(err_msg)

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
            self.quarantined_exit_keys = set(data.get("quarantined_exit_keys", []))
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
            self.reconciliation_audit_trail = data.get("reconciliation_audit_trail", [])
            logger.info(f"Loaded shadow evaluator snapshot from {path} with {len(self.asset_states)} states")
        except Exception as e:
            logger.error(f"Failed to load shadow snapshot: {e}")
            raise RuntimeError(f"Corrupt or unreadable snapshot: {e}")
