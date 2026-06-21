import os
import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch
from core.ranking_telemetry import log_ranking_snapshots, _RANKING_SNAPSHOT_JSONL, _conn, _TELEMETRY_COUNTERS, _init_db

@pytest.fixture(autouse=True)
def clean_db():
    _init_db()
    if _RANKING_SNAPSHOT_JSONL.exists():
        _RANKING_SNAPSHOT_JSONL.unlink()
    with _conn() as conn:
        try:
            conn.execute("DELETE FROM ranking_snapshots")
        except sqlite3.OperationalError:
            pass
    _TELEMETRY_COUNTERS["ranking_snapshot_seen"] = 0
    _TELEMETRY_COUNTERS["ranking_snapshot_written"] = 0
    _TELEMETRY_COUNTERS["ranking_snapshot_failed"] = 0
    yield

def test_writes_five_rows_and_groups_cycle_id():
    candidates = [
        {"trade_score": 90, "confidence": 0.9, "bid": 100},
        {"trade_score": 80, "confidence": 0.8, "bid": 90},
        {"trade_score": 70, "confidence": 0.7, "bid": 80},
        {"trade_score": 60, "confidence": 0.6, "bid": 70},
        {"trade_score": 50, "confidence": 0.5, "bid": 60},
    ]
    
    log_ranking_snapshots(candidates)
    
    assert _TELEMETRY_COUNTERS["ranking_snapshot_written"] == 1
    
    # Check JSONL
    lines = _RANKING_SNAPSHOT_JSONL.read_text().strip().split('\n')
    assert len(lines) == 5
    
    parsed = [json.loads(line) for line in lines]
    cycle_id = parsed[0]["cycle_id"]
    
    for i, p in enumerate(parsed):
        assert p["cycle_id"] == cycle_id
        assert p["rank_position"] == i + 1
        assert p["trade_score"] == candidates[i]["trade_score"]
        
    # Check SQLite
    with _conn() as conn:
        rows = conn.execute("SELECT cycle_id, rank_position, trade_score FROM ranking_snapshots ORDER BY rank_position").fetchall()
        assert len(rows) == 5
        for i, row in enumerate(rows):
            assert row[0] == cycle_id
            assert row[1] == i + 1
            assert row[2] == candidates[i]["trade_score"]

def test_no_mutation():
    candidates = [{"trade_score": 90, "gate_reasons": ["stale"]}, {"trade_score": 80}]
    original_id = id(candidates[0])
    
    log_ranking_snapshots(candidates)
    
    assert id(candidates[0]) == original_id
    assert "cycle_id" not in candidates[0]
    assert "rank_position" not in candidates[0]

def test_failure_does_not_crash():
    candidates = [{"trade_score": 90}, {"trade_score": 80}]
    with patch("core.ranking_telemetry.json.dumps", side_effect=Exception("mocked crash")):
        log_ranking_snapshots(candidates)
    
    assert _TELEMETRY_COUNTERS["ranking_snapshot_failed"] == 1
    assert _TELEMETRY_COUNTERS["ranking_snapshot_written"] == 0

def test_empty_or_single_candidate():
    log_ranking_snapshots([])
    assert _TELEMETRY_COUNTERS["ranking_snapshot_seen"] == 0
    
    log_ranking_snapshots([{"trade_score": 90}])
    assert _TELEMETRY_COUNTERS["ranking_snapshot_seen"] == 0
    assert not _RANKING_SNAPSHOT_JSONL.exists()
