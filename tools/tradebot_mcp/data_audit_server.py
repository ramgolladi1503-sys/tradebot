from __future__ import annotations

from typing import Sequence

from mcp.server.fastmcp import FastMCP

from tools.tradebot_mcp.core import DataAuditService, Settings

mcp = FastMCP(
    "tradebot-data-audit",
    instructions=(
        "Read-only, bounded market-data inspection. Tools reject paths outside approved "
        "roots, secret-bearing paths, unsupported formats and future-directed joins."
    ),
    json_response=True,
)
service = DataAuditService(Settings.from_env())


@mcp.tool()
def list_corpora(max_files: int | None = None) -> dict:
    """List approved local market-data files without reading their full contents."""
    return service.list_corpora(max_files)


@mcp.tool()
def inspect_schema(path: str) -> dict:
    """Inspect Parquet metadata or a bounded CSV schema sample."""
    return service.inspect_schema(path)


@mcp.tool()
def hash_source(path: str) -> dict:
    """Stream-hash one approved source file subject to a configured size limit."""
    return service.hash_source(path)


@mcp.tool()
def count_rows(path: str) -> dict:
    """Count rows using Parquet metadata or a streaming text count."""
    return service.count_rows(path)


@mcp.tool()
def count_sessions(path: str, timestamp_column: str, timezone: str = "Asia/Kolkata") -> dict:
    """Count date sessions from one causal timestamp column."""
    return service.count_sessions(path, timestamp_column, timezone)


@mcp.tool()
def audit_duplicates(path: str, timestamp_column: str) -> dict:
    """Count duplicate timestamps without changing the source."""
    return service.audit_duplicates(path, timestamp_column)


@mcp.tool()
def audit_missing_intervals(path: str, timestamp_column: str, expected_seconds: float) -> dict:
    """Report timestamp gaps larger than the expected interval."""
    return service.audit_missing_intervals(path, timestamp_column, expected_seconds)


@mcp.tool()
def audit_timestamp_order(path: str, timestamp_column: str) -> dict:
    """Verify that source timestamps are monotonically non-decreasing."""
    return service.audit_timestamp_order(path, timestamp_column)


@mcp.tool()
def sample_session(
    path: str,
    timestamp_column: str,
    session_date: str,
    timezone: str = "Asia/Kolkata",
    columns: Sequence[str] | None = None,
    limit: int = 50,
) -> dict:
    """Return a bounded sample from one session and selected columns."""
    return service.sample_session(path, timestamp_column, session_date, timezone, columns, limit)


@mcp.tool()
def audit_join_causality(
    left_path: str,
    right_path: str,
    left_timestamp: str,
    right_timestamp: str,
    tolerance_seconds: float,
    max_rows: int = 500_000,
) -> dict:
    """Test a backward as-of join and prove no future source row is matched."""
    return service.audit_join_causality(
        left_path,
        right_path,
        left_timestamp,
        right_timestamp,
        tolerance_seconds,
        max_rows,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
