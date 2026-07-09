from __future__ import annotations

from pathlib import Path

from config import config as cfg
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

    assert len(seen_sources) == 4
    assert len({source.name for source in seen_sources}) == 4
    assert seen_sources[0].name.startswith("advisory_latest.json.tmp.")
    assert any(source.name.startswith("advisory_latest.json.sha256.tmp.") for source in seen_sources)


def test_runtime_snapshot_atomic_writer_skips_unchanged_payload_when_dedup_enabled(tmp_path, monkeypatch):
    path = tmp_path / "runtime" / "advisory_latest.json"
    monkeypatch.setattr(cfg, "RUNTIME_SNAPSHOT_WRITE_DEDUP_ENABLE", True, raising=False)

    write_snapshot_atomic(path, payload={"run": 1}, producer="unit_test", generated_at="2026-03-10T12:00:00Z")
    first_mtime = path.stat().st_mtime
    write_snapshot_atomic(path, payload={"run": 1}, producer="unit_test", generated_at="2026-03-10T12:00:00Z")
    assert path.stat().st_mtime == first_mtime
