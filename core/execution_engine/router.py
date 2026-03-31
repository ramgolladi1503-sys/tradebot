from __future__ import annotations

from typing import Any, Dict

from core.execution_engine.pretrade_checks import validate_execution_intent


class ExecutionRouterError(RuntimeError):
    pass


def execute_intent(intent: Any, broker: Any) -> Dict[str, Any]:
    ok, reason = validate_execution_intent(intent)
    if not ok:
        return {
            "status": "rejected",
            "reason": reason,
            "order_id": None,
        }

    if broker is None:
        return {
            "status": "rejected",
            "reason": "missing_broker",
            "order_id": None,
        }

    try:
        order = broker.place_order(
            symbol=(intent["symbol"] if isinstance(intent, dict) else intent.symbol),
            price=(intent["entry_price"] if isinstance(intent, dict) else intent.entry_price),
            qty=(intent["qty"] if isinstance(intent, dict) else intent.qty),
            side=(intent["direction"] if isinstance(intent, dict) else intent.direction),
        )
    except Exception as exc:
        return {
            "status": "submit_failed",
            "reason": type(exc).__name__,
            "order_id": None,
        }

    order_id = None
    if isinstance(order, dict):
        order_id = order.get("order_id")

    return {
        "status": "submitted" if order_id else "submitted_without_order_id",
        "reason": "ok" if order_id else "missing_order_id",
        "order_id": order_id,
    }
