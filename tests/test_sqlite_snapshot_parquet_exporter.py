from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pandas as pd
import pytest

import core.sqlite_snapshot_parquet_exporter as exporter
from core.sqlite_snapshot_parquet_exporter import create_consistent_snapshot, export_once


def _db(path: Path, journal: str = "WAL") -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA journal_mode={journal}")
        conn.execute("CREATE TABLE ticks (timestamp_epoch REAL, instrument_token INTEGER, last_price REAL)")
        conn.execute("CREATE TABLE depth_snapshots (timestamp_epoch REAL, instrument_token INTEGER, depth_json TEXT)")
        conn.execute("INSERT INTO ticks VALUES (1.0, 7, 100.0)")
        conn.execute("INSERT INTO depth_snapshots VALUES (1.0, 7, '{}')")


def test_snapshot_parquet_parity_and_atomic_publish(tmp_path: Path):
    db = tmp_path / "live.sqlite"
    out = tmp_path / "parquet"
    _db(db)
    result = export_once(db, out)
    assert result.status == "HEALTHY"
    assert result.exported == {"ticks": 1, "depth_snapshots": 1}
    assert len(pd.read_parquet(out / "ticks.parquet")) == 1
    assert len(pd.read_parquet(out / "depth_snapshots.parquet")) == 1
    assert not list(out.glob(".sqlite-snapshot-*.sqlite"))
    assert not list(out.glob(".*.parquet"))


def test_wal_writer_continues_while_snapshot_is_exported(tmp_path: Path):
    db = tmp_path / "live.sqlite"
    out = tmp_path / "parquet"
    _db(db)
    errors: list[Exception] = []

    def writer() -> None:
        try:
            with sqlite3.connect(db, timeout=2) as conn:
                for i in range(2, 32):
                    conn.execute("INSERT INTO ticks VALUES (?, 7, ?)", (float(i), float(i)))
                    conn.commit()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    result = export_once(db, out)
    thread.join(timeout=5)
    assert result.status == "HEALTHY"
    assert not errors


def test_snapshot_backup_uses_batched_no_delay_mode():
    assert exporter.SNAPSHOT_BACKUP_PAGES == 1024
    assert exporter.SNAPSHOT_BACKUP_SLEEP_SECONDS == 0.0


def test_production_path_guard(tmp_path: Path):
    db = tmp_path / "live.sqlite"
    with pytest.raises(ValueError):
        create_consistent_snapshot(db, db, production_path=db)


def test_failure_after_snapshot_preserves_existing_output(tmp_path: Path):
    db = tmp_path / "live.sqlite"
    out = tmp_path / "parquet"
    _db(db)
    out.mkdir()
    sentinel = out / "ticks.parquet"
    pd.DataFrame({"sentinel": [1]}).to_parquet(sentinel, index=False)
    result = export_once(db, out, failure_after_snapshot=True)
    assert result.status == "FAILED"
    assert pd.read_parquet(sentinel).to_dict("list") == {"sentinel": [1]}
    assert not list(out.glob(".sqlite-snapshot-*.sqlite"))


def test_snapshot_failure_preserves_existing_output(tmp_path: Path, monkeypatch):
    db = tmp_path / "live.sqlite"
    out = tmp_path / "parquet"
    _db(db)
    out.mkdir()
    sentinel = out / "ticks.parquet"
    pd.DataFrame({"sentinel": [2]}).to_parquet(sentinel, index=False)

    def fail(*_args, **_kwargs):
        raise RuntimeError("injected_snapshot_failure")

    monkeypatch.setattr("core.sqlite_snapshot_parquet_exporter.create_consistent_snapshot", fail)
    result = export_once(db, out)
    assert result.status == "FAILED"
    assert pd.read_parquet(sentinel).to_dict("list") == {"sentinel": [2]}
    assert not list(out.glob(".sqlite-snapshot-*.sqlite"))
