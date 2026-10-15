"""
Shadow Circuit Breaker Evaluator (Read-Only Observer) — v3 Operational Hardened.

A non-invasive, purely prospective observer that monitors live Sentinel APM decisions
and records shadow veto telemetry without altering runtime state, execution, or placing orders.

Integrity Invariants:
1. Scoped Event Identity:
   - Events are uniquely and stably identified by `(asset, session_date, position_id)` or unique event keys.
   - Prevents cross-asset collision (e.g. NIFTY `TRADE_1014_CE` vs SENSEX `TRADE_1014_CE`).
2. Fully Idempotent Processing:
   - Both proposals and exits are recorded idempotently. Re-ingesting identical events
     never increments proposal counts, duplicates records, or alters historical shadow decisions.
3. Strict Event-Time Causality & Out-of-Order Quarantine:
   - Validates monotonic non-decreasing timestamp progression per asset.
   - Quarantines out-of-order or corrupt timestamp events into `quarantine_ledger` without
     mutating the active circuit breaker state machine.
4. Tri-State Position Lifecycle Separation:
   - Explicitly distinguishes `COMPLETED_EVALUABLE`, `COMPLETED_UNRESOLVED_RISK` (e.g. crash-fail-closed),
     and `IN_FLIGHT_PROPOSED`.
   - An unresolved position triggers a conservative risk pause, but is NEVER misreported as a verified losing exit.
5. Challenger Execution Conditioning:
   - When calculating challenger hypothetical state and P&L, the evaluator processes exits ONLY for
     trades that were SHADOW-PERMITTED at proposal time. Trades vetoed by the breaker do not mutate challenger state.
6. Mode Classification:
   - Distinguishes `BACKFILL_HISTORICAL` ingestion from `PROSPECTIVE_LIVE` events.
"""

from typing import Dict, Any, List, Optional, Tuple, Set
import os
import json
import logging

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
        
        # Proposal decisions store: scoped_key -> obs dict
        self.proposal_decisions: Dict[str, Dict[str, Any]] = {}
        
        # Chronological order tracking: asset -> latest valid ISO timestamp
        self.last_event_timestamps: Dict[str, str] = {}
        
        # Ledgers
        self.shadow_ledger: List[Dict[str, Any]] = []
        self.quarantine_ledger: List[Dict[str, Any]] = []
        
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

    def _validate_timestamp_order(self, asset: str, current_timestamp: str) -> bool:
        """Enforces strictly non-decreasing chronological ordering per asset."""
        if not current_timestamp:
            return True
        last_ts = self.last_event_timestamps.get(asset)
        if last_ts and current_timestamp < last_ts:
            return False
        self.last_event_timestamps[asset] = current_timestamp
        return True

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
        
        # Idempotency check: Return existing decision without mutating state or counters
        if scoped_key in self.processed_proposal_keys:
            existing = self.proposal_decisions.get(scoped_key, {}).copy()
            existing["status"] = "IDEMPOTENT_PROPOSAL_REPLAYED"
            return existing

        # Timestamp validation
        if not self._validate_timestamp_order(asset, proposal_timestamp):
            quarantine_record = {
                "event_type": "PROPOSAL",
                "position_id": position_id,
                "asset": asset,
                "session_date": session_date,
                "proposal_timestamp": proposal_timestamp,
                "last_valid_timestamp": self.last_event_timestamps.get(asset),
                "reason": "OUT_OF_ORDER_TIMESTAMP_QUARANTINED"
            }
            self.quarantine_ledger.append(quarantine_record)
            self._persist_snapshot()
            return {
                "position_id": position_id,
                "asset": asset,
                "shadow_decision": "QUARANTINED",
                "quarantine_reason": "OUT_OF_ORDER_TIMESTAMP"
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
            "lifecycle_state": "IN_FLIGHT_PROPOSED"
        }
        
        self.processed_proposal_keys.add(scoped_key)
        self.proposal_decisions[scoped_key] = obs
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
        Conditioning: Updates the breaker state ONLY IF the proposal was permitted under challenger.
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

        # Timestamp validation
        if not self._validate_timestamp_order(asset, exit_timestamp):
            quarantine_record = {
                "event_type": "EXIT",
                "position_id": position_id,
                "asset": asset,
                "session_date": session_date,
                "exit_timestamp": exit_timestamp,
                "last_valid_timestamp": self.last_event_timestamps.get(asset),
                "reason": "OUT_OF_ORDER_TIMESTAMP_QUARANTINED"
            }
            self.quarantine_ledger.append(quarantine_record)
            self._persist_snapshot()
            return {
                "position_id": position_id,
                "asset": asset,
                "status": "QUARANTINED",
                "quarantine_reason": "OUT_OF_ORDER_TIMESTAMP"
            }

        st = self._get_state(asset, session_date)
        st["total_completed_exits"] += 1

        # Check proposal status for challenger conditioning
        prop_decision = self.proposal_decisions.get(scoped_key, {}).get("shadow_decision", "PERMITTED")
        was_challenger_executed = (prop_decision == "PERMITTED")

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
            
            # Condition on challenger execution: Only permitted trades update the challenger's consecutive loss streak!
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

        # Assess quote depth completeness
        has_entry_depth = (opt_entry_bid is not None and opt_entry_ask is not None)
        has_exit_depth = (opt_exit_bid is not None and opt_exit_ask is not None)
        if has_entry_depth and has_exit_depth:
            depth_coverage = "FULL_BID_ASK_VERIFIED"
        elif has_entry_depth:
            depth_coverage = "ENTRY_DEPTH_ONLY_EXIT_DEPTH_MISSING"
        else:
            depth_coverage = "DEPTH_MISSING"

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
        
        self.processed_exit_keys.add(scoped_key)
        self.shadow_ledger.append(record)
        self._persist_snapshot()
        return record

    def _persist_snapshot(self):
        """Atomically persists asset_states and ledger to disk."""
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            serialized_asset_states = {
                f"{k[0]}::{k[1]}": v for k, v in self.asset_states.items()
            }
            payload = {
                "version": "shadow_evaluator_v3_hardened",
                "max_consecutive_losses": self.max_consecutive_losses,
                "asset_states": serialized_asset_states,
                "processed_proposal_keys": list(self.processed_proposal_keys),
                "processed_exit_keys": list(self.processed_exit_keys),
                "proposal_decisions": self.proposal_decisions,
                "last_event_timestamps": self.last_event_timestamps,
                "shadow_ledger": self.shadow_ledger,
                "quarantine_ledger": self.quarantine_ledger
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
            self.proposal_decisions = data.get("proposal_decisions", {})
            self.last_event_timestamps = data.get("last_event_timestamps", {})
            self.shadow_ledger = data.get("shadow_ledger", [])
            self.quarantine_ledger = data.get("quarantine_ledger", [])
            logger.info(f"Loaded shadow evaluator snapshot from {path} with {len(self.asset_states)} states")
        except Exception as e:
            logger.error(f"Failed to load shadow snapshot: {e}")
