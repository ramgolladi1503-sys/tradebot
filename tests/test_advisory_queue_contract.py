import json

import pytest

from core.advisory_queue_contract import append_advisory, normalize_advisory


def _row():
    return {"candidate_id": "c1", "strategy_id": "cas_v2", "timestamp": "2026-08-24T09:15:00Z", "source_sha": "a" * 40, "spec_sha": "b" * 64, "execution_status": "advisory_only", "direction": "UP"}


def test_advisory_queue_is_read_only_and_hashes_rows(tmp_path):
    path = tmp_path / "ADVISORY_QUEUE.jsonl"
    digest = append_advisory(path, _row(), session_id="s1")
    payload = json.loads(path.read_text().strip())
    assert payload["advisory_sha256"] == digest
    assert payload["order_authority"] is False
    assert payload["orders_placed"] == 0


def test_advisory_queue_rejects_execution_status():
    row = _row()
    row["execution_status"] = "live"
    with pytest.raises(ValueError, match="advisory_only"):
        normalize_advisory(row, session_id="s1")
