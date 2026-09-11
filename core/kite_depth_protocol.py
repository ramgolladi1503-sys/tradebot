"""Exact Kite Connect v3 top-five-per-side depth contract."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

DEPTH_LEVELS_PER_SIDE = 5
TOTAL_DEPTH_LEVELS = 10
DEPTH_ENTRY_WIRE_BYTES = 12
FULL_MODE_PACKET_BYTES = 184
DEPTH_REGION_START = 64
DEPTH_REGION_BYTES = 120


class KiteDepthProtocolViolation(ValueError):
    pass


@dataclass(frozen=True)
class DepthLevelV1:
    quantity: int
    price: float
    orders: int


def _level(value: Any) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        raise KiteDepthProtocolViolation("KITE_DEPTH_PROTOCOL_VIOLATION:level_type")
    try:
        quantity, price, orders = int(value["quantity"]), float(value["price"]), int(value["orders"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise KiteDepthProtocolViolation("KITE_DEPTH_PROTOCOL_VIOLATION:field_type") from exc
    if not (0 <= quantity <= 0xFFFFFFFF and 0 <= orders <= 0xFFFF and price >= 0.0 and price < 0xFFFFFFFF):
        raise KiteDepthProtocolViolation("KITE_DEPTH_PROTOCOL_VIOLATION:field_range")
    return {"quantity": quantity, "price": price, "orders": orders}


def canonicalize_kite_depth(depth: Mapping[str, Any]) -> dict[str, list[dict[str, int | float]]]:
    if not isinstance(depth, Mapping):
        raise KiteDepthProtocolViolation("KITE_DEPTH_PROTOCOL_VIOLATION:depth_type")
    buy, sell = depth.get("buy"), depth.get("sell")
    if not isinstance(buy, list) or not isinstance(sell, list) or len(buy) != 5 or len(sell) != 5:
        raise KiteDepthProtocolViolation("KITE_DEPTH_PROTOCOL_VIOLATION:cardinality")
    return {"buy": [_level(item) for item in buy], "sell": [_level(item) for item in sell]}


_MAX_LEVEL = {"quantity": 4294967295, "price": 4294967295.0, "orders": 65535}
KITE_DEPTH_CANONICAL_MAX_BYTES = len(json.dumps({"buy": [_MAX_LEVEL] * 5, "sell": [_MAX_LEVEL] * 5}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def canonical_bytes(depth: Mapping[str, Any]) -> bytes:
    return json.dumps(canonicalize_kite_depth(depth), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
