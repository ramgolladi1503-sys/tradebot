from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from core.events import append_event
from core.observation_execution_guard import assert_execution_allowed


@dataclass
class MockBroker:
    event_writer: Callable[[str, dict[str, Any]], None] = append_event
    _order_seq: int = 0

    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"MOCK-{self._order_seq:06d}"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            out = float(value)
            if out != out:
                return None
            return out
        except Exception:
            return None

    def _deterministic_fill_price(self, intent: dict[str, Any]) -> float:
        bid = self._safe_float(intent.get("bid"))
        ask = self._safe_float(intent.get("ask"))
        ltp = self._safe_float(intent.get("ltp"))
        if bid is not None and ask is not None:
            return float((bid + ask) / 2.0)
        if ltp is not None:
            return float(ltp)
        raise ValueError("NO_PRICE_P0")

    def place_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        assert_execution_allowed("MockBroker.place_order")
        order_id = self._next_order_id()
        payload = {
            "order_id": order_id,
            "trade_id": str(intent.get("trade_id") or ""),
            "symbol": str(intent.get("symbol") or ""),
            "side": str(intent.get("side") or "BUY").upper(),
            "qty": float(self._safe_float(intent.get("qty")) or 0.0),
            "run_id": str(intent.get("run_id") or ""),
            "desk_id": str(intent.get("desk_id") or "DEFAULT"),
            "mode": str(intent.get("mode") or "PAPER").upper(),
            "ts": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self.event_writer("order_submitted", payload)
        fill_price = self._deterministic_fill_price(intent)
        fill = self.fill_order(order_id, price=fill_price, qty=payload["qty"], intent=intent)
        return {
            "order_id": order_id,
            "status": "submitted",
            "fill": fill,
        }

    def modify_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        assert_execution_allowed("MockBroker.modify_order")
        raise NotImplementedError("modify_order is not implemented")

    def cancel_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        assert_execution_allowed("MockBroker.cancel_order")
        raise NotImplementedError("cancel_order is not implemented")

    def fill_order(
        self,
        order_id: str,
        price: float,
        qty: float,
        *,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "order_id": str(order_id),
            "trade_id": str(intent.get("trade_id") or ""),
            "symbol": str(intent.get("symbol") or ""),
            "side": str(intent.get("side") or "BUY").upper(),
            "qty": float(qty),
            "price": float(price),
            "run_id": str(intent.get("run_id") or ""),
            "desk_id": str(intent.get("desk_id") or "DEFAULT"),
            "mode": str(intent.get("mode") or "PAPER").upper(),
            "ts": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self.event_writer("fill", payload)
        return {
            "order_id": str(order_id),
            "status": "filled",
            "price": float(price),
            "qty": float(qty),
        }
