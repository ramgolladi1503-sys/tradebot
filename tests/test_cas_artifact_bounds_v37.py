import pytest

from core.read_only_consumer_cycle import _write_bounded_json
from core.storage_bounds_v37 import MAX_ATOMIC_ARTIFACT_BYTES, StorageBoundViolation


def test_cas_artifact_writer_is_atomic_and_bounded(tmp_path):
    target = tmp_path / "cas_readiness_latest.json"
    _write_bounded_json(target, {"readiness_state": "PENDING"})
    assert target.exists()
    assert not target.with_name(target.name + ".tmp").exists()


def test_cas_artifact_writer_rejects_oversized_payload(tmp_path):
    with pytest.raises(StorageBoundViolation):
        _write_bounded_json(tmp_path / "cas.json", {"payload": "x" * MAX_ATOMIC_ARTIFACT_BYTES})
