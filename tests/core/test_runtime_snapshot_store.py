from __future__ import annotations

from pathlib import Path

from core import events
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


def test_runtime_snapshot_atomic_writer_uses_unique_temp_paths(tmp_path, monkeypatch):
    path = tmp_path / "runtime" / "advisory_latest.json"
    seen_sources: list[Path] = []

    def fake_replace(src, dst):
        seen_sources.append(Path(src))

    monkeypatch.setattr(events.os, "replace", fake_replace)

    write_snapshot_atomic(path, payload={"run": 1}, producer="unit_test")
    write_snapshot_atomic(path, payload={"run": 2}, producer="unit_test")

    assert len(seen_sources) == 2
    assert seen_sources[0] != seen_sources[1]
    assert seen_sources[0].name.startswith("advisory_latest.json.tmp.")
    assert seen_sources[1].name.startswith("advisory_latest.json.tmp.")
