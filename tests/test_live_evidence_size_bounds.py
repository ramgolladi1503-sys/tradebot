"""Tests for read-only live evidence record and file size bounds."""
import pytest
from pathlib import Path
from core.read_only_live_evidence import append_jsonl_record, _LIVE_EVIDENCE_MAX_RECORD_BYTES, _LIVE_EVIDENCE_MAX_FILE_BYTES


def test_live_evidence_constants():
    """Verify live evidence limits are 2 MiB and 64 MiB."""
    assert _LIVE_EVIDENCE_MAX_RECORD_BYTES == 2 * 1024 * 1024
    assert _LIVE_EVIDENCE_MAX_FILE_BYTES == 64 * 1024 * 1024


def test_append_record_under_limit(tmp_path):
    """A record under 2 MiB (e.g. 350 KiB bundle) succeeds."""
    evidence_file = tmp_path / "authority_snapshots.jsonl"
    payload = {
        "cycle_count": 1,
        "candidates": [{"id": f"c_{i}", "data": "x" * 10000} for i in range(35)]  # ~350 KiB
    }
    rec = append_jsonl_record(evidence_file, payload, hash_field="snapshot_sha256")
    assert "snapshot_sha256" in rec
    assert evidence_file.stat().st_size > 350000


def test_append_record_over_limit_fails_closed(tmp_path):
    """A record exceeding 2 MiB is rejected with OSError."""
    evidence_file = tmp_path / "oversized.jsonl"
    payload = {
        "cycle_count": 1,
        "large_blob": "x" * (2 * 1024 * 1024 + 100)  # >2 MiB
    }
    with pytest.raises(OSError, match="bounded_jsonl_write_rejected"):
        append_jsonl_record(evidence_file, payload, hash_field="snapshot_sha256")
    assert not evidence_file.exists() or evidence_file.stat().st_size == 0
