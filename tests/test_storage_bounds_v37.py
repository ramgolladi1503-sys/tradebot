import pytest

from core.kite_depth_protocol import canonical_bytes
from core.storage_bounds_v37 import (
    MAX_DEPTH_QUEUE_ITEM_BYTES,
    MAX_PERSISTENCE_BATCH_BYTES,
    MAX_TICK_ITEM_BYTES,
    StorageBoundViolation,
    depth_queue_item_bytes,
    persistence_batch_bytes,
    tick_item_bytes,
)


def _depth():
    level = {"quantity": 4_294_967_295, "price": 4_294_967_294.0, "orders": 65_535}
    return {"buy": [level] * 5, "sell": [level] * 5}


def _row():
    return (
        "2026-09-06T09:15:00.000000+05:30", 4_294_967_295, 4_294_967_294.0,
        4_294_967_295, 4_294_967_295, 4_294_967_295.0,
        "2026-09-06T09:15:00.000000+05:30", "RECEIPT", "exchange_timestamp",
        4_294_967_295.0, 4_294_967_295.0, False,
    )


def test_protocol_and_derived_maxima_are_exact():
    assert len(canonical_bytes(_depth())) == 618
    assert depth_queue_item_bytes("2026-09-06T09:15:00.000000+05:30", 4_294_967_295, _depth(), 1.0) == MAX_DEPTH_QUEUE_ITEM_BYTES
    assert tick_item_bytes(_row()) == MAX_TICK_ITEM_BYTES
    assert persistence_batch_bytes([_row()] * 1000) == MAX_PERSISTENCE_BATCH_BYTES


def test_depth_rejects_noncanonical_cardinality():
    bad = _depth()
    bad["buy"] = bad["buy"][:-1]
    with pytest.raises(ValueError):
        depth_queue_item_bytes("2026-09-06T09:15:00Z", 1, bad, 0.0)


def test_tick_rejects_oversized_provenance():
    row = list(_row())
    row[7] = "x" * 65
    with pytest.raises(StorageBoundViolation, match="timestamp_authority_BYTES_EXCEEDED"):
        tick_item_bytes(tuple(row))


def test_batch_rejects_more_than_1000_rows():
    with pytest.raises(StorageBoundViolation, match="ROW_COUNT_EXCEEDED"):
        persistence_batch_bytes([_row()] * 1001)
