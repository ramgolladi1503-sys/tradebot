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
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, Union

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

        # If live dispatch is disabled or no broker adapter, record dry-run / paper stop safely
        if not self.enable_live_dispatch or not self.broker:
            simulated_id = f"GTT_SIM_{index_name}_{int(datetime.now().timestamp())}"
            self.active_gtt_orders[simulated_id] = req
            self.symbol_to_gtt_id[symbol] = simulated_id
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
                    self.active_gtt_orders[resp.gtt_order_id] = req
                    self.symbol_to_gtt_id[symbol] = resp.gtt_order_id
                    return resp
            elif hasattr(self.broker, "place_order"):
                # Broker adapter supports generic place_order for SL-M / GTT
                raw_resp = self.broker.place_order(
                    symbol=req.symbol,
                    qty=req.qty,
                    side=req.side,
                    order_type=req.order_type.value,
                    trigger_price=req.trigger_price,
                )
                order_id = getattr(raw_resp, "order_id", None) or str(raw_resp)
                self.active_gtt_orders[order_id] = req
                self.symbol_to_gtt_id[symbol] = order_id
                return GTTOrderResponse(
                    success=True,
                    gtt_order_id=order_id,
                    status="ACTIVE",
                    message="Broker SL order placed successfully",
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
                f"[GTTStopDispatcher] Broker GTT dispatch FAILED for {symbol}: {e}. "
                f"Triggering EMERGENCY ABORT and LOCAL FAILSAFE KILL-SWITCH."
            )
            # Vector 10: Emergency Abort on GTT Rejection to square off entry fill and avoid naked risk
            self.abort_entry_fill_immediately(symbol=symbol, qty=qty, reason=str(e))
            # Engage fallback local kill-switch to protect capital
            self._engage_local_kill_switch(symbol, trigger_price)
            return GTTOrderResponse(
                success=False,
                gtt_order_id=None,
                status="REJECTED",
                message=f"Broker GTT dispatch failed ({e}); entry fill aborted / local software stop loss active",
                timestamp=now_iso,
                fallback_local_kill=True,
                read_only=True,
                is_order_action=False,
                broker_api_called=True,
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
                return bool(res) if res is not None else True
            except Exception as e:
                logger.critical(f"[GTTStopDispatcher] abort_fill_cb failed: {e}")
                return False
        return False

    def prepare_target_exit(self, symbol: str) -> Tuple[bool, str]:
        """Vector 11: Cancel-Before-Target-Exit / Double-Fill Guard.
        
        Must cancel broker GTT stop and verify cancellation ack before permitting
        target exit release.
        
        Returns:
            Tuple[bool, str]: (permitted_to_exit, message)
        """
        gtt_order_id = self.symbol_to_gtt_id.get(symbol)
        if not gtt_order_id:
            # No resting broker GTT stop exists for this symbol (e.g. paper mode or already cancelled)
            return True, f"No resting GTT stop order for {symbol}. Safe to release target exit."

        # If resting GTT order exists, we must cancel it and confirm acknowledgment before target exit
        success = self.cancel_on_target_exit(symbol)
        if success:
            return True, f"Successfully cancelled GTT stop order {gtt_order_id} for {symbol}. Target exit permitted."
        else:
            return False, f"Failed to verify cancellation ack for GTT order {gtt_order_id} ({symbol}). Target exit BLOCKED to prevent double-fill."

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

    def _engage_local_kill_switch(self, symbol: str, trigger_price: float):
        """Invokes registered local fallback kill-switch callback if broker placement fails."""
        if self.local_kill_switch_cb:
            try:
                self.local_kill_switch_cb(symbol, trigger_price)
            except Exception as e:
                logger.critical(f"[GTTStopDispatcher] Local fallback kill-switch callback failed: {e}")
