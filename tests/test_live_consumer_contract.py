import pytest

from core.live_consumer_contract import (
    CANONICAL_CONSUMERS,
    canonical_consumer_registry,
    consumer_authority_snapshot,
    validate_consumer_registry,
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
