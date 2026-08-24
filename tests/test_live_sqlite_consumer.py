import sqlite3

import pytest

from core.live_sqlite_consumer import open_canonical_live_sqlite


def test_canonical_sqlite_consumer_is_read_only(tmp_path):
    path = tmp_path / "live.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE ticks (value INTEGER)")
        connection.execute("INSERT INTO ticks VALUES (7)")
    with open_canonical_live_sqlite(path) as connection:
        assert connection.execute("SELECT value FROM ticks").fetchone()[0] == 7
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            connection.execute("INSERT INTO ticks VALUES (8)")


def test_missing_canonical_sqlite_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="canonical_live_sqlite_missing"):
        with open_canonical_live_sqlite(tmp_path / "missing.sqlite"):
            pass
