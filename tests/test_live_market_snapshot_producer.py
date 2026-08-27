import json
import sqlite3
from pathlib import Path

from core.live_market_snapshot_producer import build_live_market_snapshot
from core.market_snapshot_schema import validate_market_snapshot


def test_builds_causal_snapshot_from_sqlite(tmp_path: Path):
    db = tmp_path / "x.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table ticks(timestamp text, instrument_token integer, last_price real, volume integer, oi integer, timestamp_epoch real, timestamp_iso text)")
    con.executemany("insert into ticks values(?,?,?,?,?,?,?)", [("", 256265, 100.0, 10, 0, 1000.0, ""), ("", 256265, 101.0, 20, 0, 1059.0, "")])
    con.commit(); con.close()
    out = tmp_path / "snapshots" / "market_snapshot_latest.json"
    snap = build_live_market_snapshot(db_path=db, output_path=out, session_id="s", session_date="2026-08-27", source_sha="a"*40, now_epoch=1060.0)
    ok, errors = validate_market_snapshot(snap)
    assert ok, errors
    assert snap["producer_meta"]["source_sha"] == "a"*40
    assert snap["producer_meta"]["max_input_timestamp"] == "1970-01-01T00:17:39Z"
    assert json.loads(out.read_text())["producer_meta"]["session_id"] == "s"


def test_missing_persisted_inputs_fail_closed(tmp_path: Path):
    db = tmp_path / "x.sqlite"; con = sqlite3.connect(db)
    con.execute("create table ticks(timestamp text, instrument_token integer, last_price real, volume integer, oi integer, timestamp_epoch real, timestamp_iso text)"); con.commit(); con.close()
    try:
        build_live_market_snapshot(db_path=db, output_path=tmp_path / "out.json", session_id="s", session_date="2026-08-27", source_sha="a"*40, now_epoch=1060.0)
    except RuntimeError as exc:
        assert str(exc) == "CANONICAL_MARKET_SNAPSHOT_INPUTS_UNAVAILABLE"
    else:
        raise AssertionError("missing inputs must fail closed")
