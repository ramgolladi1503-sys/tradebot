import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.research.hypothesis_factory.export_h1_live_capture_bars import (
    Event, aggregate, export, read_sqlite_events,
)


def event(ts, price, sequence=1):
    from scripts.research.hypothesis_factory.export_h1_live_capture_bars import parse_timestamp
    return Event(parse_timestamp(ts), price, sequence, 256265, "fixture")


def test_aggregates_five_minute_ohlc_and_boundary():
    rows, report = aggregate([
        event("2026-08-17T09:15:01+05:30", 100, 1),
        event("2026-08-17T09:19:59+05:30", 105, 2),
        event("2026-08-17T09:20:00+05:30", 110, 3),
    ], "2026-08-17")
    assert rows[0]["open"] == 100 and rows[0]["high"] == 105 and rows[0]["close"] == 105
    assert rows[1]["open"] == 110
    assert report["observed_complete_bar_count"] == 2


def test_late_start_fails_closed_and_does_not_fill():
    rows, report = aggregate([event("2026-08-17T11:55:01+05:30", 100)], "2026-08-17")
    assert rows == []
    assert report["coverage_complete"] is False
    assert len(report["missing_bar_starts"]) == 27


def test_sqlite_read_only_and_hash_unchanged(tmp_path):
    db = tmp_path / "ticks.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("create table ticks (instrument_token integer, last_price real, timestamp_iso text)")
    connection.executemany("insert into ticks values (?,?,?)", [
        (256265, 100, "2026-08-17T03:45:01Z"), (256265, 105, "2026-08-17T03:49:59Z")
    ])
    connection.commit(); connection.close()
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    events, quality = read_sqlite_events(db, 256265)
    assert len(events) == 2 and quality["invalid_event_count"] == 0
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_invalid_price_and_wrong_instrument_are_excluded(tmp_path):
    db = tmp_path / "ticks.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("create table ticks (instrument_token integer, last_price real, timestamp_iso text)")
    connection.executemany("insert into ticks values (?,?,?)", [
        (256265, 0, "2026-08-17T03:45:01Z"), (260105, 100, "2026-08-17T03:45:02Z")
    ])
    connection.commit(); connection.close()
    events, quality = read_sqlite_events(db, 256265)
    assert events == [] and quality["invalid_event_count"] == 1


def test_export_manifest_and_incomplete_gate(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({"symbol": "NIFTY", "price": 100, "ts_ist": "2026-08-17T11:55:01+05:30"}) + "\n")
    with pytest.raises(ValueError, match="opening-window coverage"):
        export(trace, tmp_path / "out.csv", tmp_path / "manifest.json", "2026-08-17", "price-trace")
    manifest = export(trace, tmp_path / "out.csv", tmp_path / "manifest.json", "2026-08-17", "price-trace", allow_incomplete=True)
    assert manifest["h1_replay_input_valid"] is False
    assert manifest["source_db_mutated"] is False
    assert list(csv.DictReader((tmp_path / "out.csv").open())) == []
