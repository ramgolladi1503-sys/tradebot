import json
from pathlib import Path

from core.market_context import derive_market_context
from core.regime_monitor import RegimeMonitor


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_regime_monitor_writes_runtime_root_without_zero_ohlc(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / ".runtime"))
    tracked = tmp_path / "runtime" / "strategy_validation" / "regime_timeline.jsonl"
    tracked.parent.mkdir(parents=True)
    tracked.write_text(json.dumps({"source": "historical"}) + "\n")

    monitor = RegimeMonitor(status_path=tmp_path / "status.json", log_path=tmp_path / "monitor.jsonl")
    monitor.record_market_snapshot(symbol="NIFTY", predicted_regime="RANGE", confidence=0.8, ltp=100, ts_epoch=1)
    monitor.record_market_snapshot(symbol="NIFTY", predicted_regime="RANGE", confidence=0.8, ltp=100.1, ts_epoch=2)

    runtime = tmp_path / ".runtime" / "strategy_validation" / "regime_timeline.jsonl"
    assert len(_rows(tracked)) == 1
    row = _rows(runtime)[0]
    assert row["source"] == "runtime"
    assert row["source_file"] == "regime_monitor"
    assert all(field not in row for field in ("open", "high", "low", "close"))


def test_market_context_runtime_and_replay_paths_are_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / ".runtime"))
    monkeypatch.chdir(tmp_path)
    tracked = tmp_path / "runtime" / "strategy_validation" / "regime_timeline.jsonl"
    tracked.parent.mkdir(parents=True)
    tracked.write_text(json.dumps({"source": "historical"}) + "\n")

    derive_market_context({"execution_mode": "LIVE", "market_open": True, "symbol": "NIFTY"})
    runtime = tmp_path / ".runtime" / "strategy_validation" / "regime_timeline.jsonl"
    assert runtime.exists()
    assert len(_rows(tracked)) == 1
    assert _rows(runtime)[-1]["source"] == "runtime"

    derive_market_context({"execution_mode": "SIM", "source": "replay", "source_file": "fixture.json"})
    assert len(_rows(tracked)) == 2
    replay_row = _rows(tracked)[-1]
    assert replay_row["source"] == "replay"
    assert "open" not in replay_row
