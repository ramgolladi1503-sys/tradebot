"""
Sentinel Automated Order Dispatcher
===================================
Translates Sentinel APM state machine events into BrokerOrderRequests:
- Emits entry Limit Orders on setup firing.
- Emits exit Limit Orders on target/stop milestones.
- Connects to MockBroker / UpstoxBrokerAdapter via SentinelExecutionRouter.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import threading

from core.broker_interface import BrokerAdapter, BrokerOrderRequest, BrokerOrderResponse
from core.sentinel_execution_router import SentinelExecutionRouter, ExecutionMode


@dataclass
class AutomatedExecutionResult:
    index_name: str
    symbol: str
    action: str  # "ENTRY_SUBMITTED", "EXIT_SUBMITTED", "VETOED_OFFLINE", "PAPER_RECORDED"
    mode: str
    order_id: Optional[str] = None
    target_price: float = 0.0
    qty: int = 0
    message: str = ""
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    status: str = "UNKNOWN"
    filled_qty: int = 0


class SentinelAutomatedOrderDispatcher:
    """
    Subscribes to APM actions and dispatches execution orders:
    - NIFTY triggers live execution if enabled in router; otherwise PAPER.
    - SENSEX and BANKNIFTY are strictly forced to PAPER execution.
    - Strict Invariants:
      * Anti-Overtrading: Hard stop at max 5 trades per session.
      * Idempotency & Anti-Duplicate: Disallows concurrent live positions or duplicate orders.
    """

    def __init__(
        self,
        router: Optional[SentinelExecutionRouter] = None,
        broker_adapter: Optional[BrokerAdapter] = None,
        paper_event_writer: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        max_daily_live_trades: int = 5,
        gtt_stop_dispatcher: Optional[Any] = None,
    ):
        self.router = router or SentinelExecutionRouter(enable_nifty_live=False)
        self.broker = broker_adapter
        self.paper_writer = paper_event_writer
        self.max_daily_live_trades = max_daily_live_trades
        self.daily_live_trade_count: Dict[str, int] = {}
        self.active_live_position: Dict[str, Optional[str]] = {}  # index_name -> symbol
        self.gtt_stop_dispatcher = gtt_stop_dispatcher
        self._lock = threading.RLock()
        self._intents: Dict[str, Dict[str, Any]] = {}
        self._filled_positions: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _intent_key(index_name: str, symbol: str, side: str, qty: int, price: float, reason: str, intent_id: Optional[str]) -> str:
        seed = intent_id or json.dumps(
            [index_name, symbol, side, int(qty), float(price), reason,
             datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()],
            separators=(",", ":"),
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _classify_fill_status(status: Any, filled_qty: Any, requested_qty: int) -> str:
        """Return a fill state only when broker status and quantity agree."""
        normalized = str(status or "UNKNOWN").upper()
        try:
            if isinstance(filled_qty, bool) or filled_qty is None:
                return "UNKNOWN"
            numeric_qty = float(filled_qty)
            if not math.isfinite(numeric_qty) or not numeric_qty.is_integer():
                return "UNKNOWN"
            qty = int(numeric_qty)
        except (TypeError, ValueError, OverflowError):
            return "UNKNOWN"
        if requested_qty <= 0 or qty < 0 or qty > requested_qty:
            return "UNKNOWN"
        if normalized in {"COMPLETE", "COMPLETED", "FILLED"}:
            return "FILLED" if qty == requested_qty else "UNKNOWN"
        if normalized == "PARTIAL":
            return "PARTIAL" if 0 < qty < requested_qty else "UNKNOWN"
        if qty > 0:
            return "UNKNOWN"
        if normalized in {"SUBMITTED", "OPEN", "REJECTED", "CANCELLED", "CANCELED"}:
            return normalized
        return "UNKNOWN"

    @staticmethod
    def _valid_positive(value: Any) -> bool:
        try:
            return math.isfinite(float(value)) and float(value) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _may_clear_exit_latch(pre_dispatch_veto: bool, stop_side_effect_started: bool) -> bool:
        """Release an exit reservation only for a proven veto before stop mutation."""
        return pre_dispatch_veto and not stop_side_effect_started

    def _reserve_live_entry(self, index_name: str, symbol: str, key: str, qty: int) -> tuple[bool, str]:
        """Atomically check process-local risk limits and reserve an entry intent."""
        with self._lock:
            count = self.daily_live_trade_count.get(index_name, 0)
            if count >= self.max_daily_live_trades:
                return False, f"Daily trade cap reached ({count}/{self.max_daily_live_trades})."
            if self.active_live_position.get(index_name) is not None or any(
                item.get("index_name") == index_name and item.get("status") in
                {"DISPATCHING", "SUBMITTED", "OPEN", "UNKNOWN", "PARTIAL"}
                for item in self._intents.values()
            ):
                return False, f"Active or unresolved live entry for {index_name}."
            if key in self._intents:
                return False, "Duplicate or unresolved entry intent is blocked."
            self._intents[key] = {
                "status": "DISPATCHING", "order_id": None, "index_name": index_name,
                "symbol": symbol, "side": "BUY", "qty": qty,
            }
            return True, "reserved"

    def reconcile_order_status(self, client_order_id: str) -> bool:
        """Refresh an already submitted order from broker-reported status only.

        Returns True only when a positive, bounded fill quantity and valid fill
        price were observed. Missing/ambiguous status leaves the intent pending.
        """
        if self.broker is None or not hasattr(self.broker, "fetch_order"):
            return False
        key = str(client_order_id or "").removeprefix("SENTINEL-ENTRY-")
        with self._lock:
            intent = self._intents.get(key)
            if not intent or not intent.get("order_id"):
                return False
            broker_order_id = intent["order_id"]
        try:
            update = self.broker.fetch_order(broker_order_id)
        except Exception:
            return False
        if update is None:
            return False
        status = str(getattr(update, "status", "UNKNOWN") or "UNKNOWN").upper()
        try:
            raw_filled = getattr(update, "filled_qty", 0)
            if isinstance(raw_filled, bool):
                return False
            numeric_filled = float(raw_filled or 0)
            if not math.isfinite(numeric_filled) or not numeric_filled.is_integer():
                return False
            filled_qty = int(numeric_filled)
            avg_fill_price = float(getattr(update, "avg_fill_price", 0.0) or 0.0)
        except (TypeError, ValueError, OverflowError):
            return False
        fill_state = self._classify_fill_status(status, filled_qty, int(intent["qty"]))
        with self._lock:
            if fill_state == "UNKNOWN":
                intent["status"] = "UNKNOWN"
                return False
            status = fill_state
            if filled_qty > 0 and not self._valid_positive(avg_fill_price):
                intent["status"] = "UNKNOWN"
                return False
            intent["status"] = status
            if filled_qty > 0 and self._valid_positive(avg_fill_price):
                self._filled_positions[intent["index_name"]] = {
                    "symbol": intent["symbol"], "qty": filled_qty,
                    "entry_price": avg_fill_price, "order_id": broker_order_id,
                    "intent_key": key,
                }
                self.active_live_position[intent["index_name"]] = intent["symbol"]
                if not intent.get("counted"):
                    self.daily_live_trade_count[intent["index_name"]] = self.daily_live_trade_count.get(intent["index_name"], 0) + 1
                    intent["counted"] = True
                return True
        return False

    def on_apm_entry(
        self,
        index_name: str,
        symbol: str,
        option_type: str,
        entry_price: float,
        target_pts: float,
        sl_pts: float,
        setup_reason: str,
        qty: Optional[int] = None,
        intent_id: Optional[str] = None,
    ) -> AutomatedExecutionResult:
        """Called when APM moves to STATE_IN_FLIGHT."""
        policy = self.router.get_policy(index_name)
        mode = policy.target_mode
        if policy.lot_size <= 0:
            return AutomatedExecutionResult(
                index_name=policy.index_name, symbol=symbol, action="VETOED_UNKNOWN_ROUTE",
                mode=mode.value, message="Unknown or missing instrument route; broker dispatch blocked.",
                status="VETOED", read_only=True, is_order_action=False, broker_api_called=False,
            )
        if not symbol or not all(self._valid_positive(v) for v in (entry_price, target_pts, sl_pts)):
            return AutomatedExecutionResult(
                index_name=policy.index_name, symbol=symbol, action="VETOED_INVALID_INTENT",
                mode=mode.value, message="Missing symbol or invalid entry, target, or stop value.", status="VETOED",
                read_only=True, is_order_action=False, broker_api_called=False,
            )
        resolved_qty = qty if qty is not None else policy.lot_size
        if isinstance(resolved_qty, bool) or not isinstance(resolved_qty, int) or resolved_qty <= 0:
            return AutomatedExecutionResult(
                index_name=policy.index_name, symbol=symbol, action="VETOED_INVALID_INTENT",
                mode=mode.value, message="Quantity must be a positive integer.", status="VETOED",
                read_only=True, is_order_action=False, broker_api_called=False,
            )

        intent = {
            "index_name": policy.index_name,
            "symbol": symbol,
            "side": "BUY",
            "qty": resolved_qty,
            "entry_price": entry_price,
            "target_pts": target_pts,
            "sl_pts": sl_pts,
            "setup_reason": setup_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        routed = self.router.route_execution_intent(index_name, intent)

        if routed["mode"] == ExecutionMode.LIVE.value:
            # LIVE automated execution for NIFTY
            if self.broker is None:
                return AutomatedExecutionResult(
                    index_name=index_name,
                    symbol=symbol,
                    action="VETOED_OFFLINE",
                    mode="LIVE",
                    message="Broker adapter offline or not connected",
                )

            key = self._intent_key(policy.index_name, symbol, "BUY", resolved_qty, entry_price, setup_reason, intent_id)
            reserved, reservation_reason = self._reserve_live_entry(
                policy.index_name, symbol, key, resolved_qty
            )
            if not reserved:
                cap_hit = reservation_reason.startswith("Daily trade cap")
                return AutomatedExecutionResult(
                    index_name=index_name, symbol=symbol,
                    action="VETOED_OVERTRADING_CAP" if cap_hit else "VETOED_CONCURRENT_POSITION",
                    mode="LIVE", qty=resolved_qty, message=reservation_reason,
                    status="VETOED", read_only=True, is_order_action=False, broker_api_called=False,
                )
            current_count = self.daily_live_trade_count.get(policy.index_name, 0)

            req = BrokerOrderRequest(
                symbol=symbol,
                side="BUY",
                qty=resolved_qty,
                order_type="LIMIT",
                limit_price=entry_price,
                client_order_id=f"SENTINEL-ENTRY-{key}",
            )
            try:
                resp = self.broker.place_order(req)
            except Exception as exc:
                with self._lock:
                    self._intents[key]["status"] = "UNKNOWN"
                return AutomatedExecutionResult(
                    index_name=policy.index_name, symbol=symbol, action="ORDER_UNKNOWN", mode="LIVE",
                    qty=resolved_qty, message=f"Broker outcome unknown; duplicate dispatch blocked: {exc}",
                    read_only=False, is_order_action=True, broker_api_called=True, status="UNKNOWN",
                )
            ok = bool(getattr(resp, "ok", False)) if resp is not None else False
            status = str(getattr(resp, "status", "UNKNOWN") or "UNKNOWN").upper() if resp is not None else "UNKNOWN"
            order_id = getattr(resp, "broker_order_id", None) if resp is not None else None
            try:
                raw_filled = getattr(resp, "filled_qty", 0) if resp is not None else 0
                if isinstance(raw_filled, bool):
                    raise ValueError("boolean fill quantity")
                numeric_filled = float(raw_filled or 0)
                if not math.isfinite(numeric_filled) or not numeric_filled.is_integer():
                    raise ValueError("fill quantity must be a finite integer")
                filled_qty = int(numeric_filled)
                avg_fill_price = float(getattr(resp, "avg_fill_price", 0.0) or 0.0) if resp is not None else 0.0
            except (TypeError, ValueError, OverflowError):
                filled_qty, avg_fill_price, status = 0, 0.0, "UNKNOWN"
            observed_status = self._classify_fill_status(status, filled_qty, resolved_qty)
            if filled_qty > 0 and not self._valid_positive(avg_fill_price):
                observed_status = "UNKNOWN"
            with self._lock:
                terminal_rejections = {"REJECTED", "CANCELLED", "CANCELED"}
                if not ok and observed_status not in terminal_rejections:
                    observed_status = "UNKNOWN"
                self._intents[key].update(status=observed_status, order_id=order_id)
                if ok and observed_status in {"PARTIAL", "FILLED"} and 0 < filled_qty <= resolved_qty and self._valid_positive(avg_fill_price):
                    self._filled_positions[policy.index_name] = {
                        "symbol": symbol, "qty": filled_qty, "entry_price": avg_fill_price,
                        "order_id": order_id, "intent_key": key,
                    }
                    self.active_live_position[policy.index_name] = symbol
                    if not self._intents[key].get("counted"):
                        self.daily_live_trade_count[policy.index_name] = current_count + 1
                        self._intents[key]["counted"] = True

            effective_ok = ok and observed_status in {"SUBMITTED", "OPEN", "PARTIAL", "FILLED"}
            return AutomatedExecutionResult(
                index_name=index_name,
                symbol=symbol,
                action=("ENTRY_FILLED" if observed_status == "FILLED" else "ENTRY_PARTIAL" if observed_status == "PARTIAL" else "ENTRY_SUBMITTED") if effective_ok else ("REJECTED" if observed_status in terminal_rejections else "ORDER_UNKNOWN"),
                mode="LIVE",
                order_id=order_id,
                target_price=entry_price,
                qty=resolved_qty,
                message=(
                    (getattr(resp, "reason", None) if observed_status in terminal_rejections else None)
                    or ("Broker-confirmed full fill" if observed_status == "FILLED" else
                        "Broker-confirmed partial fill" if observed_status == "PARTIAL" else
                        "Broker acknowledged submission; fill not confirmed" if observed_status in {"SUBMITTED", "OPEN"} else
                        "Broker fill state is inconsistent or unknown")
                ) if resp is not None else "Broker outcome unknown",
                read_only=False,
                is_order_action=True,
                broker_api_called=True,
                status=observed_status,
                filled_qty=filled_qty if observed_status in {"FILLED", "PARTIAL"} else 0,
            )
        else:
            # PAPER execution for SENSEX, BANKNIFTY, or unapproved NIFTY
            order_id = f"PAPER-{policy.index_name}-{int(datetime.now().timestamp())}"
            if self.paper_writer:
                self.paper_writer("paper_order_entry", {**routed, "order_id": order_id})
            return AutomatedExecutionResult(
                index_name=index_name,
                symbol=symbol,
                action="PAPER_RECORDED",
                mode=routed["mode"],
                order_id=order_id,
                target_price=entry_price,
                qty=resolved_qty,
                message=f"Paper trade recorded for {policy.index_name} (Live isolated)",
                read_only=True,
                is_order_action=False,
                broker_api_called=False,
            )

    def on_apm_exit(
        self,
        index_name: str,
        symbol: str,
        exit_price: float,
        reason: str,
        qty: Optional[int] = None,
        intent_id: Optional[str] = None,
    ) -> AutomatedExecutionResult:
        """Called when APM reaches TARGET_REACHED or STOP_LOSS_HIT."""
        policy = self.router.get_policy(index_name)
        mode = policy.target_mode
        if policy.lot_size <= 0 or not symbol or not self._valid_positive(exit_price):
            return AutomatedExecutionResult(
                index_name=policy.index_name, symbol=symbol, action="VETOED_INVALID_EXIT",
                mode=mode.value, message="Unknown route or invalid exit intent; dispatch blocked.", status="VETOED",
                read_only=True, is_order_action=False, broker_api_called=False,
            )
        requested_exit_qty = qty if qty is not None else policy.lot_size
        if isinstance(requested_exit_qty, bool) or not isinstance(requested_exit_qty, int) or requested_exit_qty <= 0:
            return AutomatedExecutionResult(
                index_name=policy.index_name, symbol=symbol, action="VETOED_INVALID_EXIT_QTY",
                mode=mode.value, message="Exit quantity must be a positive integer.", status="VETOED",
                read_only=True, is_order_action=False, broker_api_called=False,
            )

        intent = {
            "index_name": policy.index_name,
            "symbol": symbol,
            "side": "SELL",
            "qty": requested_exit_qty,
            "exit_price": exit_price,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        routed = self.router.route_execution_intent(index_name, intent)

        if routed["mode"] == ExecutionMode.LIVE.value:
            with self._lock:
                position = self._filled_positions.get(policy.index_name)
                if not position or position.get("symbol") != symbol:
                    return AutomatedExecutionResult(
                        index_name=policy.index_name, symbol=symbol, action="VETOED_UNRECONCILED_POSITION",
                        mode="LIVE", message="No broker-confirmed matching open position; exit blocked.", status="VETOED",
                        read_only=True, is_order_action=False, broker_api_called=False,
                    )
                exit_qty = requested_exit_qty if qty is not None else int(position.get("qty", 0))
                if isinstance(exit_qty, bool) or not isinstance(exit_qty, int) or exit_qty <= 0 or exit_qty > int(position.get("qty", 0)):
                    return AutomatedExecutionResult(
                        index_name=policy.index_name, symbol=symbol, action="VETOED_INVALID_EXIT_QTY",
                        mode="LIVE", message="Exit quantity exceeds or conflicts with reconciled remaining quantity.", status="VETOED",
                        read_only=True, is_order_action=False, broker_api_called=False,
                    )
                if position.get("exit_pending"):
                    return AutomatedExecutionResult(
                        index_name=policy.index_name, symbol=symbol, action="VETOED_DUPLICATE_EXIT",
                        mode="LIVE", message="A prior exit outcome is unresolved; repeat dispatch blocked.", status="PENDING",
                        read_only=True, is_order_action=False, broker_api_called=False,
                    )
                # Serialize concurrent exits before cancel/status reconciliation.
                position["exit_pending"] = True
            if self.broker is None:
                # Known pre-dispatch veto: no target order was sent. Release the
                # process-local latch so a later retry can be considered.
                if self._may_clear_exit_latch(True, False):
                    with self._lock:
                        position["exit_pending"] = False
                return AutomatedExecutionResult(
                    index_name=policy.index_name, symbol=symbol, action="VETOED_OFFLINE",
                    mode="LIVE", message="Broker adapter offline; target exit was not dispatched.", status="VETOED",
                    read_only=True, is_order_action=False, broker_api_called=False,
                )
            if self.gtt_stop_dispatcher is None:
                if self._may_clear_exit_latch(True, False):
                    with self._lock:
                        position["exit_pending"] = False
                return AutomatedExecutionResult(
                    index_name=policy.index_name, symbol=symbol, action="VETOED_STOP_NOT_RECONCILED",
                    mode="LIVE", message="No stop dispatcher is available to prove stop cancellation and fill reconciliation.", status="VETOED",
                    read_only=True, is_order_action=False, broker_api_called=False,
                )
            allowed, stop_message = self.gtt_stop_dispatcher.prepare_target_exit(symbol)
            if not allowed:
                return AutomatedExecutionResult(
                    index_name=policy.index_name, symbol=symbol, action="VETOED_STOP_NOT_RECONCILED",
                    mode="LIVE", message=stop_message, status="VETOED",
                    read_only=True, is_order_action=False, broker_api_called=False,
                )
            req = BrokerOrderRequest(
                symbol=symbol,
                side="SELL",
                qty=exit_qty,
                order_type="LIMIT",
                limit_price=exit_price,
                client_order_id=f"SENTINEL-EXIT-{self._intent_key(policy.index_name, symbol, 'SELL', exit_qty, exit_price, reason, intent_id)}",
            )
            try:
                resp = self.broker.place_order(req)
            except Exception as exc:
                return AutomatedExecutionResult(
                    index_name=policy.index_name, symbol=symbol, action="EXIT_UNKNOWN", mode="LIVE",
                    qty=exit_qty, message=f"Broker outcome unknown; position remains open and retry is blocked: {exc}",
                    read_only=False, is_order_action=True, broker_api_called=True, status="UNKNOWN",
                )
            ok = bool(getattr(resp, "ok", False)) if resp is not None else False
            status = str(getattr(resp, "status", "UNKNOWN") or "UNKNOWN").upper() if resp is not None else "UNKNOWN"
            return AutomatedExecutionResult(
                index_name=index_name,
                symbol=symbol,
                action="EXIT_SUBMITTED" if ok else "REJECTED",
                mode="LIVE",
                order_id=getattr(resp, "broker_order_id", None) if resp is not None else None,
                target_price=exit_price,
                qty=exit_qty,
                message=(getattr(resp, "reason", None) or "Broker acknowledged exit submission; position remains open pending fill reconciliation") if resp is not None else "Broker outcome unknown",
                read_only=False,
                is_order_action=True,
                broker_api_called=True,
                status=status,
            )
        else:
            order_id = f"PAPER-EXIT-{policy.index_name}-{int(datetime.now().timestamp())}"
            if self.paper_writer:
                self.paper_writer("paper_order_exit", {**routed, "order_id": order_id})
            return AutomatedExecutionResult(
                index_name=index_name,
                symbol=symbol,
                action="PAPER_RECORDED",
                mode=routed["mode"],
                order_id=order_id,
                target_price=exit_price,
                qty=int(routed["qty"]),
                message=f"Paper exit recorded for {policy.index_name}",
                read_only=True,
                is_order_action=False,
                broker_api_called=False,
            )
