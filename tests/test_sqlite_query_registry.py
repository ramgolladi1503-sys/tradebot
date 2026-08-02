import sqlite3

import pytest

from core.feed_self_test import _query_max_epoch
from core.sqlite_query_registry import approved_timestamp_tables, max_timestamp_query


def test_timestamp_query_registry_returns_only_literal_approved_queries():
    assert approved_timestamp_tables() == ("depth_snapshots", "feed_runtime", "ticks")
    assert max_timestamp_query("ticks") == "SELECT MAX(timestamp_epoch) FROM ticks"
    assert max_timestamp_query("depth_snapshots") == (
        "SELECT MAX(timestamp_epoch) FROM depth_snapshots"
    )


@pytest.mark.parametrize(
    "value",
    [
        "ticks; DROP TABLE ticks;--",
        "ticks WHERE 1=1",
        'ticks"',
        "",
        "unknown_table",
    ],
)
def test_timestamp_query_registry_rejects_unknown_or_malicious_identifiers(value):
    with pytest.raises(ValueError, match="unsupported_timestamp_table"):
        max_timestamp_query(value)


def test_feed_self_test_max_epoch_executes_registry_query_and_fails_closed():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ticks (timestamp_epoch REAL)")
    conn.executemany("INSERT INTO ticks(timestamp_epoch) VALUES (?)", [(1.0,), (9.0,), (3.0,)])

    assert _query_max_epoch(conn, "ticks") == 9.0
    assert _query_max_epoch(conn, "ticks; DROP TABLE ticks;--") is None
    assert conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] == 3
