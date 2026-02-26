from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.suggestion_reliability import evaluate_suggestion_reliability


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_reliability_degraded_when_ratio_below_floor(monkeypatch, tmp_path):
    decision_path = tmp_path / "decision_events.jsonl"
    reject_path = tmp_path / "reject_reasons.jsonl"
    decision_rows = []
    for idx in range(30):
        decision_rows.append(
            {
                "ts_epoch": 990.0,
                "gatekeeper_allowed": 1,
                "strategy_id": f"STRAT_{idx}" if idx < 2 else "",
            }
        )
    reject_rows = [{"ts_epoch": 990.0, "reason_code": "no_signal"} for _ in range(8)]
    _write_jsonl(decision_path, decision_rows)
    _write_jsonl(reject_path, reject_rows)

    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_WINDOW_SEC", 300.0, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_MIN_RATIO", 0.20, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_MIN_ALLOWED", 20, raising=False)

    payload = evaluate_suggestion_reliability(
        market_context={"execution_mode": "PAPER", "market_open": False},
        now_epoch=1000.0,
        decision_events_path=decision_path,
        reject_reasons_path=reject_path,
    )
    assert payload["status"] == "DEGRADED"
    assert "SUGGESTION_RATIO_BELOW_FLOOR" in payload["reason_codes"]
    assert payload["allowed_count"] == 30
    assert payload["candidate_count"] == 2
    assert payload["top_reject_reasons"].get("no_signal") == 8


def test_reliability_insufficient_sample(monkeypatch, tmp_path):
    decision_path = tmp_path / "decision_events.jsonl"
    reject_path = tmp_path / "reject_reasons.jsonl"
    _write_jsonl(
        decision_path,
        [{"ts_epoch": 995.0, "gatekeeper_allowed": 1, "strategy_id": "STRAT_A"}],
    )
    _write_jsonl(reject_path, [])

    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_WINDOW_SEC", 300.0, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_MIN_RATIO", 0.20, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_MIN_ALLOWED", 5, raising=False)

    payload = evaluate_suggestion_reliability(
        market_context={"execution_mode": "SIM", "market_open": False},
        now_epoch=1000.0,
        decision_events_path=decision_path,
        reject_reasons_path=reject_path,
    )
    assert payload["status"] == "INSUFFICIENT_SAMPLE"
    assert "SUGGESTION_SAMPLE_TOO_SMALL" in payload["reason_codes"]


def test_reliability_live_mode_stays_informational(monkeypatch, tmp_path):
    decision_path = tmp_path / "decision_events.jsonl"
    reject_path = tmp_path / "reject_reasons.jsonl"
    _write_jsonl(
        decision_path,
        [{"ts_epoch": 990.0, "gatekeeper_allowed": 1, "strategy_id": ""} for _ in range(25)],
    )
    _write_jsonl(reject_path, [{"ts_epoch": 990.0, "reason_code": "feed_stale"}])

    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_WINDOW_SEC", 300.0, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_MIN_RATIO", 0.90, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_MIN_ALLOWED", 20, raising=False)

    payload = evaluate_suggestion_reliability(
        market_context={"execution_mode": "LIVE", "market_open": True},
        now_epoch=1000.0,
        decision_events_path=decision_path,
        reject_reasons_path=reject_path,
    )
    assert payload["status"] == "OK"
    assert payload["mode"] == "LIVE"
