from __future__ import annotations

from config import config as cfg
from core.runtime_snapshot_store import (
    build_snapshot_envelope,
    read_ranked_pipeline_snapshot,
    read_snapshot,
    write_snapshot_atomic,
)


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


def test_runtime_snapshot_atomic_writer_updates_sidecar_hash_on_content_change(tmp_path):
    path = tmp_path / "runtime" / "advisory_latest.json"
    first_written = write_snapshot_atomic(path, payload={"run": 1}, producer="unit_test")
    hash_path = path.with_name(f"{path.name}.sha256")
    first_hash = hash_path.read_text(encoding="utf-8")

    second_written = write_snapshot_atomic(path, payload={"run": 2}, producer="unit_test")
    second_hash = hash_path.read_text(encoding="utf-8")

    assert first_written == path
    assert second_written == path
    assert read_snapshot(path)["payload"] == {"run": 2}
    assert first_hash != second_hash


def test_runtime_snapshot_store_exposes_ranked_pipeline_reader(tmp_path, monkeypatch):
    path = tmp_path / "runtime" / "opportunities" / "ranked_pipeline_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_snapshot_atomic(path, payload={"reports": []}, producer="unit_test")
    monkeypatch.setattr("core.runtime_snapshot_store.RANKED_PIPELINE_LATEST_PATH", path)

    loaded = read_ranked_pipeline_snapshot()

    assert loaded["payload"] == {"reports": []}
