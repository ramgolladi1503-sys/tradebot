"""GTT Stop Dispatcher
===================
Co-dispatches broker-side Stop Loss order (SL-M or GTT trigger) upon verified entry fill.
Handles cancellation upon normal target exit and fallback local kill-switch if broker API fails.

Safety Invariants:
- read_only = True by default
- is_order_action = False unless explicitly executed via authorized adapter
- broker_api_called = False (or True in live execution mode)
- allowed_for_live_execution = False unless authorized
"""

import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, Union

from core.broker_interface import BrokerOrderRequest

logger = logging.getLogger(__name__)


class StopOrderType(str, Enum):
    GTT = "GTT"
    SL_M = "SL_M"
    SL_L = "SL_L"


@dataclass
class GTTOrderRequest:
    symbol: str
    instrument_token: str
    qty: int
    trigger_price: float
    limit_price: Optional[float] = None
    side: str = "SELL"
    order_type: StopOrderType = StopOrderType.GTT
    index_name: str = "NIFTY"
    parent_order_id: Optional[str] = None


@dataclass
class GTTOrderResponse:
    success: bool
    gtt_order_id: Optional[str] = None
    status: str = "PENDING"  # "ACTIVE", "TRIGGERED", "CANCELLED", "REJECTED", "FALLBACK_LOCAL"
    message: str = ""
    timestamp: str = ""
    fallback_local_kill: bool = False
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


class BrokerGTTAdapter(Protocol):
    """Protocol for brokers providing GTT / Stop-loss order dispatch and cancel."""
    def place_gtt_order(self, request: GTTOrderRequest) -> GTTOrderResponse:
        ...

    def cancel_gtt_order(self, gtt_order_id: str) -> bool:
        ...


