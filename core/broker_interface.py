from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class BrokerHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass
class BrokerOrderRequest:
    symbol: str
    side: str
    qty: int
    order_type: str = "MARKET"
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None


@dataclass
class BrokerOrderResponse:
    ok: bool
    broker_order_id: str | None = None
    status: str = "UNKNOWN"
    reason: str | None = None


@dataclass
class BrokerFillUpdate:
    broker_order_id: str
    status: str
    filled_qty: int
    avg_fill_price: float
    reason: str | None = None


class BrokerAdapter(Protocol):
    def health(self) -> BrokerHealth: ...
    def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResponse: ...
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse: ...
    def fetch_order(self, broker_order_id: str) -> BrokerFillUpdate | None: ...
    def fetch_open_positions(self) -> list[dict]: ...
