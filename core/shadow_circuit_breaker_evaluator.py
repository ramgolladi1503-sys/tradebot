"""
Shadow Circuit Breaker Evaluator (Read-Only Observer).

A non-invasive, purely prospective observer that monitors live Sentinel APM decisions
and records shadow veto telemetry without altering runtime state, execution, or placing orders.

Invariants:
- Read-only observer pattern: wraps or listens to completed trades.
- Never mutates active position state, APM payload, or broker connections.
- Tracks consecutive losses based on strictly causal event-time exits.
- Emits shadow evaluations: what a pre-frozen L-loss circuit breaker WOULD have blocked.
- Unknown / unresolved exits (pnl_pts is None) are preserved as UNRESOLVED_RISK and do not count as wins.
"""

from typing import Dict, Any, List, Optional
import os
import json
import logging

logger = logging.getLogger("sentinel.shadow_evaluator")

class ShadowCircuitBreakerEvaluator:
    def __init__(self, max_consecutive_losses: int = 2, log_path: Optional[str] = None):
        self.max_consecutive_losses = max_consecutive_losses
        self.log_path = log_path
        # State tracked per (asset, session_date)
        self.asset_states: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.shadow_ledger: List[Dict[str, Any]] = []

    def _get_state(self, asset: str, session_date: str) -> Dict[str, Any]:
        k = (asset, session_date)
        if k not in self.asset_states:
            self.asset_states[k] = {
                "consecutive_losses": 0,
                "is_shadow_halted": False
            }
        return self.asset_states[k]

    def observe_trade_proposal(self, position_id: str, asset: str, session_date: str, direction: str, contract: str) -> Dict[str, Any]:
        """
        Observes a proposed trade entry from Sentinel and evaluates whether the shadow breaker
        would have permitted or vetoed it. Does NOT alter the live trade.
        """
        st = self._get_state(asset, session_date)
        would_permit = not st["is_shadow_halted"]
        veto_reason = f"SHADOW_CHOP_CIRCUIT_BREAKER_L{self.max_consecutive_losses}" if st["is_shadow_halted"] else None
        
        obs = {
            "position_id": position_id,
            "asset": asset,
            "session_date": session_date,
            "direction": direction,
            "contract": contract,
            "shadow_decision": "PERMITTED" if would_permit else "VETOED",
            "veto_reason": veto_reason,
            "active_consecutive_losses": st["consecutive_losses"],
        }
        return obs

    def observe_trade_exit(
        self,
        position_id: str,
        asset: str,
        session_date: str,
        spot_pnl: Optional[float],
        opt_pnl: Optional[float],
        exit_reason: str,
        opt_entry_bid: Optional[float] = None,
        opt_entry_ask: Optional[float] = None,
        opt_exit_bid: Optional[float] = None,
        opt_exit_ask: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Observes a completed trade exit from APM WAL and updates the shadow loss counter causally.
        """
        st = self._get_state(asset, session_date)
        
        # Rigorous exit evaluation:
        # Unknown/missing PnL is UNRESOLVED_RISK - never assume win or zero loss
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
            "spot_pnl": spot_pnl,
            "opt_pnl": opt_pnl,
            "exit_reason": exit_reason,
            "eval_status": eval_status,
            "depth_coverage": depth_coverage,
            "consecutive_losses_after_exit": st["consecutive_losses"],
            "is_shadow_halted_now": st["is_shadow_halted"]
        }
        self.shadow_ledger.append(record)
        self._persist_snapshot()
        return record

    def _check_date_transition(self, session_date: str):
        if self.current_session_date != session_date:
            self.current_session_date = session_date
            self.consecutive_losses = 0
            self.is_shadow_halted = False

    def _persist_snapshot(self):
        if self.log_path:
            try:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                with open(self.log_path, "w") as f:
                    json.dump({
                        "max_consecutive_losses": self.max_consecutive_losses,
                        "current_session_date": self.current_session_date,
                        "consecutive_losses": self.consecutive_losses,
                        "is_shadow_halted": self.is_shadow_halted,
                        "shadow_ledger": self.shadow_ledger
                    }, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to persist shadow snapshot: {e}")
