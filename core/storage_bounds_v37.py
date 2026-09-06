"""Deterministic byte bounds for V37 runtime storage admission.

This module is deliberately pure: it does not perform I/O, change risk policy,
or grant broker authority.  Runtime writers may use it to reject an item or
batch before crossing a material write boundary.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from core.kite_depth_protocol import KITE_DEPTH_CANONICAL_MAX_BYTES, canonical_bytes

V37_SCHEMA_VERSION = 1
DEPTH_QUEUE_MAX_ITEMS = 16_384
TICK_QUEUE_MAX_ITEMS = 10_000
PERSISTENCE_BATCH_MAX_ITEMS = 1_000

# Fixed-width provenance envelope limits.  Values are protocol fields, not
# arbitrary diagnostic text.  The queue stores the canonical depth JSON plus
# the bounded SQLite input envelope.
MAX_ISO_TIMESTAMP_BYTES = 32
MAX_TOKEN_TEXT_BYTES = 20
MAX_SCHEMA_VERSION_BYTES = 8
MAX_REASON_CODE_BYTES = 64
MAX_DEPTH_QUEUE_ITEM_BYTES = 742
MAX_TICK_ITEM_BYTES = 193
MAX_PERSISTENCE_BATCH_BYTES = MAX_TICK_ITEM_BYTES * PERSISTENCE_BATCH_MAX_ITEMS
SQLITE_PAGE_SIZE_BYTES = 4096
MAX_SQLITE_WAL_BYTES = 16 * SQLITE_PAGE_SIZE_BYTES
MAX_ATOMIC_ARTIFACT_BYTES = 1_048_576


class StorageBoundViolation(ValueError):
    """Raised when a material item exceeds its governed bound."""


@dataclass(frozen=True)
class Bound:
    name: str
    max_items: int
    max_item_bytes: int

    @property
    def max_bytes(self) -> int:
        return self.max_items * self.max_item_bytes


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def bounded_utf8(value: Any, maximum: int, field: str) -> bytes:
    raw = str(value).encode("utf-8")
    if len(raw) > maximum:
        raise StorageBoundViolation(f"{field}_BYTES_EXCEEDED")
    return raw


def depth_queue_item_bytes(timestamp_iso: str, token: int | str,
                           depth: Mapping[str, Any], imbalance: float) -> int:
    canonical = canonical_bytes(depth)
    # The envelope is the exact serialized payload submitted to the DB writer.
    payload = {"depth": json.loads(canonical.decode("utf-8")),
               "imbalance": float(imbalance)}
    envelope = {"timestamp": str(timestamp_iso), "token": int(token),
                "payload": payload, "receipt_epoch": 0.0}
    bounded_utf8(timestamp_iso, MAX_ISO_TIMESTAMP_BYTES, "timestamp")
    bounded_utf8(token, MAX_TOKEN_TEXT_BYTES, "token")
    return len(_canonical_json(envelope))


def tick_item_bytes(row: tuple[Any, ...]) -> int:
    if len(row) != 12:
        raise StorageBoundViolation("TICK_ROW_FIELD_COUNT")
    values = list(row)
    bounded_utf8(values[0], MAX_ISO_TIMESTAMP_BYTES, "timestamp")
    bounded_utf8(values[6], MAX_ISO_TIMESTAMP_BYTES, "timestamp_iso")
    for index, field in ((7, "timestamp_authority"), (8, "timestamp_source_field")):
        if values[index] is not None:
            bounded_utf8(values[index], MAX_REASON_CODE_BYTES, field)
    return len(_canonical_json(values))


def derive_bounds(*, depth_item_bytes: int, tick_item_bytes: int,
                  batch_item_bytes: int) -> dict[str, Bound]:
    values = (depth_item_bytes, tick_item_bytes, batch_item_bytes)
    if any(int(v) <= 0 for v in values):
        raise ValueError("BOUNDS_MUST_BE_POSITIVE")
    return {
        "depth_queue": Bound("depth_queue", DEPTH_QUEUE_MAX_ITEMS, int(depth_item_bytes)),
        "tick_queue": Bound("tick_queue", TICK_QUEUE_MAX_ITEMS, int(tick_item_bytes)),
        "persistence_batch": Bound("persistence_batch", PERSISTENCE_BATCH_MAX_ITEMS, int(batch_item_bytes)),
    }


def require_item_size(actual_bytes: int, maximum: int, field: str) -> None:
    if int(actual_bytes) > int(maximum):
        raise StorageBoundViolation(f"{field}_ITEM_BYTES_EXCEEDED")


def persistence_batch_bytes(rows: list[tuple[Any, ...]]) -> int:
    if len(rows) > PERSISTENCE_BATCH_MAX_ITEMS:
        raise StorageBoundViolation("PERSISTENCE_BATCH_ROW_COUNT_EXCEEDED")
    total = sum(tick_item_bytes(row) for row in rows)
    require_item_size(total, MAX_PERSISTENCE_BATCH_BYTES, "PERSISTENCE_BATCH")
    return total


__all__ = [
    "Bound", "DEPTH_QUEUE_MAX_ITEMS", "TICK_QUEUE_MAX_ITEMS",
    "PERSISTENCE_BATCH_MAX_ITEMS", "KITE_DEPTH_CANONICAL_MAX_BYTES",
    "StorageBoundViolation", "derive_bounds", "depth_queue_item_bytes",
    "tick_item_bytes", "persistence_batch_bytes", "require_item_size",
    "MAX_DEPTH_QUEUE_ITEM_BYTES", "MAX_TICK_ITEM_BYTES", "MAX_PERSISTENCE_BATCH_BYTES",
    "SQLITE_PAGE_SIZE_BYTES", "MAX_SQLITE_WAL_BYTES", "MAX_ATOMIC_ARTIFACT_BYTES",
]
