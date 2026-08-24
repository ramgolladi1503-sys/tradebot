import pytest

from core.live_consumer_contract import (
    CANONICAL_CONSUMERS,
    canonical_consumer_registry,
    consumer_authority_snapshot,
    validate_consumer_registry,
    write_consumer_registry,
)


def test_canonical_registry_covers_all_read_only_consumers():
    assert validate_consumer_registry() == CANONICAL_CONSUMERS
    assert tuple(item.name for item in canonical_consumer_registry()) == CANONICAL_CONSUMERS
    assert all(item.read_only and not item.execution_capable for item in canonical_consumer_registry())


def test_registry_rejects_missing_or_duplicate_consumer():
    with pytest.raises(ValueError, match="incomplete_or_duplicate"):
        validate_consumer_registry(CANONICAL_CONSUMERS[:-1])
    with pytest.raises(ValueError, match="incomplete_or_duplicate"):
        validate_consumer_registry((*CANONICAL_CONSUMERS, "ui"))


def test_authority_snapshot_is_fail_closed():
    snapshot = consumer_authority_snapshot()
    assert snapshot["read_only"] is True
    assert snapshot["execution_capable"] is False
    assert snapshot["broker_write_authority"] is False
    assert snapshot["order_authority"] is False
    assert snapshot["paper_authorized"] is False
    assert snapshot["live_execution_authorized"] is False


def test_consumer_registry_artifact_binds_identity_and_stays_pending(tmp_path):
    import json
    path = tmp_path / "CONSUMERS.json"
    write_consumer_registry(path, session_id="s1", source_sha="a" * 40)
    payload = json.loads(path.read_text())
    assert payload["session_id"] == "s1"
    assert payload["source_sha"] == "a" * 40
    assert len(payload["consumers"]) == len(CANONICAL_CONSUMERS)
    assert {row["health"] for row in payload["consumers"]} == {"PENDING"}
    assert all(row["execution_capable"] is False for row in payload["consumers"])
