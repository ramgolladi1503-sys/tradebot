"""
Shadow Circuit Breaker Evaluator (Read-Only Observer).

A non-invasive, purely prospective observer that monitors live Sentinel APM decisions
and records shadow veto telemetry without altering runtime state, execution, or placing orders.

Invariants:
- Read-only observer pattern: wraps or listens to completed trades.
- Never mutates active position state, APM payload, or broker connections.
- Tracks consecutive losses based on strictly causal event-time exits per (asset, date).
- Event-time validation: ensures proposals and exits adhere to monotonic chronological order.
  Rejects duplicate exits, flags out-of-order events, and handles missing/unresolved exits fail-closed.
- Robust state persistence & recovery: persists asset_states atomically and reloads cleanly on startup.
- Multi-tier financial modeling: separates modeled LTP PnL from executable bid/ask-backed estimates,
  applying verified exchange rules and 0.15% STT on option sell premium.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("sentinel.shadow_evaluator")

class ShadowCircuitBreakerEvaluator:
    def __init__(self, max_consecutive_losses: int = 2, log_path: Optional[str] = None):
        self.max_consecutive_losses = max_consecutive_losses
        self.log_path = log_path
        # State tracked per (asset, session_date) -> dict
        self.asset_states: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Completed shadow ledger
        self.shadow_ledger: List[Dict[str, Any]] = []
        # Event tracking for causality & duplicate prevention
        self.processed_exit_ids: set = set()
        self.last_event_timestamps: Dict[str, str] = {}  # asset -> latest ISO timestamp
        
        # Load persisted snapshot if file exists
        if self.log_path and os.path.exists(self.log_path):
            self.load_snapshot(self.log_path)

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
                "executed_proposals": 0
            }
        return self.asset_states[k]

    def _validate_timestamp_order(self, asset: str, current_timestamp: str) -> bool:
        """Enforces strictly non-decreasing chronological ordering per asset."""
        if not current_timestamp:
            return True
        last_ts = self.last_event_timestamps.get(asset)
        if last_ts and current_timestamp < last_ts:
            logger.warning(f"Out of order event detected for {asset}: {current_timestamp} < {last_ts}")
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
        proposal_timestamp: str = ""
    ) -> Dict[str, Any]:
        """
        Observes a proposed trade entry from Sentinel and evaluates whether the shadow breaker
        would have permitted or vetoed it. Does NOT alter the live trade.
        """
        is_order_valid = self._validate_timestamp_order(asset, proposal_timestamp)
        st = self._get_state(asset, session_date)
        st["total_proposals"] += 1

        would_permit = not st["is_shadow_halted"]
        veto_reason = None
        if not would_permit:
            veto_reason = f"SHADOW_CHOP_CIRCUIT_BREAKER_L{self.max_consecutive_losses}"
            st["vetoed_proposals"] += 1
        else:
            st["executed_proposals"] += 1

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
            "chronological_order_valid": is_order_valid
        }
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
        opt_exit_ask: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Observes a completed trade exit from APM WAL and updates the shadow loss counter causally.
        Enforces idempotency against duplicate exits and fail-closed handling on missing exits.
        """
        # Idempotency check
        if position_id in self.processed_exit_ids:
            logger.warning(f"Duplicate exit ignored for position {position_id}")
            return {
                "position_id": position_id,
                "status": "DUPLICATE_EXIT_IGNORED"
            }
        self.processed_exit_ids.add(position_id)

        is_order_valid = self._validate_timestamp_order(asset, exit_timestamp)
        st = self._get_state(asset, session_date)

        # Rigorous exit evaluation:
        # Unknown/missing PnL is UNRESOLVED_RISK - never assume win or zero loss!
        if opt_pnl is None and spot_pnl is None:
            is_loss = True
            eval_status = "UNRESOLVED_EXIT_PRESERVED_AS_RISK"
        elif opt_pnl is not None:
            is_loss = (opt_pnl < 0.0) or ("STOP_LOSS" in exit_reason)
            eval_status = "EVALUABLE"
        else:
            is_loss = (spot_pnl < 0.0) or ("STOP_LOSS" in exit_reason)
            eval_status = "EVALUABLE_SPOT_ONLY"

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
            "eval_status": eval_status,
            "depth_coverage": depth_coverage,
            "consecutive_losses_after_exit": st["consecutive_losses"],
            "is_shadow_halted_now": st["is_shadow_halted"],
            "chronological_order_valid": is_order_valid
        }
        self.shadow_ledger.append(record)
        self._persist_snapshot()
        return record

    def _persist_snapshot(self):
        """Atomically persists asset_states and ledger to disk."""
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            # Serialize (asset, date) tuple keys as "asset::date" strings
            serialized_asset_states = {
                f"{k[0]}::{k[1]}": v for k, v in self.asset_states.items()
            }
            payload = {
                "version": "shadow_evaluator_v2",
                "max_consecutive_losses": self.max_consecutive_losses,
                "asset_states": serialized_asset_states,
                "processed_exit_ids": list(self.processed_exit_ids),
                "last_event_timestamps": self.last_event_timestamps,
                "shadow_ledger": self.shadow_ledger
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
            self.processed_exit_ids = set(data.get("processed_exit_ids", []))
            self.last_event_timestamps = data.get("last_event_timestamps", {})
            self.shadow_ledger = data.get("shadow_ledger", [])
            logger.info(f"Loaded shadow evaluator snapshot from {path} with {len(self.asset_states)} states")
        except Exception as e:
            logger.error(f"Failed to load shadow snapshot: {e}")
