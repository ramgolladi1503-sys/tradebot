"""Literal SQLite query registry for approved dynamic identifier choices.

SQLite parameters protect values, not table or column identifiers. Runtime code
must therefore select complete SQL statements from this registry instead of
interpolating caller-provided identifiers.
"""

from __future__ import annotations

from typing import Final


_MAX_TIMESTAMP_QUERY_BY_TABLE: Final[dict[str, str]] = {
    "ticks": "SELECT MAX(timestamp_epoch) FROM ticks",
    "depth_snapshots": "SELECT MAX(timestamp_epoch) FROM depth_snapshots",
    "feed_runtime": "SELECT MAX(timestamp_epoch) FROM feed_runtime",
}


def max_timestamp_query(table: str) -> str:
    normalized = str(table or "").strip()
    try:
        return _MAX_TIMESTAMP_QUERY_BY_TABLE[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported_timestamp_table:{normalized or '<empty>'}") from exc


def approved_timestamp_tables() -> tuple[str, ...]:
    return tuple(sorted(_MAX_TIMESTAMP_QUERY_BY_TABLE))
