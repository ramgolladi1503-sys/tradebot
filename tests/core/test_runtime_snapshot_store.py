from __future__ import annotations

from core.runtime_snapshot_store import build_snapshot_envelope, read_snapshot, write_snapshot_atomic


def test_runtime_snapshot_store_writes_expected_envelope(tmp_path):
    path = tmp_path / "runtime" / "advisory_latest.json"
    payload = {"rows": [{"advisory_id": "ADV-1", "symbol": "NIFTY"}], "row_count": 1}

    written = write_snapshot_atomic(path, payload=payload, producer="unit_test")
    loaded = read_snapshot(path)

    assert written == path
    assert loaded["schema_version"] == 1
    assert loaded["producer"] == "unit_test"
    assert loaded["payload"] == payload


def test_runtime_snapshot_envelope_preserves_payload_roundtrip():
    payload = {"ok": True, "count": 2}

    wrapped = build_snapshot_envelope(payload=payload, producer="unit_test", generated_at="2026-03-10T12:00:00Z")

    assert wrapped == {
        "schema_version": 1,
        "generated_at": "2026-03-10T12:00:00Z",
        "producer": "unit_test",
        "payload": payload,
    }
