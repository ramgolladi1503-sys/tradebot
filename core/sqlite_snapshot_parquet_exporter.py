"""Non-blocking SQLite snapshot exporter for live market-data artifacts."""
from __future__ import annotations

import os
import json
import signal
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd


class SnapshotDeadlineExceeded(TimeoutError):
    pass


@dataclass(frozen=True)
class ExportResult:
    status: str
    snapshot_path: Path | None
    exported: dict[str, int]
    failure_class: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "PARQUET_EXPORT_STATUS": self.status,
            "PARQUET_EXPORT_READS_LIVE_SQLITE": False,
            "exported_rows": dict(self.exported),
            "snapshot_path": str(self.snapshot_path) if self.snapshot_path else None,
            "failure_class": self.failure_class,
        }


def _assert_distinct(source: Path, production: Path | None) -> None:
    if production is not None and source.resolve() == production.resolve():
        raise ValueError("EXPORT_SOURCE_PATH_MUST_NOT_BE_PRODUCTION_SQLITE_PATH")


def create_consistent_snapshot(
    source: Path,
    destination: Path,
    *,
    deadline_seconds: float = 10.0,
    production_path: Path | None = None,
) -> None:
    """Copy a consistent DB image, then close every source connection."""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("SNAPSHOT_PATH_MUST_DIFFER_FROM_SOURCE")
    destination.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.1, float(deadline_seconds))
    src = dst = None
    try:
        src = sqlite3.connect(str(source), timeout=max(0.1, deadline_seconds))
        dst = sqlite3.connect(str(destination), timeout=max(0.1, deadline_seconds))

        def progress(_status: int, _remaining: int, _total: int) -> None:
            if time.monotonic() > deadline:
                raise SnapshotDeadlineExceeded("snapshot_deadline_exceeded")

        src.backup(dst, pages=128, progress=progress, sleep=0.01)
        dst.commit()
    finally:
        if src is not None:
            src.close()
        if dst is not None:
            dst.close()


def _read_snapshot(snapshot: Path, table: str) -> pd.DataFrame:
    uri = f"file:{snapshot.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return pd.DataFrame()
        return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)


def export_snapshot_to_parquet(
    snapshot: Path,
    output_dir: Path,
    *,
    tables: tuple[str, ...] = ("ticks", "depth_snapshots"),
    failure_after_snapshot: bool = False,
    production_path: Path | None = None,
) -> dict[str, int]:
    """Export only from an immutable snapshot and publish each file atomically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _assert_distinct(snapshot, production_path)
    if failure_after_snapshot:
        raise RuntimeError("injected_export_failure")
    counts: dict[str, int] = {}
    for table in tables:
        frame = _read_snapshot(snapshot, table)
        target = output_dir / f"{table}.parquet"
        with NamedTemporaryFile(prefix=f".{table}.", suffix=".parquet", dir=output_dir, delete=False) as tmp:
            temp = Path(tmp.name)
        try:
            frame.to_parquet(temp, index=False, engine="pyarrow")
            check = pd.read_parquet(temp, engine="pyarrow")
            if len(check) != len(frame) or list(check.columns) != list(frame.columns):
                raise ValueError(f"parquet_validation_failed:{table}")
            os.replace(temp, target)
            counts[table] = len(frame)
        finally:
            temp.unlink(missing_ok=True)
    return counts


def export_once(
    production_db: Path,
    output_dir: Path,
    *,
    deadline_seconds: float = 10.0,
    failure_after_snapshot: bool = False,
) -> ExportResult:
    """Run one bounded export; failures never propagate into live writers."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = None
    try:
        with NamedTemporaryFile(prefix=".sqlite-snapshot-", suffix=".sqlite", dir=output_dir, delete=False) as tmp:
            snapshot = Path(tmp.name)
        create_consistent_snapshot(
            production_db,
            snapshot,
            deadline_seconds=deadline_seconds,
            production_path=production_db,
        )
        counts = export_snapshot_to_parquet(
            snapshot, output_dir, failure_after_snapshot=failure_after_snapshot, production_path=production_db
        )
        return ExportResult("HEALTHY", snapshot, counts)
    except SnapshotDeadlineExceeded as exc:
        return ExportResult("DEGRADED", snapshot, {}, type(exc).__name__)
    except Exception as exc:
        return ExportResult("FAILED", snapshot, {}, type(exc).__name__)
    finally:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)


def run_export_loop(
    production_db: Path,
    output_dir: Path,
    *,
    interval_seconds: float,
    deadline_seconds: float = 10.0,
    status_path: Path | None = None,
) -> None:
    """Run exports until signalled; shutdown never waits on an export."""
    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop:
        started = time.monotonic()
        result = export_once(production_db, output_dir, deadline_seconds=deadline_seconds)
        if status_path is not None:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            payload = result.as_dict() | {
                "LAST_EXPORT_SUCCESS": time.time() if result.status == "HEALTHY" else None,
                "LAST_EXPORT_FAILURE": time.time() if result.status != "HEALTHY" else None,
                "SNAPSHOT_DURATION_MS": round((time.monotonic() - started) * 1000, 2),
                "EXPORTER_SHUTDOWN_BOUNDED": True,
            }
            temp = status_path.with_name(f".{status_path.name}.tmp")
            temp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            os.replace(temp, status_path)
        stop = stop or interval_seconds <= 0
        if not stop:
            time.sleep(max(0.0, float(interval_seconds) - (time.monotonic() - started)))
