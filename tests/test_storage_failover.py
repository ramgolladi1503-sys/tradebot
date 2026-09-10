from pathlib import Path
import pytest
from core.storage_failover import EmergencyAuthority, FailoverError, StorageEpochState, begin_failover, preflight_emergency_root, verify_cross_epoch, write_genesis


def test_emergency_preflight_is_dedicated_and_same_device(tmp_path):
    auth = preflight_emergency_root(session_id="s1", base=tmp_path / "emergency")
    assert auth.root == (tmp_path / "emergency" / "s1").resolve()
    assert auth.device_id == auth.root.stat().st_dev


def test_emergency_root_rejects_external_volume(tmp_path):
    with pytest.raises(FailoverError, match="MUST_NOT_BE_EXTERNAL"):
        preflight_emergency_root(session_id="s1", base=Path("/Volumes/TradeBotData"))


def test_failover_is_one_way_and_invalidates_admission(tmp_path):
    auth = preflight_emergency_root(session_id="s1", base=tmp_path / "emergency")
    state = StorageEpochState("s1", "source", "candidate")
    genesis = begin_failover(state, emergency=auth, reason="mount_disappeared", last_external_cycle_id="c0")
    assert state.storage_epoch == 1 and state.storage_authority == "EMERGENCY_INTERNAL"
    assert genesis["prospective_admission_state"] == "INVALIDATED_BY_STORAGE_FAILOVER"
    with pytest.raises(FailoverError, match="ONE_WAY"):
        begin_failover(state, emergency=auth, reason="again", last_external_cycle_id="c1")


def test_genesis_is_immutable(tmp_path):
    auth = preflight_emergency_root(session_id="s1", base=tmp_path / "emergency")
    state = StorageEpochState("s1", "source", "candidate")
    path = write_genesis(auth, begin_failover(state, emergency=auth, reason="write_failed", last_external_cycle_id=None))
    assert path.exists()
    with pytest.raises(FailoverError, match="ALREADY"):
        write_genesis(auth, {})


def test_independent_cross_epoch_verifier_passes_and_rejects_gap_identity(tmp_path):
    auth = preflight_emergency_root(session_id="s1", base=tmp_path / "emergency")
    state = StorageEpochState("s1", "source", "candidate")
    genesis = begin_failover(state, emergency=auth, reason="mount_disappeared", last_external_cycle_id="c0")
    ok, errors = verify_cross_epoch(genesis=genesis, records=[{"session_id": "s1", "source_sha": "source", "storage_epoch": 0}, {"session_id": "s1", "source_sha": "source", "storage_epoch": 1, "failover_event_id": genesis["failover_event_id"]}], session_id="s1", source_sha="source", candidate_sha="candidate")
    assert ok and not errors
    bad = dict(genesis); bad["prospective_admission_state"] = "ADMITTED"
    ok, errors = verify_cross_epoch(genesis=bad, records=[], session_id="s1", source_sha="source", candidate_sha="candidate")
    assert not ok and "ADMISSION_NOT_INVALIDATED" in errors
