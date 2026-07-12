import json
import pytest
import subprocess
from pathlib import Path

def test_nifty_real_replay_vertical_slice_missing_field(tmp_path):
    raw_event = {
        "local_ts": 1782969042.612944,
        "symbol": "NIFTY",
        "raw_tick": {
            "instrument_token": 256265,
            # last_price is missing!
            "volume_traded": 15000,
            "exchange_timestamp": "2026-07-02 10:15:00",
        }
    }
    source = tmp_path / "source.jsonl"
    with open(source, "w") as f:
        f.write(json.dumps(raw_event) + "\n")

    out = tmp_path / "evidence.jsonl"
    proc = subprocess.run([
        "scripts/run_nifty_vertical_slice_replay.py",
        "--source", str(source),
        "--row-index", "0",
        "--output", str(out)
    ], capture_output=True, text=True)

    assert out.exists()
    lines = out.read_text().strip().split("\n")
    trace = json.loads(lines[-1])
    assert trace["decision"] in ("EXPLICIT_REJECTION", "FAILED")

def test_nifty_real_replay_vertical_slice_normal(tmp_path):
    source = "data/ticks/20260702/index_ticks.jsonl"
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
    assert "decision" in trace
    assert trace["read_only"] is True

def test_nifty_real_replay_determinism(tmp_path):
    source = "data/ticks/20260702/index_ticks.jsonl"
    out = tmp_path / "evidence.jsonl"

    for _ in range(3):
        subprocess.run([
            "scripts/run_nifty_vertical_slice_replay.py",
            "--source", source,
            "--row-index", "0",
            "--output", str(out)
        ], capture_output=True, text=True)

    lines = out.read_text().strip().split("\n")
    assert len(lines) == 3
    t1, t2, t3 = [json.loads(line) for line in lines]
    assert t1 == t2 == t3
