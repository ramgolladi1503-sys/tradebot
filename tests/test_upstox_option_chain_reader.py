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


def test_explicit_snapshot_root_isolated_from_live_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSTOX_UI_SNAPSHOT_ROOT", str(tmp_path))
    now = datetime(2026, 9, 17, 10, 0, 0)
    day = tmp_path / "2026-09-17"
    day.mkdir()
    (day / reader.SNAPSHOT_NAME).write_text(json.dumps({
        "written_epoch": now.timestamp() - 1,
        "subscribed_count": 1,
        "observed_count": 1,
        "chains": {"NIFTY": {"rows": [{"strike": 25000}]}},
    }))
    snap = reader.load_upstox_option_chain_snapshot(now=now, stale_after_sec=5)
    assert snap.status == "fresh"
    assert 0 <= snap.age_sec <= 5


def test_fresh_timestamp_with_incomplete_chain_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSTOX_UI_SNAPSHOT_ROOT", str(tmp_path))
    now = datetime(2026, 9, 17, 10, 0, 0)
    day = tmp_path / "2026-09-17"
    day.mkdir()
    (day / reader.SNAPSHOT_NAME).write_text(json.dumps({"written_epoch": now.timestamp() - 1, "chains": {}}))
    snap = reader.load_upstox_option_chain_snapshot(now=now, stale_after_sec=5)
    assert snap.status == "incomplete"
    assert snap.message == "snapshot_has_no_option_chain_rows"
