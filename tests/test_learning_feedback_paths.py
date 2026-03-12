import json
from pathlib import Path

from config import config as cfg
from core.review_queue import add_to_queue
from core.orchestrator import Orchestrator


def _queue_trade(**overrides):
    trade = {
        "trade_id": "T-1",
        "symbol": "NIFTY",
        "strike": 24000,
        "instrument": "OPT",
        "instrument_type": "OPT",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "target": 120.0,
        "qty": 25,
        "timestamp": "2026-02-24T10:00:00+05:30",
        "strategy_id": "CORE",
        "strategy_name": "CORE",
    }
    trade.update(overrides)
    return trade


def test_add_to_queue_writes_canonical_suggestions_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    canonical = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(canonical), raising=False)

    trade = _queue_trade()

    add_to_queue(trade, queue_path=tmp_path / "queue.json")

    assert canonical.exists()
    rows = [json.loads(line) for line in canonical.read_text().splitlines() if line.strip()]
    assert rows and rows[0]["trade_id"] == "T-1"
    assert rows[0]["strategy_id"] == "CORE"
    assert rows[0]["strategy_name"] == "CORE"


def test_add_to_queue_backfills_legacy_strategy_identity_for_minimal_trade(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    canonical = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(canonical), raising=False)

    trade = _queue_trade(strategy_id=None, strategy_name=None)

    add_to_queue(trade, queue_path=tmp_path / "queue.json")

    assert canonical.exists()
    rows = [json.loads(line) for line in canonical.read_text().splitlines() if line.strip()]
    assert rows and rows[0]["trade_id"] == "T-1"
    assert rows[0]["strategy_id"] == "LEGACY_QUEUE"
    assert rows[0]["strategy_name"] == "LEGACY_QUEUE"


def test_add_to_queue_dedupes_same_suggestions_destination(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    canonical = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(canonical), raising=False)

    import core.review_queue as review_queue

    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [canonical])
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (100.0, 200.0))

    trade = _queue_trade(
        trade_id="T-DEDUPE-1",
        tradingsymbol="NIFTY27MAR24000CE",
        instrument_token=123456,
        instrument_id="NIFTY27MAR24000CE",
        expiry_date="2026-03-27",
        expiry="2026-03-27",
        option_type="CE",
        right="CE",
    )

    add_to_queue(trade, queue_path=tmp_path / "queue.json")

    rows = [json.loads(line) for line in canonical.read_text().splitlines() if line.strip()]
    assert len([row for row in rows if row.get("trade_id") == "T-DEDUPE-1"]) == 1


def test_add_to_queue_writes_once_per_distinct_suggestions_destination(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    canonical = tmp_path / "runtime" / "logs" / "suggestions.jsonl"
    legacy = tmp_path / "logs" / "suggestions.jsonl"
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(canonical), raising=False)

    import core.review_queue as review_queue

    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [canonical, legacy])
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (100.0, 200.0))

    trade = _queue_trade(
        trade_id="T-DEDUPE-2",
        symbol="BANKNIFTY",
        strike=52000,
        tradingsymbol="BANKNIFTY27MAR52000PE",
        instrument_token=223456,
        instrument_id="BANKNIFTY27MAR52000PE",
        expiry_date="2026-03-27",
        expiry="2026-03-27",
        option_type="PE",
        right="PE",
        qty=15,
        timestamp="2026-02-24T10:05:00+05:30",
    )

    add_to_queue(trade, queue_path=tmp_path / "queue.json")

    canonical_rows = [json.loads(line) for line in canonical.read_text().splitlines() if line.strip()]
    legacy_rows = [json.loads(line) for line in legacy.read_text().splitlines() if line.strip()]
    assert len([row for row in canonical_rows if row.get("trade_id") == "T-DEDUPE-2"]) == 1
    assert len([row for row in legacy_rows if row.get("trade_id") == "T-DEDUPE-2"]) == 1


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
