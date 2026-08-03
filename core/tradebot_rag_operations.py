"""Operational hardening for the local TradeBot evidence RAG index.

This module does not change retrieval, ranking, or answer behavior. It adds an
atomic build lock for supported entrypoints and a read-only integrity doctor for
production operations.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from core.tradebot_rag import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_INCLUDE_PATHS,
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_OVERLAP_LINES,
    SCHEMA_VERSION,
    IndexBuildReport,
    build_index,
)

DEFAULT_STALE_LOCK_SECONDS = 30 * 60
LOCK_SUFFIX = ".build.lock"


class BuildLockError(RuntimeError):
    """Raised when another supported build owns the index lock."""


@dataclass(frozen=True)
class IndexCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class IndexDoctorReport:
    index_path: str
    healthy: bool
    checks: tuple[IndexCheck, ...]
    checked_at_utc: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["checks"] = [asdict(check) for check in self.checks]
        return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_lock_path(index_path: Path | str) -> Path:
    index = Path(index_path).expanduser()
    return Path(f"{index}{LOCK_SUFFIX}")


def _lock_age_seconds(lock_path: Path) -> float:
    try:
        return max(0.0, time.time() - lock_path.stat().st_mtime)
    except OSError:
        return 0.0


def _read_lock_description(lock_path: Path) -> str:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unreadable_lock"
    owner = payload.get("hostname", "unknown-host")
    pid = payload.get("pid", "unknown-pid")
    started = payload.get("started_at_utc", "unknown-time")
    return f"owner={owner} pid={pid} started_at_utc={started}"


@contextmanager
def exclusive_build_lock(
    index_path: Path | str,
    *,
    stale_after_seconds: int = DEFAULT_STALE_LOCK_SECONDS,
) -> Iterator[Path]:
    """Acquire an atomic lock for one supported index build.

    A fresh existing lock fails closed. A stale lock is removed and acquisition is
    retried once. Cleanup removes the lock only when its unique token still matches,
    preventing one process from deleting a replacement lock.
    """

    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds_must_be_positive")

    lock_path = build_lock_path(index_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    payload = {
        "token": token,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "started_at_utc": _utc_now(),
        "index_path": str(Path(index_path).expanduser()),
    }
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")

    acquired = False
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            age = _lock_age_seconds(lock_path)
            if attempt == 0 and age >= stale_after_seconds:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as unlink_error:
                    raise BuildLockError(
                        f"rag_build_lock_stale_but_not_removable path={lock_path} age_seconds={age:.1f}"
                    ) from unlink_error
                continue
            description = _read_lock_description(lock_path)
            raise BuildLockError(
                f"rag_build_in_progress path={lock_path} age_seconds={age:.1f} {description}"
            ) from exc
        else:
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            acquired = True
            break

    if not acquired:
        raise BuildLockError(f"rag_build_lock_not_acquired path={lock_path}")

    try:
        yield lock_path
    finally:
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
            current = {}
        if current.get("token") == token:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def build_index_safely(
    repo_root: Path | str,
    index_path: Path | str,
    *,
    include_paths: Sequence[str] = DEFAULT_INCLUDE_PATHS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
    stale_lock_seconds: int = DEFAULT_STALE_LOCK_SECONDS,
) -> IndexBuildReport:
    """Run the existing incremental builder under the operational build lock."""

    with exclusive_build_lock(index_path, stale_after_seconds=stale_lock_seconds):
        return build_index(
            repo_root,
            index_path,
            include_paths=include_paths,
            max_file_bytes=max_file_bytes,
            max_chunk_chars=max_chunk_chars,
            overlap_lines=overlap_lines,
        )


def _check(name: str, passed: bool, detail: str) -> IndexCheck:
    return IndexCheck(name=name, passed=bool(passed), detail=detail)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }


def doctor_index(index_path: Path | str) -> IndexDoctorReport:
    """Inspect index consistency without creating, repairing, or mutating it."""

    path = Path(index_path).expanduser()
    checks: list[IndexCheck] = []
    checked_at = _utc_now()
    if not path.exists() or not path.is_file():
        checks.append(_check("index_exists", False, f"missing:{path}"))
        return IndexDoctorReport(str(path), False, tuple(checks), checked_at)

    checks.append(_check("index_exists", True, str(path)))
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        checks.append(_check("sqlite_open_read_only", False, f"{type(exc).__name__}:{exc}"))
        return IndexDoctorReport(str(path), False, tuple(checks), checked_at)

    try:
        quick_rows = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
        quick_ok = quick_rows == ["ok"]
        checks.append(_check("sqlite_quick_check", quick_ok, "; ".join(quick_rows[:10])))

        tables = _table_names(connection)
        required = {"rag_meta", "rag_documents", "rag_chunks"}
        missing = sorted(required - tables)
        checks.append(
            _check(
                "required_tables",
                not missing,
                "present" if not missing else "missing=" + ",".join(missing),
            )
        )
        if missing:
            return IndexDoctorReport(str(path), False, tuple(checks), checked_at)

        metadata = {
            str(row["key"]): str(row["value"])
            for row in connection.execute("SELECT key, value FROM rag_meta")
        }
        schema_value = metadata.get("schema_version")
        checks.append(
            _check(
                "schema_version",
                schema_value == str(SCHEMA_VERSION),
                f"expected={SCHEMA_VERSION} actual={schema_value}",
            )
        )

        document_count = int(connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0])
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
        checks.append(_check("nonempty_documents", document_count > 0, f"count={document_count}"))
        checks.append(_check("nonempty_chunks", chunk_count > 0, f"count={chunk_count}"))

        declared_chunks = int(
            connection.execute("SELECT COALESCE(SUM(chunk_count), 0) FROM rag_documents").fetchone()[0]
        )
        checks.append(
            _check(
                "document_chunk_total",
                declared_chunks == chunk_count,
                f"declared={declared_chunks} actual={chunk_count}",
            )
        )

        mismatch_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT d.path, d.chunk_count, COUNT(c.id) AS actual_count "
                "FROM rag_documents d LEFT JOIN rag_chunks c ON c.path = d.path "
                "GROUP BY d.path HAVING d.chunk_count != actual_count"
                ")"
            ).fetchone()[0]
        )
        checks.append(
            _check(
                "per_document_chunk_counts",
                mismatch_count == 0,
                f"mismatched_documents={mismatch_count}",
            )
        )

        orphan_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM rag_chunks c "
                "LEFT JOIN rag_documents d ON d.path = c.path WHERE d.path IS NULL"
            ).fetchone()[0]
        )
        checks.append(_check("orphan_chunks", orphan_count == 0, f"count={orphan_count}"))

        meta_chunk_count = metadata.get("chunk_count")
        checks.append(
            _check(
                "metadata_chunk_count",
                meta_chunk_count == str(chunk_count),
                f"metadata={meta_chunk_count} actual={chunk_count}",
            )
        )

        fts_enabled = metadata.get("fts_enabled") == "1"
        if fts_enabled:
            fts_present = "rag_chunks_fts" in tables
            checks.append(_check("fts_table_present", fts_present, f"present={fts_present}"))
            if fts_present:
                fts_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks_fts").fetchone()[0])
                missing_fts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM rag_chunks c "
                        "LEFT JOIN rag_chunks_fts f ON f.rowid = c.id WHERE f.rowid IS NULL"
                    ).fetchone()[0]
                )
                extra_fts = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM rag_chunks_fts f "
                        "LEFT JOIN rag_chunks c ON c.id = f.rowid WHERE c.id IS NULL"
                    ).fetchone()[0]
                )
                checks.append(
                    _check("fts_row_count", fts_count == chunk_count, f"fts={fts_count} chunks={chunk_count}")
                )
                checks.append(_check("fts_missing_rows", missing_fts == 0, f"count={missing_fts}"))
                checks.append(_check("fts_extra_rows", extra_fts == 0, f"count={extra_fts}"))
        else:
            checks.append(_check("fts_optional", True, "fts_enabled=0; deterministic fallback expected"))

        foreign_key_rows = list(connection.execute("PRAGMA foreign_key_check"))
        checks.append(
            _check(
                "foreign_key_check",
                not foreign_key_rows,
                f"violations={len(foreign_key_rows)}",
            )
        )
    except (sqlite3.Error, ValueError, TypeError) as exc:
        checks.append(_check("doctor_execution", False, f"{type(exc).__name__}:{exc}"))
    finally:
        connection.close()

    healthy = bool(checks) and all(check.passed for check in checks)
    return IndexDoctorReport(str(path), healthy, tuple(checks), checked_at)


__all__ = [
    "BuildLockError",
    "DEFAULT_STALE_LOCK_SECONDS",
    "IndexCheck",
    "IndexDoctorReport",
    "build_index_safely",
    "build_lock_path",
    "doctor_index",
    "exclusive_build_lock",
]
