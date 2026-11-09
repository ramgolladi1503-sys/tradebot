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


class SentinelAutomatedOrderDispatcher:
    """
    Subscribes to APM actions and dispatches execution orders:
    - NIFTY triggers live execution if enabled in router; otherwise PAPER.
    - SENSEX and BANKNIFTY are strictly forced to PAPER execution.
    """

    def __init__(
        self,
        router: Optional[SentinelExecutionRouter] = None,
        broker_adapter: Optional[BrokerAdapter] = None,
        paper_event_writer: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.router = router or SentinelExecutionRouter(enable_nifty_live=False)
        self.broker = broker_adapter
        self.paper_writer = paper_event_writer

    def on_apm_entry(
        self,
        index_name: str,
        symbol: str,
        option_type: str,
        entry_price: float,
        target_pts: float,
        sl_pts: float,
        setup_reason: str,
    ) -> AutomatedExecutionResult:
        """Called when APM moves to STATE_IN_FLIGHT."""
        policy = self.router.get_policy(index_name)
        mode = policy.target_mode

        intent = {
            "index_name": policy.index_name,
            "symbol": symbol,
            "side": "BUY",
            "qty": policy.lot_size,
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

            req = BrokerOrderRequest(
                symbol=symbol,
                side="BUY",
                qty=routed["lot_size"],
                order_type="LIMIT",
                limit_price=entry_price,
                client_order_id=f"SENTINEL-ENTRY-{int(datetime.now().timestamp()*1000)}",
            )
            resp = self.broker.place_order(req)
            return AutomatedExecutionResult(
                index_name=index_name,
                symbol=symbol,
                action="ENTRY_SUBMITTED" if resp.ok else "REJECTED",
                mode="LIVE",
                order_id=resp.broker_order_id,
                target_price=entry_price,
                qty=routed["lot_size"],
                message=resp.reason or "LIVE order dispatched",
                read_only=False,
                is_order_action=True,
                broker_api_called=True,
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
                qty=routed["lot_size"],
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
    ) -> AutomatedExecutionResult:
        """Called when APM reaches TARGET_REACHED or STOP_LOSS_HIT."""
        policy = self.router.get_policy(index_name)
        mode = policy.target_mode

        intent = {
            "index_name": policy.index_name,
            "symbol": symbol,
            "side": "SELL",
            "qty": policy.lot_size,
            "exit_price": exit_price,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        routed = self.router.route_execution_intent(index_name, intent)

        if routed["mode"] == ExecutionMode.LIVE.value and self.broker:
            req = BrokerOrderRequest(
                symbol=symbol,
                side="SELL",
                qty=routed["lot_size"],
                order_type="LIMIT",
                limit_price=exit_price,
                client_order_id=f"SENTINEL-EXIT-{int(datetime.now().timestamp()*1000)}",
            )
            resp = self.broker.place_order(req)
            return AutomatedExecutionResult(
                index_name=index_name,
                symbol=symbol,
                action="EXIT_SUBMITTED" if resp.ok else "REJECTED",
                mode="LIVE",
                order_id=resp.broker_order_id,
                target_price=exit_price,
                qty=routed["lot_size"],
                message=resp.reason or "LIVE exit dispatched",
                read_only=False,
                is_order_action=True,
                broker_api_called=True,
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
                qty=routed["lot_size"],
                message=f"Paper exit recorded for {policy.index_name}",
                read_only=True,
                is_order_action=False,
                broker_api_called=False,
            )
