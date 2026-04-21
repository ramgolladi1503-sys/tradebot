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
    assert rows[0]["candidate_outcome_label"] == "favorable_excursion"
    assert rows[0]["candidate_outcome_label_provenance"]["scope"] == "candidate"

    perf_path = Path(cfg.LOGS_ROOT) / "suggestion_strategy_perf.json"
    perf = json.loads(perf_path.read_text())
    stats = perf.get("stats") or {}
    assert "QUICK_OPT" in stats
    assert "TARGET_POINTS::QUICK_OPT" in stats


def test_target_points_evaluation_reads_incrementally(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_INCREMENTAL_READ_ENABLE", True, raising=False)
    suggestions_path = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    eval_path = tmp_path / "runtime" / "logs" / "suggestion_eval.jsonl"
    suggestions_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(suggestions_path), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_LOG_PATH", str(eval_path), raising=False)

    suggestion_one = {
        "trade_id": "NIFTY-24000-CE-INC1",
        "symbol": "NIFTY",
        "strike": 24000,
        "entry": 100.0,
        "stop": 90.0,
        "target": 110.0,
        "strategy": "QUICK_OPT",
    }
    suggestions_path.write_text(json.dumps(suggestion_one) + "\n")

    orch = Orchestrator.__new__(Orchestrator)
    Orchestrator._load_suggestion_eval(orch)
    market_data = [
        {
            "instrument": "OPT",
            "symbol": "NIFTY",
            "ltp": 24010.0,
            "option_chain": [{"strike": 24000, "type": "CE", "ltp": 112.0}],
        }
    ]

    orch._evaluate_suggestions(market_data)
    rows = _read_jsonl(eval_path)
    assert [row["trade_id"] for row in rows] == ["NIFTY-24000-CE-INC1"]

    first_offset = orch._suggestion_log_offsets[str(suggestions_path)]["offset"]
    orch._evaluate_suggestions(market_data)
    rows = _read_jsonl(eval_path)
    assert [row["trade_id"] for row in rows] == ["NIFTY-24000-CE-INC1"]
    assert orch._suggestion_log_offsets[str(suggestions_path)]["offset"] == first_offset

    suggestion_two = {
        "trade_id": "NIFTY-24050-CE-INC2",
        "symbol": "NIFTY",
        "strike": 24050,
        "entry": 120.0,
        "stop": 110.0,
        "target": 130.0,
        "strategy": "QUICK_OPT",
    }
    with suggestions_path.open("a") as f:
        f.write(json.dumps(suggestion_two) + "\n")

    market_data[0]["option_chain"].append({"strike": 24050, "type": "CE", "ltp": 131.0})
    orch._evaluate_suggestions(market_data)
    rows = _read_jsonl(eval_path)
    assert [row["trade_id"] for row in rows] == [
        "NIFTY-24000-CE-INC1",
        "NIFTY-24050-CE-INC2",
    ]
    assert orch._suggestion_log_offsets[str(suggestions_path)]["offset"] > first_offset


def test_target_points_evaluation_respects_interval_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_INTERVAL_SEC", 60.0, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_INCREMENTAL_READ_ENABLE", True, raising=False)
    suggestions_path = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    eval_path = tmp_path / "runtime" / "logs" / "suggestion_eval.jsonl"
    suggestions_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(suggestions_path), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_LOG_PATH", str(eval_path), raising=False)

    suggestions_path.write_text(
        json.dumps(
            {
                "trade_id": "NIFTY-24000-CE-TIME1",
                "symbol": "NIFTY",
                "strike": 24000,
                "entry": 100.0,
                "stop": 90.0,
                "target": 110.0,
                "strategy": "QUICK_OPT",
            }
        )
        + "\n"
    )

    orch = Orchestrator.__new__(Orchestrator)
    Orchestrator._load_suggestion_eval(orch)
    market_data = [
        {
            "instrument": "OPT",
            "symbol": "NIFTY",
            "ltp": 24010.0,
            "option_chain": [{"strike": 24000, "type": "CE", "ltp": 112.0}],
        }
    ]

    clock = {"now": 1000.0}
    monkeypatch.setattr("core.orchestrator.now_utc_epoch", lambda: clock["now"])

    orch._evaluate_suggestions(market_data)
    assert [row["trade_id"] for row in _read_jsonl(eval_path)] == ["NIFTY-24000-CE-TIME1"]

    with suggestions_path.open("a") as f:
        f.write(
            json.dumps(
                {
                    "trade_id": "NIFTY-24050-CE-TIME2",
                    "symbol": "NIFTY",
                    "strike": 24050,
                    "entry": 120.0,
                    "stop": 110.0,
                    "target": 130.0,
                    "strategy": "QUICK_OPT",
                }
            )
            + "\n"
        )

    market_data[0]["option_chain"].append({"strike": 24050, "type": "CE", "ltp": 131.0})
    clock["now"] = 1030.0
    orch._evaluate_suggestions(market_data)
    assert [row["trade_id"] for row in _read_jsonl(eval_path)] == ["NIFTY-24000-CE-TIME1"]

    clock["now"] = 1061.0
    orch._evaluate_suggestions(market_data)
    assert [row["trade_id"] for row in _read_jsonl(eval_path)] == [
        "NIFTY-24000-CE-TIME1",
        "NIFTY-24050-CE-TIME2",
    ]
