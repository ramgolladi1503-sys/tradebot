"""Unit and adversarial attack tests for governed audit-chain forensic recovery."""
import hashlib
import json
import pytest
from pathlib import Path
from core.audit_chain_recovery import perform_audit_chain_rollover
from core.audit_log import verify_chain, GENESIS, append_event


def test_forensic_rollover_preserves_archive_and_rebinds_genesis(tmp_path, monkeypatch):
    """Verify broken audit log is preserved, hashed, and cleanly rebound to GENESIS."""
    log_dir = tmp_path / "desks" / "DEFAULT"
    log_dir.mkdir(parents=True)
    corrupt_log = log_dir / "audit_log.jsonl"

    # Create a corrupted log starting without GENESIS
    corrupt_events = [
        {
            "event": "STARTUP_AUDIT_CHAIN_FAIL",
            "desk_id": "DEFAULT",
            "prev_hash": "orphaned_hash_1111",
            "event_hash": "hash_line_0",
            "ts_ist": "2026-09-17T07:48:42+05:30",
        },
        {
            "event": "STARTUP_AUDIT_CHAIN_FAIL",
            "desk_id": "DEFAULT",
            "prev_hash": "hash_line_0",
            "event_hash": "hash_line_1",
            "ts_ist": "2026-09-17T07:49:15+05:30",
        },
    ]
    corrupt_text = "\n".join(json.dumps(e) for e in corrupt_events) + "\n"
    corrupt_log.write_text(corrupt_text, encoding="utf-8")
    orig_sha = hashlib.sha256(corrupt_log.read_bytes()).hexdigest()

    # Pre-condition: verify_chain fails
    ok, status, count = verify_chain(corrupt_log)
    assert ok is False
    assert status == "missing_hash_fields" or status == "prev_hash_mismatch"

    # Perform governed rollover
    res = perform_audit_chain_rollover(
        audit_log_path=corrupt_log,
        reason="test_forensic_rollover",
        tool_sha="test_tool_sha_123",
        certified_release_sha="test_cert_sha_456",
        new_run_id="session_test_run_01",
    )

    assert res["success"] is True
    assert res["count"] == 1
    assert res["archive_sha256"] == orig_sha

    # Verify archive exists and matches original SHA
    arch_path = Path(res["archive_path"])
    assert arch_path.is_file()
    assert hashlib.sha256(arch_path.read_bytes()).hexdigest() == orig_sha

    # Verify manifest exists and records forensic data
    man_path = Path(res["manifest_path"])
    assert man_path.is_file()
    man_data = json.loads(man_path.read_text(encoding="utf-8"))
    assert man_data["archive_sha256"] == orig_sha
    assert man_data["total_records"] == 2
    assert man_data["first_record_prev_hash"] == "orphaned_hash_1111"

    # Verify new audit log is valid from GENESIS
    ok, status, count = verify_chain(corrupt_log, expected_run_id="session_test_run_01")
    assert ok is True
    assert count == 1
    assert status == res["new_genesis_hash"]

    # Verify rollover forensic evidence in bootstrap event
    first_record = json.loads(corrupt_log.read_text().splitlines()[0])
    assert first_record["event"] == "AUDIT_CHAIN_BOOTSTRAP"
    assert first_record["prev_hash"] == GENESIS
    evidence = first_record["rollover_forensic_evidence"]
    assert evidence["predecessor_archive_sha256"] == orig_sha
    assert evidence["rollover_reason"] == "test_forensic_rollover"


def test_forensic_rollover_missing_file_raises(tmp_path):
    """Missing file fails closed."""
    missing = tmp_path / "missing_audit_log.jsonl"
    with pytest.raises(FileNotFoundError):
        perform_audit_chain_rollover(audit_log_path=missing)
