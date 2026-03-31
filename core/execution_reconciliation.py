from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.order_lifecycle import OrderLifecycleManager, OrderStatus


@dataclass
class ReconcileResult:
    client_order_id: str
    local_status: str
    broker_status: str | None
    action: str


class ExecutionReconciler:
    def __init__(self, lifecycle: OrderLifecycleManager) -> None:
        self.lifecycle = lifecycle

    def reconcile_order_snapshot(self, broker_snapshot: dict[str, Any]) -> ReconcileResult | None:
        broker_order_id = broker_snapshot.get("broker_order_id")
        if not broker_order_id:
            return None

        rec = self.lifecycle.get_by_broker_order_id(str(broker_order_id))
        if rec is None:
            return None

        broker_status = str(broker_snapshot.get("status", "UNKNOWN")).upper()
        filled_qty = int(broker_snapshot.get("filled_qty", 0) or 0)
        avg_fill_price = float(broker_snapshot.get("avg_fill_price", 0.0) or 0.0)
        reason = broker_snapshot.get("reason")

        if broker_status in {"COMPLETE", "FILLED"}:
            delta = max(0, filled_qty - rec.filled_qty)
            if delta > 0:
                self.lifecycle.apply_fill(rec.client_order_id, delta, avg_fill_price)
            else:
                rec.status = OrderStatus.FILLED
            return ReconcileResult(rec.client_order_id, rec.status.value, broker_status, "filled")

        if broker_status in {"REJECTED"}:
            rec.status = OrderStatus.REJECTED
            rec.reject_reason = str(reason) if reason else None
            return ReconcileResult(rec.client_order_id, rec.status.value, broker_status, "rejected")

        return ReconcileResult(rec.client_order_id, rec.status.value, broker_status, "noop")
