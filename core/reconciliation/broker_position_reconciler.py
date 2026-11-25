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
import math
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
    target_pts: Optional[float]
    sl_pts: Optional[float]
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
            return False, [], "UNCONFIGURED_BROKER: Broker adapter is None"
        try:
            raw_positions = self.broker.fetch_open_positions()
            if not isinstance(raw_positions, list):
                err = f"Unexpected position payload type: {type(raw_positions)}"
                logger.error(f"[BrokerPositionReconciler] {err}")
                return False, [], err
            
            # Any malformed row makes the account snapshot incomplete. Do not
            # drop it and then authorize a destructive reset from partial data.
            open_positions = []
            for row_number, pos in enumerate(raw_positions):
                if not isinstance(pos, dict):
                    return False, [], f"Unclassifiable broker position row {row_number}"
                symbol = str(pos.get("trading_symbol") or pos.get("symbol") or "").strip()
                if not symbol:
                    return False, [], f"Broker position row {row_number} has no symbol identity"
                raw_qty = pos.get("net_quantity")
                if raw_qty is None:
                    raw_qty = pos.get("quantity")
                try:
                    if isinstance(raw_qty, bool) or raw_qty is None:
                        raise ValueError("missing or boolean quantity")
                    numeric_qty = float(raw_qty)
                    if not math.isfinite(numeric_qty) or not numeric_qty.is_integer():
                        raise ValueError("quantity must be a finite integer")
                    qty = int(numeric_qty)
                except (TypeError, ValueError, OverflowError):
                    return False, [], f"Broker position row {row_number} has invalid quantity"
                if qty != 0:
                    raw_average = pos.get("average_price") or pos.get("buy_price")
                    try:
                        average_price = float(raw_average)
                        if not math.isfinite(average_price) or average_price <= 0:
                            raise ValueError("average price must be finite and positive")
                    except (TypeError, ValueError, OverflowError):
                        return False, [], f"Broker position row {row_number} has invalid average price"
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
        if not self.broker:
            return ReconciliationResult(
                has_open_positions=False,
                open_positions=[],
                wal_reset_permitted=False,
                reattached_apm=False,
                message="BLOCKED_FAIL_CLOSED: Broker adapter is unconfigured",
                status="UNCONFIGURED_BROKER",
            )

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

        # Match the canonical index prefix only. Substring matching can make
        # NIFTY match BANKNIFTY and can mistake opaque tokens for identity.
        matching_positions: List[Dict[str, Any]] = []
        for pos in broker_positions:
            sym = str(pos.get("trading_symbol") or pos.get("symbol") or "")
            normalized = sym.upper().strip()
            requested = index_name.upper().strip()
            if normalized == requested or normalized.startswith(requested + " ") or normalized.startswith(requested + "-") or normalized.startswith(requested + "_"):
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

        # Risk parameters may only be restored from the matching persisted
        # position. Never manufacture target/stop values during recovery.
        existing_payload: Dict[str, Any] = {}
        try:
            if wal_file.exists():
                with open(wal_file, "r", encoding="utf-8") as f:
                    existing_payload = (json.load(f).get("payload") or {})
        except Exception:
            existing_payload = {}

        reconciled_list: List[ReconciledPosition] = []
        for p in matching_positions:
            qty = int(p.get("net_quantity") or p.get("quantity") or 0)
            avg_price = float(p.get("average_price") or p.get("buy_price") or 0.0)
            sym = str(p.get("trading_symbol") or p.get("symbol") or "")
            inst = str(p.get("instrument_token") or "")
            existing_matches_position = str(existing_payload.get("symbol") or existing_payload.get("strike_contract") or "") == sym
            target_value = existing_payload.get("opt_target_pts", existing_payload.get("target_pts")) if existing_matches_position else None
            stop_value = existing_payload.get("opt_sl_pts", existing_payload.get("sl_pts")) if existing_matches_position else None
            try:
                target_pts = float(target_value) if target_value is not None else None
                sl_pts = float(stop_value) if stop_value is not None else None
                if target_pts is not None and (not math.isfinite(target_pts) or target_pts <= 0):
                    target_pts = None
                if sl_pts is not None and (not math.isfinite(sl_pts) or sl_pts <= 0):
                    sl_pts = None
            except (TypeError, ValueError):
                target_pts = sl_pts = None
            
            reconciled = ReconciledPosition(
                symbol=sym,
                instrument_token=inst,
                net_qty=qty,
                avg_price=avg_price,
                side="BUY" if qty > 0 else "SELL",
                index_name=index_name,
                entry_time=datetime.now(timezone.utc).isoformat(),
                target_pts=target_pts,
                sl_pts=sl_pts,
                highest_price=avg_price,
                status="REATTACHED" if target_pts is not None and sl_pts is not None else "ORPHANED_ALERT",
            )
            reconciled_list.append(reconciled)

        # The existing WAL schema holds one position. Do not overwrite it with
        # one arbitrary member of a multi-position broker book.
        reattached = False
        if len(reconciled_list) == 1:
            reattached = self.reattach_to_wal(wal_file, reconciled_list[0])

        return ReconciliationResult(
            has_open_positions=True,
            open_positions=reconciled_list,
            wal_reset_permitted=False,
            reattached_apm=reattached,
            status="ACTIVE_DETECTED",
            message=(f"ACTIVE POSITIONS DETECTED on broker for {index_name} ({len(reconciled_list)} positions). WAL reset BLOCKED; "
                     + ("matching position reattached using persisted risk values." if reattached else
                        "no safe single-position reattachment was possible; persisted state was not replaced.")),
        )

    def reattach_to_wal(self, wal_file: Path, reconciled_pos: ReconciledPosition) -> bool:
        """Modifies or writes WAL file to STATE_IN_FLIGHT preserving position payload and trailing stops."""
        if reconciled_pos.target_pts is None or reconciled_pos.sl_pts is None:
            logger.error("[BrokerPositionReconciler] Missing persisted target/stop values; refusing synthetic recovery payload")
            return False
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
            payload_symbol = str(existing_payload.get("symbol") or existing_payload.get("strike_contract") or "")
            existing_matches_position = payload_symbol == reconciled_pos.symbol
            entry_price = float(existing_payload.get("entry_price") or reconciled_pos.avg_price) if existing_matches_position else float(reconciled_pos.avg_price)
            sl_pts = float(reconciled_pos.sl_pts)
            target_pts = float(reconciled_pos.target_pts)
            direction = "CE" if "CE" in reconciled_pos.symbol else "PE"
            pos_id = (existing_payload.get("position_id") if existing_matches_position else None) or f"POS_{reconciled_pos.index_name}_{int(datetime.now().timestamp())}"
            computed_sl = max(0.0, entry_price - sl_pts if direction == "CE" else entry_price + sl_pts)
            computed_target = round(entry_price + target_pts if direction == "CE" else entry_price - target_pts, 2)
            # A matching persisted trailing stop is more protective state than
            # a recomputed initial stop. Preserve it when it is finite/positive.
            current_sl = existing_payload.get("current_sl") if existing_matches_position else None
            initial_sl = existing_payload.get("initial_sl") if existing_matches_position else None
            target_price = existing_payload.get("target_price") if existing_matches_position else None
            current_sl = float(current_sl) if self._valid_positive(current_sl) else computed_sl
            initial_sl = float(initial_sl) if self._valid_positive(initial_sl) else computed_sl
            target_price = float(target_price) if self._valid_positive(target_price) else computed_target

            new_payload = {
                "position_id": pos_id,
                "direction": direction,
                "strike_contract": reconciled_pos.symbol,
                "symbol": reconciled_pos.symbol,
                "entry_price": entry_price,
                "entry_time": (existing_payload.get("entry_time") if existing_matches_position else None) or reconciled_pos.entry_time,
                "current_sl": current_sl,
                "initial_sl": initial_sl,
                "target_price": target_price,
                "opt_symbol": reconciled_pos.symbol,
                "opt_token": reconciled_pos.instrument_token,
                "opt_entry_ltp": entry_price,
                "opt_current_ltp": entry_price,
                "opt_target_pts": target_pts,
                "opt_sl_pts": sl_pts,
                "highest_price": max(entry_price, float(existing_payload.get("highest_price") or entry_price)) if existing_matches_position else entry_price,
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
        requested = index_name.upper().strip()
        matching = []
        for p in broker_positions:
            symbol = str(p.get("trading_symbol") or p.get("symbol") or "").upper().strip()
            if symbol == requested or symbol.startswith(requested + " ") or symbol.startswith(requested + "-") or symbol.startswith(requested + "_"):
                matching.append(p)
        if not matching:
            return False
        if len(matching) != 1 or apm_instance.payload is None:
            return False

        pos = matching[0]
        qty = int(pos.get("net_quantity") or pos.get("quantity") or 0)
        avg_price = float(pos.get("average_price") or pos.get("buy_price") or 0.0)
        sym = str(pos.get("trading_symbol") or pos.get("symbol") or "")
        payload = apm_instance.payload
        if str(getattr(payload, "opt_symbol", None) or getattr(payload, "strike_contract", "")) != sym:
            return False
        target_pts = getattr(payload, "opt_target_pts", None)
        sl_pts = getattr(payload, "opt_sl_pts", None)
        if not self._valid_positive(target_pts) or not self._valid_positive(sl_pts) or qty == 0 or not self._valid_positive(avg_price):
            return False

        from core.active_position_manager import STATE_IN_FLIGHT
        apm_instance.state = STATE_IN_FLIGHT
        apm_instance.cool_off_until = None
        payload.total_quantity = abs(qty)
        payload.opt_entry_ltp = avg_price
        payload.opt_current_ltp = avg_price
        if hasattr(apm_instance, "_persist_wal_atomic"):
            apm_instance._persist_wal_atomic(force_sync=True)
        return True

    @staticmethod
    def _valid_positive(value: Any) -> bool:
        try:
            return math.isfinite(float(value)) and float(value) > 0
        except (TypeError, ValueError):
            return False
