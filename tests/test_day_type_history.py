import json
from pathlib import Path

from core.day_type_history import append_day_type_event, load_day_type_events


def test_append_day_type_event_writes_epoch_and_ist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    append_day_type_event(
        symbol="NIFTY",
        event="CHANGE",
        day_type="TREND_DAY",
        confidence=0.71,
        minutes_since_open=35,
    )
    path = Path("logs/day_type_events.jsonl")
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.get("ts_epoch"), float)
    assert isinstance(row.get("ts_ist"), str) and row["ts_ist"]
    assert row.get("ts") == row.get("ts_ist")


def test_load_day_type_events_backfills_existing_file_safely(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("logs/day_type_events.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "symbol": "SENSEX",
        "event": "TICK",
        "day_type": "RANGE_DAY",
        "confidence": 0.55,
        "minutes_since_open": 42,
        "ts": "2026-02-18T10:00:00+05:30",
    }
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    rows = load_day_type_events(backfill=True)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.get("ts_epoch"), float)
    assert isinstance(row.get("ts_ist"), str) and row["ts_ist"]
    assert row.get("ts") == row.get("ts_ist")

    refreshed = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert isinstance(refreshed[0].get("ts_epoch"), float)
    backups = list(path.parent.glob("day_type_events.bak.*.jsonl"))
    assert backups, "expected safety backup file during backfill"

