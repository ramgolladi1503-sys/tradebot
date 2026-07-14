import json
import pytest
import subprocess
from pathlib import Path

def _write_source(tmp_path, *, include_last_price: bool) -> Path:
    raw_event = {
        "local_ts": 1782969042.612944,
        "symbol": "NIFTY",
        "raw_tick": {
            "instrument_token": 256265,
            "volume_traded": 15000,
            "exchange_timestamp": "2026-07-02 10:15:00",
        },
    }
    if include_last_price:
        raw_event["raw_tick"]["last_price"] = 24350.0
    source = tmp_path / "source.jsonl"
    with source.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(raw_event) + "\n")
    return source

def test_invalid_state_cannot_pass(tmp_path):
    source = _write_source(tmp_path, include_last_price=False)

    out = tmp_path / "evidence.jsonl"
    proc = subprocess.run([
        "scripts/run_nifty_vertical_slice_replay.py",
        "--source", str(source),
        "--row-index", "0",
        "--output", str(out)
    ], capture_output=True, text=True)

    assert proc.returncode == 0
    assert out.exists()
    lines = out.read_text().strip().split("\n")
    trace = json.loads(lines[-1])
    assert trace["normalized_snapshot"] == "SUCCESS"
    assert trace["strategy_context"] == "SUCCESS"
    assert trace["decision"] == "EXPLICIT_REJECTION"
    assert trace["reason"] == "No candidate produced by strategy"
    assert trace["replay_only"] is True
    assert trace["broker_api_called"] is False
    assert trace["order_action"] is False
    assert trace["live_feed_used"] is False
    assert trace["append"] is False
    assert trace["output_isolated"] is True
    assert trace["production_artifacts_written"] is False

def test_nifty_real_replay_vertical_slice_normal(tmp_path):
    source = _write_source(tmp_path, include_last_price=True)
    out = tmp_path / "evidence.jsonl"

    proc = subprocess.run([
        "scripts/run_nifty_vertical_slice_replay.py",
        "--source", source,
        "--row-index", "0",
        "--output", str(out)
    ], capture_output=True, text=True)

    assert proc.returncode == 0
    assert out.exists()

    lines = out.read_text().strip().split("\n")
    trace = json.loads(lines[-1])
    assert trace["normalized_snapshot"] == "SUCCESS"
    assert trace["strategy_context"] == "SUCCESS"
    assert trace["decision"] in ("EXPLICIT_REJECTION", "CANDIDATE")
    assert trace["read_only"] is True
    assert trace["replay_only"] is True
    assert trace["broker_api_called"] is False
    assert trace["order_action"] is False
    assert trace["live_feed_used"] is False
    assert trace["append"] is False
    assert trace["output_isolated"] is True
    assert trace["production_artifacts_written"] is False

def test_nifty_real_replay_determinism(tmp_path):
    source = _write_source(tmp_path, include_last_price=True)
    out = tmp_path / "evidence.jsonl"

    for _ in range(3):
        subprocess.run([
            "scripts/run_nifty_vertical_slice_replay.py",
            "--source", source,
            "--row-index", "0",
            "--output", str(out)
        ], capture_output=True, text=True)

    t1, t2, t3 = [json.loads(line) for line in out.read_text().strip().split("\n")]
    assert t1 == t2 == t3
