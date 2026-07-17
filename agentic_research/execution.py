from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from agentic_research.contracts import ToolResult
from agentic_research.storage import ArtifactStore


class TraceRecorder:
    def __init__(self, store: ArtifactStore):
        self.store = store

    def record(self, research_id: str, event: str, **payload: Any) -> None:
        self.store.append_jsonl(
            research_id,
            "trace.jsonl",
            {"timestamp_epoch": time.time(), "event": event, **payload},
        )


class IdempotentToolExecutor:
    """SQLite-backed exactly-once result reuse for deterministic read-only tools."""

    def __init__(self, db_path: Path, trace: TraceRecorder):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.trace = trace
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_runs (
                    idempotency_key TEXT PRIMARY KEY,
                    research_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    args_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    updated_epoch REAL NOT NULL
                )
                """
            )

    def execute(self, *, research_id: str, tool_name: str, arguments: dict[str, Any], operation: Callable[[], ToolResult]) -> ToolResult:
        args_json = json.dumps(arguments, sort_keys=True, default=str)
        args_hash = hashlib.sha256(args_json.encode()).hexdigest()
        key = hashlib.sha256(f"{research_id}:{tool_name}:{args_hash}".encode()).hexdigest()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT status, attempts, result_json FROM tool_runs WHERE idempotency_key = ?", (key,)).fetchone()
            if row and row[0] == "COMPLETED" and row[2]:
                self.trace.record(research_id, "tool_cache_hit", tool=tool_name, idempotency_key=key)
                return ToolResult.model_validate_json(row[2])
            attempts = int(row[1]) + 1 if row else 1
            conn.execute(
                """
                INSERT INTO tool_runs(idempotency_key, research_id, tool_name, args_hash, status, attempts, updated_epoch)
                VALUES (?, ?, ?, ?, 'RUNNING', ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET status='RUNNING', attempts=excluded.attempts, error=NULL, updated_epoch=excluded.updated_epoch
                """,
                (key, research_id, tool_name, args_hash, attempts, time.time()),
            )
        self.trace.record(research_id, "tool_started", tool=tool_name, attempt=attempts, idempotency_key=key)
        try:
            result = operation()
            if not isinstance(result, ToolResult):
                raise TypeError("tool_operation_must_return_tool_result")
            encoded = result.model_dump_json()
            with self._lock, self._connect() as conn:
                conn.execute("UPDATE tool_runs SET status='COMPLETED', result_json=?, error=NULL, updated_epoch=? WHERE idempotency_key=?", (encoded, time.time(), key))
            self.trace.record(research_id, "tool_completed", tool=tool_name, result_hash=result.result_hash, idempotency_key=key)
            return result
        except Exception as exc:
            with self._lock, self._connect() as conn:
                conn.execute("UPDATE tool_runs SET status='FAILED', error=?, updated_epoch=? WHERE idempotency_key=?", (str(exc), time.time(), key))
            self.trace.record(research_id, "tool_failed", tool=tool_name, error=str(exc), idempotency_key=key)
            raise

    def attempts(self, research_id: str, tool_name: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(attempts), 0) FROM tool_runs WHERE research_id=? AND tool_name=?", (research_id, tool_name)).fetchone()
        return int(row[0]) if row else 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)
