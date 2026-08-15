from concurrent.futures import ThreadPoolExecutor

import pytest

from core.feed.feed_epoch import (
    _reset_feed_epoch_for_tests,
    advance_feed_epoch,
    current_feed_epoch,
    feed_epoch_audit,
)
from core.runtime_boot_identity import get_runtime_boot_identity


def setup_function():
    _reset_feed_epoch_for_tests()


def test_initial_value_is_deterministic():
    assert current_feed_epoch() == 0


def test_query_is_read_only():
    assert current_feed_epoch() == current_feed_epoch() == 0


def test_sequential_advance_is_monotonic():
    assert advance_feed_epoch("WS_RECONNECT") == 1
    assert advance_feed_epoch("RECOVERY", {"source": "test"}) == 2
    assert current_feed_epoch() == 2


def test_concurrent_advancement_has_no_lost_updates():
    count = 64
    with ThreadPoolExecutor(max_workers=8) as executor:
        returned = list(executor.map(lambda i: advance_feed_epoch(f"TEST_{i}"), range(count)))
    assert sorted(returned) == list(range(1, count + 1))
    assert current_feed_epoch() == count


def test_advancement_audit_contains_transition_and_session():
    advance_feed_epoch("ATM_REBALANCE", {"changed": True})
    event = feed_epoch_audit()[-1]
    identity = get_runtime_boot_identity()
    assert event["old_epoch"] == 0
    assert event["new_epoch"] == 1
    assert event["reason"] == "ATM_REBALANCE"
    assert event["metadata"] == {"changed": True}
    assert event["run_id"] == identity.run_id
    assert event["boot_epoch"] == identity.boot_epoch
    assert event["timestamp"] > 0


def test_input_metadata_is_deeply_copied():
    metadata = {"nested": {"x": 1}, "items": ["a"]}
    advance_feed_epoch("TEST", metadata)
    metadata["nested"]["x"] = 999
    metadata["items"].append("mutated")
    event = feed_epoch_audit()[0]
    assert event["metadata"] == {"nested": {"x": 1}, "items": ["a"]}


def test_returned_snapshot_is_deeply_independent():
    advance_feed_epoch("TEST", {"nested": {"x": 1}, "items": ["a"]})
    snapshot = feed_epoch_audit()
    snapshot[0]["metadata"]["nested"]["x"] = 999
    snapshot[0]["metadata"]["items"].append("mutated")
    assert feed_epoch_audit()[0]["metadata"] == {"nested": {"x": 1}, "items": ["a"]}


def test_multiple_snapshots_do_not_share_mutable_state():
    advance_feed_epoch("TEST", {"nested": {"x": 1}})
    first = feed_epoch_audit()
    second = feed_epoch_audit()
    first[0]["metadata"]["nested"]["x"] = 2
    assert second[0]["metadata"]["nested"]["x"] == 1
    assert feed_epoch_audit()[0]["metadata"]["nested"]["x"] == 1


def test_reason_is_required():
    with pytest.raises(ValueError):
        advance_feed_epoch(" ")


def test_session_scope_is_not_global_identity():
    advance_feed_epoch("TEST")
    identity = get_runtime_boot_identity()
    assert current_feed_epoch() == 1
    assert identity.run_id
    assert identity.boot_epoch
    # Numeric epochs are intentionally session-local; session identity binds them later.


def test_m1_has_no_implicit_lifecycle_wiring():
    assert feed_epoch_audit() == ()
