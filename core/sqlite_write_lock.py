"""Process-local serialization for SQLite transaction boundaries.

The live observer has several persistence workers targeting the same SQLite
database. SQLite WAL permits concurrent readers, but concurrent writers still
contend on the single writer lock. This boundary serializes repository-owned
connection transactions inside one process; SQLite's busy timeout remains the
cross-process protection.
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator


_SQLITE_TRANSACTION_LOCK = RLock()


@contextmanager
def sqlite_transaction_lock() -> Iterator[None]:
    """Serialize one repository-owned SQLite transaction in this process."""

    with _SQLITE_TRANSACTION_LOCK:
        yield


__all__ = ["sqlite_transaction_lock"]
