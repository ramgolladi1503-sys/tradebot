from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.storage.events import EventStore
from core.storage.guard import (
    MODE_CRITICAL_MINIMAL,
    MODE_NORMAL,
    MODE_SNAPSHOTS_DISABLED,
    DiskGuard,
)
from core.storage.retention import RetentionManager
from core.storage.schema import build_event_record, config_version_hash
from core.storage.snapshots import SnapshotStore


def _read_gzip_jsonl(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_gzip_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def test_event_store_writes_gz_jsonl(tmp_path: Path):
    store = EventStore(base_dir=tmp_path, snapshot_store=None)

    out = store.store_event(
        {
            "event_type": "gate_rejected",
            "desk": "TEST",
            "mode": "PAPER",
            "symbols": ["NIFTY"],
            "reason_code": "premium_band_fail",
            "data_source": "decision",
            "missing_fields": ["bid", "ask"],
            "features_summary": {"confidence": 0.82},
        }
    )

    assert out is not None
    files = sorted((tmp_path / "events").glob("events_*.jsonl.gz"))
    assert files
    rows = _read_gzip_jsonl(files[0])
    assert rows
    row = rows[-1]
    assert row["event_type"] == "gate_rejected"
    assert row["symbols"] == ["NIFTY"]
    assert "event_id" in row
    assert "config_version" in row


def test_snapshot_store_writes_gz_jsonl(tmp_path: Path):
    guard = DiskGuard(tmp_path, min_free_pct=0.1, critical_free_pct=0.05)
    store = SnapshotStore(base_dir=tmp_path, guard=guard)

    out = store.store_snapshot(
        {
            "ts_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "instrument": {"symbol": "NIFTY", "instrument_token": 111},
            "ltp": 22451.5,
            "bid": 22451.0,
            "ask": 22452.0,
            "spread_pct": None,
            "depth_summary": {"best_bid": 22451.0, "best_ask": 22452.0},
            "oi": 1000,
            "volume": 500,
            "iv": 0.22,
            "capture_reason": {"around_event": "evt-1", "periodic": None},
        }
    )

    assert out is not None
    files = sorted((tmp_path / "snapshots").glob("snapshots_*.jsonl.gz"))
    assert files
    rows = _read_gzip_jsonl(files[0])
    assert rows
    row = rows[-1]
    assert row["instrument"]["symbol"] == "NIFTY"
    assert set(["snapshot_id", "ltp", "capture_reason"]).issubset(row.keys())


def test_retention_deletes_old_snapshots_and_keeps_events(tmp_path: Path):
    events_dir = tmp_path / "events"
    snaps_dir = tmp_path / "snapshots"
    today = datetime.now(timezone.utc).date()

    old_event = events_dir / f"events_{(today - timedelta(days=31)).isoformat()}.jsonl.gz"
    keep_event = events_dir / f"events_{(today - timedelta(days=2)).isoformat()}.jsonl.gz"
    old_snap = snaps_dir / f"snapshots_{(today - timedelta(days=9)).isoformat()}.jsonl.gz"
    keep_snap = snaps_dir / f"snapshots_{(today - timedelta(days=1)).isoformat()}.jsonl.gz"
    raw_event = events_dir / f"events_{today.isoformat()}.jsonl"
    temp_frag = snaps_dir / ".snapshots_fragment.tmp"

    _write_gzip_jsonl(old_event, {"k": "old_event"})
    _write_gzip_jsonl(keep_event, {"k": "keep_event"})
    _write_gzip_jsonl(old_snap, {"k": "old_snap"})
    _write_gzip_jsonl(keep_snap, {"k": "keep_snap"})
    raw_event.parent.mkdir(parents=True, exist_ok=True)
    raw_event.write_text(json.dumps({"k": "raw"}) + "\n", encoding="utf-8")
    temp_frag.parent.mkdir(parents=True, exist_ok=True)
    temp_frag.write_text("temp", encoding="utf-8")

    manager = RetentionManager(tmp_path, keep_events_days=30, keep_snapshots_days=7)
    result = manager.run(dry_run=False)

    assert result["compressed"] >= 1
    assert result["deleted_events"] >= 1
    assert result["deleted_snapshots"] >= 1
    assert result["deleted_temp_fragments"] >= 1
    assert not old_event.exists()
    assert keep_event.exists()
    assert not old_snap.exists()
    assert keep_snap.exists()
    assert not raw_event.exists()
    assert raw_event.with_suffix(".jsonl.gz").exists()


def test_disk_guard_degrades_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core.storage import guard as guard_mod

    vals = iter(
        [
            SimpleNamespace(total=100.0, free=20.0),
            SimpleNamespace(total=100.0, free=8.0),
            SimpleNamespace(total=100.0, free=4.0),
            SimpleNamespace(total=100.0, free=4.0),
            SimpleNamespace(total=100.0, free=4.0),
        ]
    )

    def _fake_disk_usage(_path):
        return next(vals)

    monkeypatch.setattr(guard_mod.shutil, "disk_usage", _fake_disk_usage)
    guard = DiskGuard(tmp_path, min_free_pct=10.0, critical_free_pct=5.0)

    assert guard.refresh().mode == MODE_NORMAL
    assert guard.refresh().mode == MODE_SNAPSHOTS_DISABLED
    assert guard.refresh().mode == MODE_CRITICAL_MINIMAL
    assert guard.should_emit_disk_critical() is True
    assert guard.should_emit_disk_critical() is False


def test_config_hash_stable():
    cfg_a = {"ORB_WINDOW_MIN": 15, "PREMIUM_BAND": 0.03, "STRICT_QUOTES": True}
    cfg_b = {"STRICT_QUOTES": True, "PREMIUM_BAND": 0.03, "ORB_WINDOW_MIN": 15}
    assert config_version_hash(cfg_a) == config_version_hash(cfg_b)


def test_event_payload_size_capped():
    features = {f"k{i}": "x" * 200 for i in range(100)}
    record = build_event_record(
        {
            "event_type": "gate_rejected",
            "desk": "TEST",
            "mode": "PAPER",
            "symbols": ["NIFTY"],
            "reason_code": "too_large",
            "features_summary": features,
            "data_source": "decision",
        },
        config_version="abc123def456",
        features_max_bytes=512,
        features_max_keys=100,
    )
    encoded = json.dumps(record.features_summary or {}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= 512
    assert record.features_summary


def test_atomic_write_no_partial_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core.storage import events as events_mod
    from core.storage.guard import DiskGuard

    # Force NORMAL mode regardless of host disk pressure to keep this atomic-write
    # test deterministic.
    guard = DiskGuard(tmp_path, min_free_pct=0.0, critical_free_pct=-1.0)
    store = EventStore(base_dir=tmp_path, guard=guard, snapshot_store=None)
    first = store.store_event(
        {
            "event_type": "trade_accepted",
            "desk": "TEST",
            "mode": "PAPER",
            "symbols": ["NIFTY"],
            "data_source": "trade_store",
        }
    )
    assert first is not None

    def _fail_replace(_src, _dst):
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(events_mod.os, "replace", _fail_replace)
    second = store.store_event(
        {
            "event_type": "trade_exited",
            "desk": "TEST",
            "mode": "PAPER",
            "symbols": ["NIFTY"],
            "data_source": "trade_store",
        }
    )
    assert second is None

    files = sorted((tmp_path / "events").glob("events_*.jsonl.gz"))
    assert files
    rows = _read_gzip_jsonl(files[0])
    assert len(rows) == 1
    assert rows[0]["event_type"] == "trade_accepted"
