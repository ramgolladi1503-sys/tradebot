"""Broker Position Reconciler
==========================
Pre-reset and boot reconciliation engine that audits broker open positions
before permitting APM state resets or fail-closed purges.

If an open position exists on the broker:
- Prevents destructive WAL wiping or cold cooldowns.
- Re-attaches APM into STATE_IN_FLIGHT with active trailing stops preserved.
- Restores in-memory position state for seamless continuous tracking.

Safety Invariants:
- read_only = True (does not place, modify, or cancel orders)
- is_order_action = False
- broker_api_called = True (read-only portfolio inspection)
- allowed_for_live_execution = False
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union

logger = logging.getLogger(__name__)


class PositionQueryableBroker(Protocol):
    """Protocol for brokers providing read-only position fetching."""
    def fetch_open_positions(self) -> List[Dict[str, Any]]:
        ...


@dataclass
class ReconciledPosition:
    symbol: str
    instrument_token: str
    net_qty: int
    avg_price: float
    side: str
    index_name: str
    entry_time: str
    target_pts: float
    sl_pts: float
    highest_price: float
    status: str  # "REATTACHED", "ALREADY_TRACKED", "ORPHANED_ALERT"


@dataclass
class ReconciliationResult:
    has_open_positions: bool
    open_positions: List[ReconciledPosition]
    wal_reset_permitted: bool
    reattached_apm: bool
    message: str
    status: str = "OK"  # "OK", "ERROR_FAIL_CLOSED", "ACTIVE_DETECTED"
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = True
    allowed_for_live_execution: bool = False


class BrokerPositionReconciler:
    """Audits broker positions before WAL resets or APM re-initialization."""

    def __init__(self, broker: Optional[PositionQueryableBroker] = None):
        self.broker = broker

    def fetch_broker_positions(self) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """Safely fetches open positions from broker adapter.
        
        Returns:
            Tuple[bool, List[Dict[str, Any]], Optional[str]]:
            (success, open_positions_list, error_message)
        """
        if not self.broker:
            logger.warning("[BrokerPositionReconciler] No broker adapter configured.")
            return True, [], None
        try:
            raw_positions = self.broker.fetch_open_positions()
            if not isinstance(raw_positions, list):
                err = f"Unexpected position payload type: {type(raw_positions)}"
                logger.error(f"[BrokerPositionReconciler] {err}")
                return False, [], err
            
            # Filter for active non-zero net positions
            open_positions = []
            for pos in raw_positions:
                qty = int(pos.get("net_quantity") or pos.get("quantity") or 0)
                if qty != 0:
                    open_positions.append(pos)
            return True, open_positions, None
        except Exception as e:
            err = f"Error fetching broker positions: {e}"
            logger.error(f"[BrokerPositionReconciler] {err}")
            return False, [], err

    def reconcile_before_wal_reset(
        self,
        wal_path: Union[str, Path],
        index_name: str = "NIFTY",
    ) -> ReconciliationResult:
        """Audits broker before a WAL file can be wiped or reset to STANDBY.
        
        If broker query fails (network timeout, exception):
        - Fails closed: blocks WAL reset (wal_reset_permitted = False, status = "ERROR_FAIL_CLOSED")
        
        If open position found for index:
        - Blocks WAL reset (wal_reset_permitted = False, status = "ACTIVE_DETECTED")
        - Re-attaches or ensures STATE_IN_FLIGHT in WAL
        
        If no open positions and query succeeded:
        - Permits WAL reset (wal_reset_permitted = True, status = "OK")
        """
        wal_file = Path(wal_path)
        success, broker_positions, err_msg = self.fetch_broker_positions()

        # Vector 5 Hardening: Broker query failure MUST fail-closed to prevent wiping WAL during broker disconnect
        if not success:
            return ReconciliationResult(
                has_open_positions=False,
                open_positions=[],
                wal_reset_permitted=False,
                reattached_apm=False,
                status="ERROR_FAIL_CLOSED",
                message=f"Broker position query FAILED ({err_msg}). Fail-closed: WAL reset prohibited.",
            )

        # Find matching positions for this index
        matching_positions: List[Dict[str, Any]] = []
        for pos in broker_positions:
            sym = str(pos.get("trading_symbol") or pos.get("symbol") or "")
            inst = str(pos.get("instrument_token") or "")
            if index_name.upper() in sym.upper() or index_name.upper() in inst.upper():
                matching_positions.append(pos)

        if not matching_positions:
            return ReconciliationResult(
                has_open_positions=False,
                open_positions=[],
                wal_reset_permitted=True,
                reattached_apm=False,
                status="OK",
                message=f"No open broker positions detected for {index_name}. Safe to reset WAL.",
            )

        # Active positions exist on broker! Prohibit destructive reset
        reconciled_list: List[ReconciledPosition] = []
        for p in matching_positions:
            qty = int(p.get("net_quantity") or p.get("quantity") or 0)
            avg_price = float(p.get("average_price") or p.get("buy_price") or 0.0)
            sym = str(p.get("trading_symbol") or p.get("symbol") or "")
            inst = str(p.get("instrument_token") or "")
            
            reconciled = ReconciledPosition(
                symbol=sym,
                instrument_token=inst,
                net_qty=qty,
                avg_price=avg_price,
                side="BUY" if qty > 0 else "SELL",
                index_name=index_name,
                entry_time=datetime.now(timezone.utc).isoformat(),
                target_pts=round(avg_price * 0.20, 2),  # Default 20% target if unstated
                sl_pts=round(avg_price * 0.15, 2),      # Default 15% stop if unstated
                highest_price=avg_price,
                status="REATTACHED",
            )
            reconciled_list.append(reconciled)

        # Re-attach into WAL: Ensure state is STATE_IN_FLIGHT with position payload
        reattached = self.reattach_to_wal(wal_file, reconciled_list[0])

        return ReconciliationResult(
            has_open_positions=True,
            open_positions=reconciled_list,
            wal_reset_permitted=False,
            reattached_apm=reattached,
            status="ACTIVE_DETECTED",
            message=f"ACTIVE POSITION DETECTED on broker for {index_name} ({reconciled_list[0].symbol}, Qty: {reconciled_list[0].net_qty}). WAL reset BLOCKED; re-attached into STATE_IN_FLIGHT.",
        )

    def reattach_to_wal(self, wal_file: Path, reconciled_pos: ReconciledPosition) -> bool:
        """Modifies or writes WAL file to STATE_IN_FLIGHT preserving position payload and trailing stops."""
        try:
            wal_file.parent.mkdir(parents=True, exist_ok=True)
            existing_data: Dict[str, Any] = {}
            if wal_file.exists():
                try:
                    with open(wal_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception:
                    existing_data = {}

            # If existing WAL already had valid trailing stops or payload, preserve them
            existing_payload = existing_data.get("payload") or {}
            entry_price = float(existing_payload.get("entry_price") or reconciled_pos.avg_price)
            sl_pts = float(existing_payload.get("opt_sl_pts") or existing_payload.get("sl_pts") or reconciled_pos.sl_pts)
            target_pts = float(existing_payload.get("opt_target_pts") or existing_payload.get("target_pts") or reconciled_pos.target_pts)
            direction = "CE" if "CE" in reconciled_pos.symbol else "PE"
            pos_id = existing_payload.get("position_id") or f"POS_{reconciled_pos.index_name}_{int(datetime.now().timestamp())}"

            new_payload = {
                "position_id": pos_id,
                "direction": direction,
                "strike_contract": reconciled_pos.symbol,
                "symbol": reconciled_pos.symbol,
                "entry_price": entry_price,
                "entry_time": existing_payload.get("entry_time") or reconciled_pos.entry_time,
                "current_sl": max(0.0, entry_price - sl_pts if direction == "CE" else entry_price + sl_pts),
                "initial_sl": max(0.0, entry_price - sl_pts if direction == "CE" else entry_price + sl_pts),
                "target_price": round(entry_price + target_pts if direction == "CE" else entry_price - target_pts, 2),
                "opt_symbol": reconciled_pos.symbol,
                "opt_token": reconciled_pos.instrument_token,
                "opt_entry_ltp": entry_price,
                "opt_current_ltp": entry_price,
                "opt_target_pts": target_pts,
                "opt_sl_pts": sl_pts,
                "highest_price": max(entry_price, float(existing_payload.get("highest_price") or entry_price)),
                "lots": 1,
                "total_quantity": abs(reconciled_pos.net_qty),
                "reconciled": True,
                "reconciled_at": datetime.now(timezone.utc).isoformat(),
            }

            wal_data = {
                "state": "IN_FLIGHT",
                "payload": new_payload,
                "last_completed_trade": existing_data.get("last_completed_trade"),
                "trade_history": existing_data.get("trade_history", []),
                "cool_off_until": None,
                "cool_off_ref_spot": None,
                "cool_off_direction": None,
                "session_date": datetime.now().strftime("%Y-%m-%d"),
                "persisted_at": datetime.now(timezone.utc).isoformat(),
                "recovery_source": "BROKER_POSITION_RECONCILER",
            }

            tmp_path = wal_file.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(wal_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, wal_file)
            logger.info(f"[BrokerPositionReconciler] Successfully reattached {wal_file} to STATE_IN_FLIGHT")
            return True
        except Exception as e:
            logger.error(f"[BrokerPositionReconciler] Failed to reattach WAL: {e}")
            return False

    def reattach_apm_instance(self, apm_instance: Any, index_name: str = "NIFTY") -> bool:
        """Directly re-attaches an active in-memory ActivePositionManager instance if broker has open position."""
        success, broker_positions, _ = self.fetch_broker_positions()
        if not success:
            return False
        matching = [
            p for p in broker_positions
            if index_name.upper() in str(p.get("trading_symbol") or "").upper()
        ]
        if not matching:
            return False

        pos = matching[0]
        qty = int(pos.get("net_quantity") or pos.get("quantity") or 0)
        avg_price = float(pos.get("average_price") or pos.get("buy_price") or 0.0)
        sym = str(pos.get("trading_symbol") or pos.get("symbol") or "")

        # Set APM state directly into STATE_IN_FLIGHT
        from core.active_position_manager import STATE_IN_FLIGHT, PositionPayload
        
        direction = "CE" if "CE" in sym else "PE"
        target_pts = round(avg_price * 0.20, 2)
        sl_pts = round(avg_price * 0.15, 2)
        target_price = round(avg_price + target_pts if direction == "CE" else avg_price - target_pts, 2)
        initial_sl = max(0.0, avg_price - sl_pts if direction == "CE" else avg_price + sl_pts)

        apm_instance.state = STATE_IN_FLIGHT
        apm_instance.cool_off_until = None
        apm_instance.payload = PositionPayload(
            position_id=f"POS_{index_name}_{int(datetime.now().timestamp())}",
            direction=direction,
            strike_contract=sym,
            entry_price=avg_price,
            entry_time=datetime.now(timezone.utc).isoformat(),
            current_sl=initial_sl,
            initial_sl=initial_sl,
            target_price=target_price,
            opt_symbol=sym,
            opt_entry_ltp=avg_price,
            opt_current_ltp=avg_price,
            opt_target_pts=target_pts,
            opt_sl_pts=sl_pts,
            lots=1,
            total_quantity=abs(qty),
        )
        if hasattr(apm_instance, "_persist_wal_atomic"):
            apm_instance._persist_wal_atomic(force_sync=True)
        return True
