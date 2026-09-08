import json
import pytest
from core.kite_depth_protocol import KITE_DEPTH_CANONICAL_MAX_BYTES, KiteDepthProtocolViolation, canonical_bytes, canonicalize_kite_depth


def level(i=1):
    return {"quantity": i, "price": 100.0 + i, "orders": i}


def depth():
    return {"buy": [level(i) for i in range(1, 6)], "sell": [level(i) for i in range(6, 11)]}


def test_exact_five_by_five_roundtrip_preserves_all_fields():
    canonical = canonicalize_kite_depth(depth())
    assert canonical == depth()
    assert len(canonical_bytes(canonical)) <= KITE_DEPTH_CANONICAL_MAX_BYTES


@pytest.mark.parametrize("bad", [
    {"buy": [level()] * 4, "sell": [level()] * 5},
    {"buy": [level()] * 5, "sell": [level()] * 4},
    {"buy": [level()] * 6, "sell": [level()] * 5},
    {"buy": [level()] * 5, "sell": [level()] * 6},
    {"buy": list(range(10)), "sell": []},
])
def test_cardinality_violation_is_rejected_not_truncated(bad):
    with pytest.raises(KiteDepthProtocolViolation, match="cardinality"):
        canonicalize_kite_depth(bad)


def test_field_type_and_range_violations_fail_closed():
    bad = depth(); bad["buy"][0] = {"quantity": -1, "price": 1, "orders": 1}
    with pytest.raises(KiteDepthProtocolViolation): canonicalize_kite_depth(bad)
    bad = depth(); bad["sell"][0] = {"quantity": 1, "price": "bad", "orders": 1}
    with pytest.raises(KiteDepthProtocolViolation): canonicalize_kite_depth(bad)
