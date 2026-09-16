from __future__ import annotations

import json
from datetime import datetime

import dashboard.upstox_option_chain_reader as reader


def test_missing_snapshot_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "PRIMARY_BASE_DIR", tmp_path / "primary")
    monkeypatch.setattr(reader, "FALLBACK_BASE_DIR", tmp_path / "fallback")
    snap = reader.load_upstox_option_chain_snapshot(now=datetime(2026, 9, 17, 10, 0, 0))
    assert snap.status == "missing"
    assert snap.payload == {}


def test_snapshot_freshness_is_receive_only(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "PRIMARY_BASE_DIR", tmp_path)
    monkeypatch.setattr(reader, "FALLBACK_BASE_DIR", tmp_path / "fallback")
    now = datetime(2026, 9, 17, 10, 0, 0)
    day = tmp_path / "2026-09-17"
    day.mkdir()
    (day / reader.SNAPSHOT_NAME).write_text(json.dumps({"written_epoch": now.timestamp() - 1, "chains": {}}))
    snap = reader.load_upstox_option_chain_snapshot(now=now, stale_after_sec=5)
    assert snap.status == "fresh"
    assert 0 <= snap.age_sec <= 5
