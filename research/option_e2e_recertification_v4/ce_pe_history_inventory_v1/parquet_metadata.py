from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Iterable

TIME_COLUMNS = (
    "timestamp",
    "ts",
    "local_ts",
    "exchange_timestamp",
    "quote_timestamp",
    "quote_ts",
)
IDENTITY_COLUMNS = (
    "instrument_key",
    "instrument_token",
    "symbol",
    "trading_symbol",
    "tradingsymbol",
)
OPTION_TYPE_COLUMNS = ("option_type", "instrument_type", "type")
STRIKE_COLUMNS = ("strike", "strike_price")
EXPIRY_COLUMNS = ("expiry", "expiry_date")
BID_COLUMNS = ("bid", "bid_price", "best_bid")
ASK_COLUMNS = ("ask", "ask_price", "best_ask")
NORMALIZED_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "bid",
    "ask",
    "quote_timestamp",
    "underlying",
    "option_type",
    "strike",
    "expiry",
    "provider",
    "dataset_hash",
    "bar_interval",
}
OPTION_RE = re.compile(r"(?:^|[^A-Z0-9])(CE|PE)(?:[^A-Z0-9]|$)", re.IGNORECASE)


def option_name_hint(value: str) -> bool:
    name = PurePosixPath(value).name.replace("_", " ").replace("-", " ")
    return bool(OPTION_RE.search(name))


def _first(columns: set[str], aliases: Iterable[str]) -> str | None:
    return next((name for name in aliases if name in columns), None)


def classify_parquet(columns: Iterable[str], *, path_hint: str) -> str | None:
    values = set(map(str, columns))
    if NORMALIZED_COLUMNS.issubset(values):
        return "NORMALIZED_OPTION_REPLAY_DATASET"
    has_time = _first(values, TIME_COLUMNS) is not None
    has_identity = _first(values, IDENTITY_COLUMNS) is not None
    has_bid = _first(values, BID_COLUMNS) is not None
    has_ask = _first(values, ASK_COLUMNS) is not None
    has_contract = all(
        _first(values, aliases) is not None
        for aliases in (OPTION_TYPE_COLUMNS, STRIKE_COLUMNS, EXPIRY_COLUMNS)
    )
    if has_time and has_identity and has_bid and has_ask:
        return "RAW_OPTION_TICK_DATASET"
    if has_time and has_contract:
        return "OPTION_CONTRACT_DATASET"
    if (
        has_time
        and {"open", "high", "low", "close"}.issubset(values)
        and option_name_hint(path_hint)
    ):
        return "OPTION_CONTRACT_DATASET"
    return None


def _to_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        number = float(value)
        magnitude = abs(number)
        divisor = (
            1e9
            if magnitude >= 1e17
            else 1e6
            if magnitude >= 1e14
            else 1e3
            if magnitude >= 1e11
            else 1.0
        )
        try:
            return datetime.fromtimestamp(number / divisor, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def inspect_parquet_footer(source: Any, *, path_hint: str = "") -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pyarrow_required_for_metadata_first_inventory") from exc
    parquet = pq.ParquetFile(source)
    metadata = parquet.metadata
    columns = [str(name) for name in parquet.schema_arrow.names]
    timestamp_column = _first(set(columns), TIME_COLUMNS)
    minimums: list[str] = []
    maximums: list[str] = []
    if timestamp_column:
        for group_index in range(metadata.num_row_groups):
            group = metadata.row_group(group_index)
            for column_index in range(group.num_columns):
                column = group.column(column_index)
                if column.path_in_schema != timestamp_column:
                    continue
                stats = column.statistics
                if stats is None or not stats.has_min_max:
                    continue
                minimum = _to_date(stats.min)
                maximum = _to_date(stats.max)
                if minimum:
                    minimums.append(minimum)
                if maximum:
                    maximums.append(maximum)
    return {
        "schema_columns": columns,
        "candidate_class": classify_parquet(columns, path_hint=path_hint),
        "row_count": int(metadata.num_rows),
        "row_group_count": int(metadata.num_row_groups),
        "created_by": metadata.created_by,
        "timestamp_column": timestamp_column,
        "footer_date_min": min(minimums) if minimums else None,
        "footer_date_max": max(maximums) if maximums else None,
    }
