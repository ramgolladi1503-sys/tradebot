from core.feed.artifact_provenance import (
    FEED_RUNTIME_CANONICAL_WRITER,
    FEED_RUNTIME_SCHEMA_VERSION,
    FEED_TRUTH_CANONICAL_WRITER,
    FEED_TRUTH_SCHEMA_VERSION,
    stamp_feed_runtime_provenance,
    stamp_feed_truth_provenance,
)
from core.feed.feed_epoch import _reset_feed_epoch_for_tests, advance_feed_epoch
from core.runtime_boot_identity import get_runtime_boot_identity


def setup_function():
    _reset_feed_epoch_for_tests()


def test_truth_provenance_uses_authoritative_identity_and_preserves_fields():
    original = {"feed_fresh": True, "feed_ok": False, "feed_epoch": 999, "writer": "spoof"}
    stamped = stamp_feed_truth_provenance(original)
    identity = get_runtime_boot_identity()
    assert stamped["run_id"] == identity.run_id
    assert stamped["boot_epoch"] == identity.boot_epoch
    assert stamped["feed_epoch"] == 0
    assert stamped["writer"] == FEED_TRUTH_CANONICAL_WRITER
    assert stamped["schema_version"] == FEED_TRUTH_SCHEMA_VERSION
    assert stamped["produced_at"] > 0
    assert stamped["feed_fresh"] is True
    assert original == {"feed_fresh": True, "feed_ok": False, "feed_epoch": 999, "writer": "spoof"}


def test_runtime_provenance_uses_current_epoch_and_preserves_feed_ok():
    advance_feed_epoch("TEST")
    stamped = stamp_feed_runtime_provenance({"feed_ok": True, "runtime_state": "RUNNING"})
    assert stamped["feed_epoch"] == 1
    assert stamped["writer"] == FEED_RUNTIME_CANONICAL_WRITER
    assert stamped["schema_version"] == FEED_RUNTIME_SCHEMA_VERSION
    assert stamped["feed_ok"] is True
    assert stamped["runtime_state"] == "RUNNING"


def test_caller_cannot_override_session_epoch_writer_or_schema():
    stamped = stamp_feed_runtime_provenance(
        {"run_id": "fake", "boot_epoch": -1, "feed_epoch": 999, "writer": "fake", "schema_version": 99}
    )
    identity = get_runtime_boot_identity()
    assert stamped["run_id"] == identity.run_id
    assert stamped["boot_epoch"] == identity.boot_epoch
    assert stamped["feed_epoch"] == 0
    assert stamped["writer"] == FEED_RUNTIME_CANONICAL_WRITER
    assert stamped["schema_version"] == FEED_RUNTIME_SCHEMA_VERSION


def test_truth_and_runtime_stamps_are_independent_copies():
    original = {"nested": {"x": 1}}
    truth = stamp_feed_truth_provenance(original)
    runtime = stamp_feed_runtime_provenance(original)
    truth["nested"]["x"] = 2
    assert runtime["nested"]["x"] == 1
    assert original["nested"]["x"] == 1
