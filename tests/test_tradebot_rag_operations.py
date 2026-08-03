from __future__ import annotations

import os
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


def test_doctor_accepts_healthy_index(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)

    report = doctor_index(index)

    assert report.healthy is True
    assert not _failed_checks(report)
    assert {"sqlite_quick_check", "schema_version", "document_chunk_total"}.issubset(
        {check.name for check in report.checks}
    )


def test_doctor_reports_missing_index(tmp_path: Path) -> None:
    report = doctor_index(tmp_path / "missing.sqlite")

    assert report.healthy is False
    assert _failed_checks(report) == {"index_exists"}


def test_doctor_detects_document_chunk_count_mismatch(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)
    with sqlite3.connect(index) as connection:
        connection.execute("UPDATE rag_documents SET chunk_count = chunk_count + 1 WHERE path = 'README.md'")
        connection.commit()

    report = doctor_index(index)

    assert report.healthy is False
    assert "document_chunk_total" in _failed_checks(report)
    assert "per_document_chunk_counts" in _failed_checks(report)


def test_doctor_detects_fts_row_loss(tmp_path: Path) -> None:
    index = _build_fixture(tmp_path)
    with sqlite3.connect(index) as connection:
        fts_enabled = connection.execute(
            "SELECT value FROM rag_meta WHERE key = 'fts_enabled'"
        ).fetchone()[0]
        if fts_enabled != "1":
            pytest.skip("SQLite FTS5 unavailable")
        connection.execute(
            "DELETE FROM rag_chunks_fts WHERE rowid = (SELECT MIN(id) FROM rag_chunks)"
        )
        connection.commit()

    report = doctor_index(index)

    assert report.healthy is False
    failed = _failed_checks(report)
    assert "fts_row_count" in failed
    assert "fts_missing_rows" in failed


def test_doctor_reports_non_database_file(tmp_path: Path) -> None:
    index = tmp_path / "broken.sqlite"
    index.write_text("not a sqlite database", encoding="utf-8")

    report = doctor_index(index)

    assert report.healthy is False
    assert "doctor_execution" in _failed_checks(report) or "sqlite_quick_check" in _failed_checks(report)
