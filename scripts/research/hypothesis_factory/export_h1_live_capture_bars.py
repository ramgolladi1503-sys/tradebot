#!/usr/bin/env python3
"""Export sealed NIFTY price captures to deterministic H1 5-minute OHLC.

This module is deliberately read-only.  It accepts a sealed SQLite tick store
or price-trace JSONL, never connects to a broker, and fails closed when the
opening-window coverage contract is not met.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

MARKET_TZ = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
EXPECTED_SYMBOL = "NIFTY 50"
DEFAULT_TOKEN = 256265
BAR_MINUTES = 5
OPENING_START = "09:15"
OPENING_END = "11:30"
MINIMUM_SEQUENTIAL_BARS = 7
OUTPUT_COLUMNS = ["datetime", "open", "high", "low", "close"]
EXPORTER_VERSION = "H1_LIVE_CAPTURE_EXPORTER_V1"


@dataclass(frozen=True)
class Event:
    timestamp: datetime
    price: float
    sequence: int
    instrument_token: int
    source: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(MARKET_TZ)


def valid_price(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def _event_sort_key(event: Event) -> tuple[datetime, int]:
    return event.timestamp, event.sequence


def read_sqlite_events(path: Path, instrument_token: int) -> tuple[list[Event], dict[str, int]]:
    """Read ticks through SQLite's immutable read-only URI; never writes."""
    uri = f"file:{path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    invalid = 0
    events: list[Event] = []
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ticks)")}
        required = {"instrument_token", "last_price", "timestamp_iso"}
        if not required.issubset(columns):
            raise ValueError(f"ticks table missing columns: {sorted(required - columns)}")
        rows = connection.execute(
            "SELECT rowid, instrument_token, last_price, timestamp_iso "
            "FROM ticks WHERE instrument_token = ? ORDER BY timestamp_iso ASC, rowid ASC",
            (instrument_token,),
        )
        for rowid, token, price, timestamp in rows:
            try:
                parsed = parse_timestamp(timestamp)
                if not valid_price(price):
                    raise ValueError("invalid price")
                events.append(Event(parsed, float(price), int(rowid), int(token), "sqlite"))
            except (TypeError, ValueError, OverflowError):
                invalid += 1
    finally:
        connection.close()
    return events, {"invalid_event_count": invalid}


def read_price_trace_events(path: Path, instrument_token: int = DEFAULT_TOKEN) -> tuple[list[Event], dict[str, int]]:
    events: list[Event] = []
    invalid = 0
    with path.open() as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                item = json.loads(line)
                if item.get("symbol") != "NIFTY":
                    continue
                price = item.get("price")
                parsed = parse_timestamp(item["ts_ist"])
                if not valid_price(price):
                    raise ValueError("invalid price")
                events.append(Event(parsed, float(price), line_number, instrument_token, "price_trace"))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OverflowError):
                invalid += 1
    return events, {"invalid_event_count": invalid}


def opening_starts(observation_date: str) -> list[datetime]:
    start = datetime.fromisoformat(f"{observation_date}T09:15:00").replace(tzinfo=MARKET_TZ)
    return [start + timedelta(minutes=BAR_MINUTES * index) for index in range(27)]


def aggregate(events: Iterable[Event], observation_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered = sorted(events, key=_event_sort_key)
    bars: dict[datetime, list[Event]] = {}
    for event in ordered:
        if event.timestamp.date().isoformat() != observation_date:
            continue
        start = event.timestamp.replace(minute=(event.timestamp.minute // 5) * 5, second=0, microsecond=0)
        bars.setdefault(start, []).append(event)

    starts = opening_starts(observation_date)
    rows = []
    for start in starts:
        values = bars.get(start, [])
        if not values:
            continue
        values.sort(key=_event_sort_key)
        prices = [event.price for event in values]
        rows.append({
            "datetime": start.strftime("%Y-%m-%d %H:%M:%S%z"),
            "open": prices[0], "high": max(prices), "low": min(prices), "close": prices[-1],
        })
    observed = {datetime.fromisoformat(row["datetime"]) for row in rows}
    missing = [start.strftime("%Y-%m-%d %H:%M:%S%z") for start in starts if start not in observed]
    report = {
        "expected_bar_count": len(starts),
        "observed_complete_bar_count": len(rows),
        "missing_bar_starts": missing,
        "first_bar": rows[0]["datetime"] if rows else None,
        "last_bar": rows[-1]["datetime"] if rows else None,
        "coverage_complete": not missing,
        "minimum_sequential_bars": MINIMUM_SEQUENTIAL_BARS,
        "warmup_satisfied": len(rows) >= MINIMUM_SEQUENTIAL_BARS and not missing,
    }
    return rows, report


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export(input_path: Path, output_csv: Path, manifest_path: Path, observation_date: str,
           source_format: str, instrument_token: int = DEFAULT_TOKEN, allow_incomplete: bool = False) -> dict[str, Any]:
    source_hash = sha256_file(input_path)
    if source_format == "sqlite":
        events, quality = read_sqlite_events(input_path, instrument_token)
    elif source_format == "price-trace":
        events, quality = read_price_trace_events(input_path, instrument_token)
    else:
        raise ValueError("source_format must be sqlite or price-trace")
    rows, coverage = aggregate(events, observation_date)
    if not coverage["coverage_complete"] and not allow_incomplete:
        raise ValueError("H1_REPLAY_INPUT_INVALID: opening-window coverage is incomplete")
    write_csv(output_csv, rows)
    manifest = {
        "exporter_version": EXPORTER_VERSION, "source_path": str(input_path), "source_sha256": source_hash,
        "source_size": input_path.stat().st_size, "source_mtime": input_path.stat().st_mtime,
        "source_format": source_format, "instrument_identity": EXPECTED_SYMBOL, "instrument_token": instrument_token,
        "timezone": "Asia/Kolkata", "bar_interval": "5m", "session_filter": "09:15-11:30 IST",
        "event_count": len(events) + quality["invalid_event_count"], "valid_event_count": len(events),
        "invalid_event_count": quality["invalid_event_count"],
        "first_event_timestamp": events[0].timestamp.isoformat() if events else None,
        "last_event_timestamp": events[-1].timestamp.isoformat() if events else None,
        **coverage,
        "complete_bar_count": coverage["observed_complete_bar_count"],
        "missing_bar_count": len(coverage["missing_bar_starts"]),
        "deterministic_duplicate_policy": "event_timestamp_asc_then_rowid_or_jsonl_line_asc",
        "missing_bar_policy": "MISSING; no forward-fill, backfill, interpolation, or substitution",
        "opening_window_coverage_gate": "09:15-11:30 IST requires all 27 five-minute starts",
        "h1_replay_input_valid": coverage["coverage_complete"] and coverage["warmup_satisfied"],
        "output_csv_sha256": sha256_file(output_csv), "PR814_HEAD": "15752004bfcb0a80fffbc0939a11b495d4ac066b",
        "source_db_mutated": False, "orders_created": 0, "broker_writes_created": 0,
        "broker_write_authority": False, "order_authority": False, "paper_authorized": False, "live_authorized": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only NIFTY capture to H1 OHLC exporter")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sqlite")
    group.add_argument("--price-trace")
    parser.add_argument("--observation-date", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--instrument-token", type=int, default=DEFAULT_TOKEN)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    source = Path(args.sqlite or args.price_trace)
    fmt = "sqlite" if args.sqlite else "price-trace"
    manifest = export(source, Path(args.output_csv), Path(args.manifest), args.observation_date, fmt, args.instrument_token, args.allow_incomplete)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
