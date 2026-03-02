import json
from pathlib import Path

from config import config as cfg
from core.review_queue import add_to_queue
from core.orchestrator import Orchestrator


def test_add_to_queue_writes_canonical_suggestions_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    canonical = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(canonical), raising=False)

    trade = {
        "trade_id": "T-1",
        "symbol": "NIFTY",
        "strike": 24000,
        "instrument": "OPT",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "target": 120.0,
        "qty": 25,
        "timestamp": "2026-02-24T10:00:00+05:30",
    }

    add_to_queue(trade, queue_path=tmp_path / "queue.json")

    assert canonical.exists()
    rows = [json.loads(line) for line in canonical.read_text().splitlines() if line.strip()]
    assert rows and rows[0]["trade_id"] == "T-1"


def test_orchestrator_load_suggestion_eval_reads_canonical_and_legacy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    canonical = tmp_path / "runtime" / "logs" / "suggestion_eval.jsonl"
    legacy = Path(cfg.LOGS_ROOT) / "suggestion_eval.jsonl"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(json.dumps({"trade_id": "CANON"}) + "\n")
    legacy.write_text(json.dumps({"trade_id": "LEGACY"}) + "\n")
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_LOG_PATH", str(canonical), raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    Orchestrator._load_suggestion_eval(orch)

    assert orch.suggestion_eval_path == Path(canonical)
    assert orch.suggestion_evaluated == {"CANON", "LEGACY"}