class GTTStopDispatcher:
    """Manages broker-side GTT / SL-M orders co-dispatched alongside entry orders."""

    def __init__(
        self,
        broker_adapter: Optional[Any] = None,
        local_kill_switch_cb: Optional[Any] = None,
        abort_fill_cb: Optional[Callable[[str, int, str], Any]] = None,
        enable_live_dispatch: bool = False,
    ):
        self.broker = broker_adapter
        self.local_kill_switch_cb = local_kill_switch_cb
        self.abort_fill_cb = abort_fill_cb
        self.enable_live_dispatch = enable_live_dispatch
        self.active_gtt_orders: Dict[str, GTTOrderRequest] = {}  # gtt_order_id -> GTTOrderRequest
        self.symbol_to_gtt_id: Dict[str, str] = {}  # symbol -> gtt_order_id
        self._stop_reservations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _reservation_key(symbol: str, parent_order_id: Optional[str]) -> str:
        return f"{symbol.strip()}|{str(parent_order_id or '').strip()}"

    def _reserve_stop(self, symbol: str, parent_order_id: Optional[str]) -> Tuple[bool, str]:
        """Reserve a stop identity before transport; unresolved reservations persist."""
        if not isinstance(symbol, str) or not symbol.strip():
            return False, "invalid symbol"
        key = self._reservation_key(symbol, parent_order_id)
        with self._lock:
            for row in self._stop_reservations.values():
                if row.get("state") in {"RESERVED", "UNKNOWN", "SUBMITTED", "ACTIVE"} and (
                    row.get("symbol") == symbol.strip()
                    or (parent_order_id and row.get("parent_order_id") == parent_order_id)
                ):
                    return False, "stop identity already reserved or unresolved"
            self._stop_reservations[key] = {
                "symbol": symbol.strip(), "parent_order_id": parent_order_id, "state": "RESERVED"
            }
        return True, key

    def _set_stop_reservation_state(self, key: str, state: str, order_id: Optional[str] = None) -> None:
        if state not in {"UNKNOWN", "SUBMITTED", "ACTIVE", "CANCELLED", "CANCELED", "REJECTED"}:
            raise ValueError("invalid stop reservation state")
        with self._lock:
            row = self._stop_reservations.get(key)
            if row is None:
                return
            row["state"] = state
            if order_id:
                row["order_id"] = order_id

    @staticmethod
    def _classify_submission_state(status: Any, dedicated_gtt_interface: bool) -> str:
        """A generic order acknowledgment cannot establish a resting GTT state."""
        normalized = str(status or "UNKNOWN").upper()
        if dedicated_gtt_interface and normalized == "ACTIVE":
            return "ACTIVE"
        if normalized in {"REJECTED", "CANCELLED", "CANCELED"}:
            return normalized
        return "UNKNOWN"

    def calculate_stop_trigger(
        self,
        entry_price: float,
        sl_pts: float,
        side: str = "BUY",
        min_tick: float = 0.05,
    ) -> float:
        """Calculates valid stop trigger price rounded to broker tick size (e.g. 0.05)."""
        if side.upper() == "BUY":
            raw_trigger = entry_price - sl_pts
        else:
            raw_trigger = entry_price + sl_pts
        
        # Guard against zero or negative stop price
        raw_trigger = max(min_tick, raw_trigger)
        # Round to nearest 0.05 tick
        rounded = round(raw_trigger / min_tick) * min_tick
        return round(rounded, 2)

    def dispatch_stop_on_entry_fill(
        self,
        index_name: str,
        symbol: str,
        instrument_token: str,
        entry_price: float,
        sl_pts: float,
        qty: int,
        parent_order_id: Optional[str] = None,
        order_type: StopOrderType = StopOrderType.GTT,
    ) -> GTTOrderResponse:
        """Co-dispatches broker-side Stop Loss order upon verified entry fill."""
        trigger_price = self.calculate_stop_trigger(entry_price, sl_pts, side="BUY")
        req = GTTOrderRequest(
            symbol=symbol,
            instrument_token=instrument_token,
            qty=qty,
            trigger_price=trigger_price,
            limit_price=round(trigger_price * 0.95, 2) if order_type != StopOrderType.SL_M else None,
            side="SELL",
            order_type=order_type,
            index_name=index_name,
            parent_order_id=parent_order_id,
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        reserved, reservation_key = self._reserve_stop(symbol, parent_order_id)
        if not reserved:
            return GTTOrderResponse(
                success=False, status="UNKNOWN", message=reservation_key, timestamp=now_iso,
                read_only=True, is_order_action=False, broker_api_called=False,
            )

        # If live dispatch is disabled or no broker adapter, record dry-run / paper stop safely
        if not self.enable_live_dispatch or not self.broker:
            simulated_id = f"GTT_SIM_{index_name}_{int(datetime.now().timestamp())}"
            self.active_gtt_orders[simulated_id] = req
            self.symbol_to_gtt_id[symbol] = simulated_id
            self._set_stop_reservation_state(reservation_key, "ACTIVE", simulated_id)
            logger.info(
                f"[GTTStopDispatcher] Registered paper/simulated stop order {simulated_id} "
                f"for {symbol} @ trigger {trigger_price:.2f}"
            )
            return GTTOrderResponse(
                success=True,
                gtt_order_id=simulated_id,
                status="ACTIVE",
                message="Paper/simulated stop order registered",
                timestamp=now_iso,
                fallback_local_kill=False,
                read_only=True,
                is_order_action=False,
                broker_api_called=False,
            )

        # Attempt broker API dispatch
        try:
            resp: Optional[GTTOrderResponse] = None
            if hasattr(self.broker, "place_gtt_order"):
                resp = self.broker.place_gtt_order(req)
                if resp and resp.success and resp.gtt_order_id:
                    stop_state = self._classify_submission_state(
                        resp.status, dedicated_gtt_interface=True
                    )
                    confirmed_active = stop_state == "ACTIVE"
                    self._set_stop_reservation_state(
                        reservation_key, stop_state, resp.gtt_order_id
                    )
                    if confirmed_active:
                        self.active_gtt_orders[resp.gtt_order_id] = req
                    self.symbol_to_gtt_id[symbol] = resp.gtt_order_id
                    return resp
            elif hasattr(self.broker, "place_order"):
                # Broker adapter supports generic place_order for SL-M / GTT
                mapped_order_type = "SL-M" if req.order_type.value == "SL_M" else ("SL" if req.order_type.value == "SL_L" else req.order_type.value)
                order_req = BrokerOrderRequest(
                    symbol=req.symbol,
                    side=req.side,
                    qty=req.qty,
                    order_type=mapped_order_type,
                    limit_price=req.limit_price,
                    stop_price=req.trigger_price,
                )
                # A TypeError may be raised after a transport side effect. Never
                # retry a broker submission with a second calling convention.
                raw_resp = self.broker.place_order(order_req)
                order_id = getattr(raw_resp, "broker_order_id", None) or getattr(raw_resp, "order_id", None)
                if not order_id or not bool(getattr(raw_resp, "ok", False)):
                    raise RuntimeError(getattr(raw_resp, "reason", None) or "Broker did not confirm GTT submission")
                # Generic order acknowledgment proves submission only, not that
                # a broker-side GTT/stop is resting and active.
                self._set_stop_reservation_state(
                    reservation_key,
                    self._classify_submission_state(getattr(raw_resp, "status", "UNKNOWN"), False),
                    order_id,
                )
                self.symbol_to_gtt_id[symbol] = order_id
                return GTTOrderResponse(
                    success=True,
                    gtt_order_id=order_id,
                    status="SUBMITTED",
                    message="Generic broker acknowledged submission; resting stop state is unverified",
                    timestamp=now_iso,
                    fallback_local_kill=False,
                    read_only=False,
                    is_order_action=True,
                    broker_api_called=True,
                )
            else:
                raise RuntimeError("Broker adapter lacks GTT / SL placement interface")

            # If broker returned an explicit unsuccessful or rejected response
            err_msg = resp.message if resp else "GTT order rejected by broker"
            raise RuntimeError(err_msg)
        except Exception as e:
            logger.error(
                f"[GTTStopDispatcher] Broker stop submission outcome UNKNOWN for {symbol}: {e}. "
                f"Retaining reservation and blocking duplicate dispatch."
            )
            # The adapter exposes no typed proof that a transport exception
            # occurred before broker acceptance. Do not create a compensating
            # side effect; keep the unresolved reservation fail-closed.
            self._set_stop_reservation_state(reservation_key, "UNKNOWN")
            return GTTOrderResponse(
                success=False,
                gtt_order_id=None,
                status="UNKNOWN",
                message=f"Broker stop submission outcome is unknown ({e}); reservation retained and no compensating action attempted",
                timestamp=now_iso,
                fallback_local_kill=False,
                read_only=False,
                is_order_action=True,
                broker_api_called=True,
                allowed_for_live_execution=False,
            )

    def abort_entry_fill_immediately(
        self,
        symbol: str,
        qty: int,
        reason: str,
    ) -> bool:
        """Vector 10: Synchronous emergency abort to square off entry fill and avoid naked risk.
        
        Invoked if broker rejects GTT stop order placement.
        Calls registered abort_fill_cb or broker emergency square-off if available.
        """
        logger.critical(
            f"[GTTStopDispatcher] EMERGENCY ABORT TRIGGERED for {symbol} (Qty: {qty}): {reason}. "
            f"Squaring off entry fill immediately."
        )
        if self.abort_fill_cb:
            try:
                res = self.abort_fill_cb(symbol, qty, reason)
                return res is True
            except Exception as e:
                logger.critical(f"[GTTStopDispatcher] abort_fill_cb failed: {e}")
                return False
        return False

    @staticmethod
    def validate_cancelled_stop_update(update: Any) -> Tuple[bool, str]:
        """Accept only broker status proving cancellation and an explicit zero fill."""
        if update is None:
            return False, "Stop fill status unavailable; target exit blocked."
        status = str(getattr(update, "status", "UNKNOWN") or "UNKNOWN").upper()
        raw_filled = getattr(update, "filled_qty", None)
        try:
            if isinstance(raw_filled, bool) or raw_filled is None:
                raise ValueError("missing or boolean fill quantity")
            numeric_filled = float(raw_filled)
            if not numeric_filled.is_integer() or numeric_filled < 0:
                raise ValueError("fill quantity must be a non-negative integer")
            filled_qty = int(numeric_filled)
        except (TypeError, ValueError, OverflowError):
            return False, "Stop fill quantity is invalid; target exit blocked."
        if status not in {"CANCELLED", "CANCELED"} or filled_qty != 0:
            return False, f"Stop is {status} with filled_qty={filled_qty}; reconcile position before target exit."
        return True, "Stop cancellation acknowledged and zero-fill status reconciled."

    def prepare_target_exit(self, symbol: str) -> Tuple[bool, str]:
        """Vector 11: Cancel-Before-Target-Exit / Double-Fill Guard.
        
        Must cancel broker GTT stop and verify cancellation ack before permitting
        target exit release.
        
        Returns:
            Tuple[bool, str]: (permitted_to_exit, message)
        """
        gtt_order_id = self.symbol_to_gtt_id.get(symbol)
        if not gtt_order_id:
            if self.enable_live_dispatch:
                return False, f"No correlated stop record for {symbol}; target exit blocked because stop state is unknown."
            return True, f"No broker stop is configured in simulation for {symbol}."

        if not self.enable_live_dispatch or not self.broker:
            return self.cancel_on_target_exit(symbol), f"Simulation stop cleared for {symbol}."

        with self._lock:
            try:
                if hasattr(self.broker, "cancel_gtt_order"):
                    cancel_ack = self.broker.cancel_gtt_order(gtt_order_id) is True
                elif hasattr(self.broker, "cancel_order"):
                    cancel_result = self.broker.cancel_order(gtt_order_id)
                    cancel_ack = bool(getattr(cancel_result, "ok", False)) and str(getattr(cancel_result, "status", "")).upper() in {"CANCELLED", "CANCELED"}
                else:
                    cancel_ack = False
            except Exception as exc:
                return False, f"Stop cancellation outcome unknown ({exc}); target exit blocked."
            if not cancel_ack:
                return False, f"Broker cancellation acknowledgment missing for {gtt_order_id}; target exit blocked."

            # The cancellation acknowledgment alone cannot rule out a trigger/fill
            # racing the request. Require a post-cancel broker status with an
            # explicit zero fill. Any fill or unavailable status stays blocked.
            if not hasattr(self.broker, "fetch_order"):
                return False, f"Cannot reconcile stop fill state for {gtt_order_id}; target exit blocked."
            try:
                update = self.broker.fetch_order(gtt_order_id)
            except Exception as exc:
                return False, f"Stop fill reconciliation failed ({exc}); target exit blocked."
            verified, message = self.validate_cancelled_stop_update(update)
            if not verified:
                return False, f"{message} ({gtt_order_id})"
            self.active_gtt_orders.pop(gtt_order_id, None)
            self.symbol_to_gtt_id.pop(symbol, None)
            with self._lock:
                for row in self._stop_reservations.values():
                    if row.get("symbol") == symbol and row.get("order_id") == gtt_order_id:
                        row["state"] = "CANCELLED"
            return True, f"{message} ({gtt_order_id})"

    def cancel_on_target_exit(self, symbol: str) -> bool:
        """Cancels resting broker-side GTT stop order upon normal target exit."""
        gtt_order_id = self.symbol_to_gtt_id.get(symbol)
        if not gtt_order_id:
            logger.warning(f"[GTTStopDispatcher] No active GTT order found to cancel for {symbol}")
            return False

        cancelled = False
        if not self.enable_live_dispatch or not self.broker:
            # Paper mode cancel
            cancelled = True
        else:
            try:
                if hasattr(self.broker, "cancel_gtt_order"):
                    cancelled = self.broker.cancel_gtt_order(gtt_order_id)
                elif hasattr(self.broker, "cancel_order"):
                    cancelled = bool(self.broker.cancel_order(gtt_order_id))
            except Exception as e:
                logger.error(f"[GTTStopDispatcher] Error cancelling broker GTT order {gtt_order_id}: {e}")
                cancelled = False

        if cancelled or not self.enable_live_dispatch:
            self.active_gtt_orders.pop(gtt_order_id, None)
            self.symbol_to_gtt_id.pop(symbol, None)
            logger.info(f"[GTTStopDispatcher] Successfully cancelled stop order {gtt_order_id} for {symbol}")
            return True
        return False

    def _engage_local_kill_switch(self, symbol: str, trigger_price: float) -> bool:
        """Invokes registered local fallback kill-switch callback if broker placement fails."""
        if self.local_kill_switch_cb:
            try:
                return self.local_kill_switch_cb(symbol, trigger_price) is True
            except Exception as e:
                logger.critical(f"[GTTStopDispatcher] Local fallback kill-switch callback failed: {e}")
        return False
