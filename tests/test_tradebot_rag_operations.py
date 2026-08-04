from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from pathlib import Path

import pytest

from core.tradebot_rag_operations import (
    BuildLockError,
    build_index_safely,
    build_lock_path,
    doctor_index,
    exclusive_build_lock,
    read_only_index_status,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_fixture(tmp_path: Path) -> Path:
    _write(tmp_path / "README.md", "# TradeBot\nFeed freshness evidence and risk controls.\n")
    _write(tmp_path / "docs" / "verdict.md", "# Verdict\nORB failed negative walk-forward validation.\n")
    index = tmp_path / ".runtime" / "rag.sqlite"
    report = build_index_safely(tmp_path, index)
    assert report.indexed_files == 2
    return index


def _failed_checks(report) -> set[str]:
    return {check.name for check in report.checks if not check.passed}


def test_safe_build_uses_and_cleans_lock(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)

    assert index.exists()
    assert not build_lock_path(index).exists()


def test_fresh_lock_blocks_nested_build(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# TradeBot\nEvidence\n")
    index = tmp_path / ".runtime" / "rag.sqlite"

    with exclusive_build_lock(index, stale_after_seconds=300):
        assert build_lock_path(index).exists()
        with pytest.raises(BuildLockError, match="rag_build_in_progress"):
            build_index_safely(tmp_path, index, stale_lock_seconds=300)

    assert not build_lock_path(index).exists()


def test_failed_lock_metadata_write_removes_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    index = tmp_path / ".runtime" / "rag.sqlite"
    lock = build_lock_path(index)

    def fail_write(_descriptor: int, _payload: bytes) -> int:
        raise OSError("simulated_lock_write_failure")

    monkeypatch.setattr("core.tradebot_rag_operations.os.write", fail_write)

    with pytest.raises(OSError, match="simulated_lock_write_failure"):
        with exclusive_build_lock(index):
            pytest.fail("lock acquisition should not complete")

    assert not lock.exists()


def test_stale_lock_is_recovered(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# TradeBot\nRecovered build evidence\n")
    index = tmp_path / ".runtime" / "rag.sqlite"
    lock = build_lock_path(index)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text('{"token":"old","pid":1}', encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))

    report = build_index_safely(tmp_path, index, stale_lock_seconds=1)

    assert report.indexed_files == 1
    assert not lock.exists()


def test_old_lock_owned_by_live_local_process_is_not_reclaimed(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# TradeBot\nEvidence\n")
    index = tmp_path / ".runtime" / "rag.sqlite"
    lock = build_lock_path(index)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "token": "live",
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "started_at_utc": "2000-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    old = time.time() - 120
    os.utime(lock, (old, old))

    with pytest.raises(BuildLockError, match="owner_alive=true"):
        build_index_safely(tmp_path, index, stale_lock_seconds=1)

    assert lock.exists()


def test_read_only_status_reports_inventory(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)

    status = read_only_index_status(index)

    assert status["exists"] is True
    assert status["readable"] is True
    assert status["document_count"] == 2
    assert status["chunk_count"] >= 2
    assert status["build_lock_present"] is False


def test_read_only_status_missing_index_does_not_create_it(tmp_path: Path) -> None:
    index = tmp_path / "missing.sqlite"

    status = read_only_index_status(index)

    assert status == {"exists": False, "index_path": str(index), "readable": False}
    assert not index.exists()


def test_read_only_status_does_not_repair_fts_row_loss(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)
    with sqlite3.connect(index) as connection:
        fts_enabled = connection.execute(
            "SELECT value FROM rag_meta WHERE key = 'fts_enabled'"
        ).fetchone()[0]
        if fts_enabled != "1":
            pytest.skip("SQLite FTS5 unavailable")
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
        connection.execute(
            "DELETE FROM rag_chunks_fts WHERE rowid = (SELECT MIN(id) FROM rag_chunks)"
        )
        connection.commit()

    status = read_only_index_status(index)

    with sqlite3.connect(index) as connection:
        remaining_fts = int(connection.execute("SELECT COUNT(*) FROM rag_chunks_fts").fetchone()[0])

    assert status["readable"] is True
    assert status["chunk_count"] == chunk_count
    assert remaining_fts == chunk_count - 1


def test_doctor_accepts_healthy_index(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)

    report = doctor_index(index)

    assert report.healthy is True
    assert not _failed_checks(report)
    assert {"sqlite_quick_check", "schema_version", "document_chunk_total"}.issubset(
        {check.name for check in report.checks}
    )


def test_doctor_reports_missing_index(tmp_path: Path) -> None:
    index = tmp_path / "missing.sqlite"

    report = doctor_index(index)

    assert report.healthy is False
    assert _failed_checks(report) == {"index_exists"}
    assert not index.exists()


def test_doctor_reports_active_build_lock(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)

    with exclusive_build_lock(index):
        report = doctor_index(index)

    assert report.healthy is False
    assert "build_lock_absent" in _failed_checks(report)


def test_doctor_detects_document_chunk_count_mismatch(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)
    with sqlite3.connect(index) as connection:
        connection.execute("UPDATE rag_documents SET chunk_count = chunk_count + 1 WHERE path = 'README.md'")
        connection.commit()

    report = doctor_index(index)

    assert report.healthy is False
    assert "document_chunk_total" in _failed_checks(report)
    assert "per_document_chunk_counts" in _failed_checks(report)


def test_doctor_detects_fts_row_loss_without_repairing_it(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)
    with sqlite3.connect(index) as connection:
        fts_enabled = connection.execute(
            "SELECT value FROM rag_meta WHERE key = 'fts_enabled'"
        ).fetchone()[0]
        if fts_enabled != "1":
            pytest.skip("SQLite FTS5 unavailable")
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
        connection.execute(
            "DELETE FROM rag_chunks_fts WHERE rowid = (SELECT MIN(id) FROM rag_chunks)"
        )
        connection.commit()

    report = doctor_index(index)

    with sqlite3.connect(index) as connection:
        remaining_fts = int(connection.execute("SELECT COUNT(*) FROM rag_chunks_fts").fetchone()[0])

    assert report.healthy is False
    failed = _failed_checks(report)
    assert "fts_row_count" in failed
    assert "fts_missing_rows" in failed
    assert remaining_fts == chunk_count - 1


def test_doctor_reports_non_database_file(tmp_path: Path) -> None:
    index = tmp_path / "broken.sqlite"
    index.write_text("not a sqlite database", encoding="utf-8")

    report = doctor_index(index)

    assert report.healthy is False
    assert "doctor_execution" in _failed_checks(report) or "sqlite_quick_check" in _failed_checks(report)
