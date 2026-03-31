from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import time


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTING = "SUBMITTING"
    ACKED = "ACKED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


@dataclass
class OrderIntent:
    symbol: str
    side: str
    qty: int
    order_type: str = "MARKET"
    limit_price: float | None = None
    stop_price: float | None = None
    strategy_name: str | None = None
    correlation_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderRecord:
    client_order_id: str
    intent: OrderIntent
    status: OrderStatus = OrderStatus.CREATED
    broker_order_id: str | None = None
    requested_qty: int = 0
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    reject_reason: str | None = None
    created_ts: float = field(default_factory=time.time)
    updated_ts: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)

    def append_event(self, event_type: str, **payload: Any) -> None:
        self.updated_ts = time.time()
        self.events.append({
            "ts": self.updated_ts,
            "event_type": event_type,
            **payload,
        })


class OrderLifecycleManager:
    def __init__(self) -> None:
        self.orders: dict[str, OrderRecord] = {}

    def create(self, client_order_id: str, intent: OrderIntent) -> OrderRecord:
        rec = OrderRecord(
            client_order_id=client_order_id,
            intent=intent,
            requested_qty=max(0, int(intent.qty)),
        )
        rec.append_event("created", symbol=intent.symbol, side=intent.side, qty=intent.qty)
        self.orders[client_order_id] = rec
        return rec

    def mark_submitting(self, client_order_id: str) -> OrderRecord:
        rec = self.orders[client_order_id]
        rec.status = OrderStatus.SUBMITTING
        rec.append_event("submitting")
        return rec

    def mark_acked(self, client_order_id: str, broker_order_id: str) -> OrderRecord:
        rec = self.orders[client_order_id]
        rec.status = OrderStatus.ACKED
        rec.broker_order_id = broker_order_id
        rec.append_event("acked", broker_order_id=broker_order_id)
        return rec

    def apply_fill(self, client_order_id: str, fill_qty: int, fill_price: float) -> OrderRecord:
        rec = self.orders[client_order_id]
        prior_qty = rec.filled_qty
        new_qty = max(0, int(fill_qty))
        total_qty = prior_qty + new_qty
        if total_qty > 0:
            rec.avg_fill_price = ((rec.avg_fill_price * prior_qty) + (float(fill_price) * new_qty)) / total_qty
        rec.filled_qty = min(rec.requested_qty, total_qty)
        rec.status = OrderStatus.FILLED if rec.filled_qty >= rec.requested_qty else OrderStatus.PARTIALLY_FILLED
        rec.append_event("fill", fill_qty=new_qty, fill_price=float(fill_price), cum_qty=rec.filled_qty, avg_fill=rec.avg_fill_price)
        return rec

    def mark_cancel_pending(self, client_order_id: str) -> OrderRecord:
        rec = self.orders[client_order_id]
        rec.status = OrderStatus.CANCEL_PENDING
        rec.append_event("cancel_pending")
        return rec

    def mark_cancelled(self, client_order_id: str) -> OrderRecord:
        rec = self.orders[client_order_id]
        rec.status = OrderStatus.CANCELLED
        rec.append_event("cancelled")
        return rec

    def mark_rejected(self, client_order_id: str, reason: str) -> OrderRecord:
        rec = self.orders[client_order_id]
        rec.status = OrderStatus.REJECTED
        rec.reject_reason = reason
        rec.append_event("rejected", reason=reason)
        return rec

    def mark_error(self, client_order_id: str, reason: str) -> OrderRecord:
        rec = self.orders[client_order_id]
        rec.status = OrderStatus.ERROR
        rec.reject_reason = reason
        rec.append_event("error", reason=reason)
        return rec

    def get(self, client_order_id: str) -> Optional[OrderRecord]:
        return self.orders.get(client_order_id)

    def get_by_broker_order_id(self, broker_order_id: str) -> Optional[OrderRecord]:
        for rec in self.orders.values():
            if rec.broker_order_id == broker_order_id:
                return rec
        return None
