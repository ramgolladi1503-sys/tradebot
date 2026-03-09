from __future__ import annotations

import json
import os

from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
from core.market_snapshot_store import (
    get_market_snapshot_status,
    read_market_snapshot,
    write_market_snapshot_atomic,
)


def _sample_snapshot() -> dict:
    return build_market_snapshot(
        generated_at="2026-03-08T14:00:00Z",
        market_open=True,
        symbols_payload={
            "NIFTY": build_symbol_market_snapshot(spot=22500.0, ltp=22510.0),
        },
        warnings=[],
        compute_ms=3.2,
        loop_id="cycle-1",
    )


def test_writer_writes_atomically_and_reader_reads_valid_payload(tmp_path):
    path = tmp_path / "snapshots" / "market_snapshot_latest.json"
    snapshot = _sample_snapshot()

    written = write_market_snapshot_atomic(snapshot, path=path)
    loaded = read_market_snapshot(path)
    status = get_market_snapshot_status(path, now_ts=1_778_000_005.0, stale_after_sec=10_000_000_000.0)

    assert written == path
    assert loaded == snapshot
    assert status["state"] == "fresh"
    assert status["valid"] is True


def test_malformed_json_yields_invalid_status(tmp_path):
    path = tmp_path / "snapshots" / "market_snapshot_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad-json", encoding="utf-8")

    status = get_market_snapshot_status(path)

    assert status["state"] == "invalid"
    assert status["valid"] is False
    assert status["errors"]


def test_temp_write_failure_does_not_destroy_previous_valid_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "snapshots" / "market_snapshot_latest.json"
    initial = _sample_snapshot()
    write_market_snapshot_atomic(initial, path=path)
    updated = _sample_snapshot()
    updated["warnings"] = ["new-warning"]

    def _boom(src, dst):
        raise RuntimeError("replace_failed")

    monkeypatch.setattr(os, "replace", _boom)

    try:
        write_market_snapshot_atomic(updated, path=path)
    except RuntimeError:
        pass

    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded == initial
