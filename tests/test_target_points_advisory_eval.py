import json
from pathlib import Path

from config import config as cfg
from core.orchestrator import Orchestrator


def _read_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def test_target_points_evaluation_records_category_and_strategy_bucket(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    suggestions_path = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    eval_path = tmp_path / "runtime" / "logs" / "suggestion_eval.jsonl"
    suggestions_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(suggestions_path), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_LOG_PATH", str(eval_path), raising=False)

    suggestion = {
        "trade_id": "NIFTY-24000-CE-TP1",
        "symbol": "NIFTY",
        "strike": 24000,
        "entry": 100.0,
        "stop": 90.0,
        "target": 110.0,
        "strategy": "QUICK_OPT",
        "category": "target_points",
        "tier": "OPPORTUNITY",
    }
    suggestions_path.write_text(json.dumps(suggestion) + "\n")

    orch = Orchestrator.__new__(Orchestrator)
    Orchestrator._load_suggestion_eval(orch)

    market_data = [
        {
            "instrument": "OPT",
            "symbol": "NIFTY",
            "ltp": 24010.0,
            "option_chain": [
                {"strike": 24000, "type": "CE", "ltp": 112.0},
            ],
        }
    ]

    orch._evaluate_suggestions(market_data)

    rows = _read_jsonl(eval_path)
    assert len(rows) == 1
    assert rows[0]["trade_id"] == suggestion["trade_id"]
    assert rows[0]["category"] == "target_points"
    assert rows[0]["strategy"] == "QUICK_OPT"
    assert rows[0]["outcome"] == "target"

    perf_path = Path(cfg.LOGS_ROOT) / "suggestion_strategy_perf.json"
    perf = json.loads(perf_path.read_text())
    stats = perf.get("stats") or {}
    assert "QUICK_OPT" in stats
    assert "TARGET_POINTS::QUICK_OPT" in stats
