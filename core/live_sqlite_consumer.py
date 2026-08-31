"""Shared read-only connection boundary for canonical live SQLite consumers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


@contextmanager
def open_canonical_live_sqlite(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open an existing canonical store in SQLite read-only/query-only mode."""
    database = Path(path)
    if not database.is_file():
        raise FileNotFoundError(f"canonical_live_sqlite_missing:{database}")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5.0)
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise RuntimeError("canonical_live_sqlite_query_only_not_enabled")
        connection.row_factory = sqlite3.Row
        yield connection
    finally:
        connection.close()
