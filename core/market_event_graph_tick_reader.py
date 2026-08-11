"""Read-only batch tick reader for completed constituent-minute reconstruction.

The reader never creates or migrates the tick database. It opens the canonical
SQLite database with ``mode=ro`` and returns the last observed tick inside each
requested completed one-minute interval.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from config import config as cfg

MINUTE_SECONDS = 60
_SQLITE_BIND_LIMIT = 900


def read_last_ticks_by_minute(
    tokens: Iterable[int],
    minute_end_epochs: Iterable[float],
    *,
    db_path: str | Path | None = None,
) -> dict[int, dict[int, dict[str, Any]]]:
    """Return ``{minute_end: {token: latest_tick_in_minute}}``.

    Minute membership is causal and right-closed: ``(end - 60, end]``. Missing
    tokens/minutes are omitted rather than forward-filled.
    """

    normalized_tokens = _positive_unique_ints(tokens)
    normalized_ends = _strict_minute_ends(minute_end_epochs)
    if not normalized_tokens or not normalized_ends:
        return {}

    source = Path(db_path or getattr(cfg, "TRADE_DB_PATH", "")).expanduser().resolve()
    if not source.is_file():
        return {}

    start_epoch = float(normalized_ends[0] - MINUTE_SECONDS)
    end_epoch = float(normalized_ends[-1])
    requested = set(normalized_ends)
    result: dict[int, dict[int, dict[str, Any]]] = {end: {} for end in normalized_ends}

    try:
        connection = sqlite3.connect(
            f"file:{source.as_posix()}?mode=ro",
            uri=True,
            timeout=5.0,
        )
    except sqlite3.Error:
        return {}

    try:
        columns = _tick_columns(connection)
        required = {"instrument_token", "timestamp_epoch", "last_price"}
        if not required.issubset(columns):
            return {}

        for offset in range(0, len(normalized_tokens), _SQLITE_BIND_LIMIT):
            chunk = normalized_tokens[offset : offset + _SQLITE_BIND_LIMIT]
            placeholders = ",".join("?" for _ in chunk)
            sql = (
                "SELECT rowid, instrument_token, last_price, timestamp_epoch, "
                + ("volume" if "volume" in columns else "NULL")
                + " AS volume, "
                + ("oi" if "oi" in columns else "NULL")
                + " AS oi FROM ticks "
                + f"WHERE instrument_token IN ({placeholders}) "
                + "AND timestamp_epoch > ? AND timestamp_epoch <= ? "
                + "ORDER BY instrument_token ASC, timestamp_epoch ASC, rowid ASC"
            )
            params = tuple(chunk) + (start_epoch, end_epoch)
            try:
                rows = connection.execute(sql, params)
            except sqlite3.Error:
                return {}
            for rowid, token, price, timestamp_epoch, volume, oi in rows:
                parsed = _parse_tick(
                    rowid=rowid,
                    token=token,
                    price=price,
                    timestamp_epoch=timestamp_epoch,
                    volume=volume,
                    oi=oi,
                )
                if parsed is None:
                    continue
                minute_end = _right_closed_minute_end(parsed["ts_epoch"])
                if minute_end not in requested:
                    continue
                previous = result[minute_end].get(parsed["instrument_token"])
                if previous is None or (
                    parsed["ts_epoch"], parsed["rowid"]
                ) >= (previous["ts_epoch"], previous["rowid"]):
                    result[minute_end][parsed["instrument_token"]] = parsed
    finally:
        connection.close()

    return result


def _tick_columns(connection: sqlite3.Connection) -> set[str]:
    try:
        return {str(row[1]) for row in connection.execute("PRAGMA table_info(ticks)")}
    except sqlite3.Error:
        return set()


def _positive_unique_ints(values: Iterable[int]) -> list[int]:
    output: set[int] = set()
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            output.add(parsed)
    return sorted(output)


def _strict_minute_ends(values: Iterable[float]) -> list[int]:
    output: set[int] = set()
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(parsed) or parsed <= 0.0:
            continue
        rounded = int(round(parsed))
        if rounded % MINUTE_SECONDS != 0:
            continue
        output.add(rounded)
    return sorted(output)


def _right_closed_minute_end(timestamp_epoch: float) -> int:
    quotient = float(timestamp_epoch) / float(MINUTE_SECONDS)
    return int(math.ceil(quotient - 1e-12) * MINUTE_SECONDS)


def _parse_tick(
    *,
    rowid: Any,
    token: Any,
    price: Any,
    timestamp_epoch: Any,
    volume: Any,
    oi: Any,
) -> dict[str, Any] | None:
    try:
        parsed_rowid = int(rowid)
        parsed_token = int(token)
        parsed_price = float(price)
        parsed_timestamp = float(timestamp_epoch)
    except (TypeError, ValueError):
        return None
    if (
        parsed_rowid <= 0
        or parsed_token <= 0
        or parsed_price <= 0.0
        or not math.isfinite(parsed_price)
        or not math.isfinite(parsed_timestamp)
    ):
        return None

    return {
        "rowid": parsed_rowid,
        "instrument_token": parsed_token,
        "ltp": parsed_price,
        "ts_epoch": parsed_timestamp,
        "volume": _optional_finite(volume),
        "oi": _optional_finite(oi),
        "source": "sqlite_read_only",
    }


def _optional_finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


__all__ = ["MINUTE_SECONDS", "read_last_ticks_by_minute"]
