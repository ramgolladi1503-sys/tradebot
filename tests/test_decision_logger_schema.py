import json
from pathlib import Path

import pytest

from config import config as cfg
import core.decision_logger as dl


def test_decision_logger_requires_instrument_id(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    jsonl_path = tmp_path / "decisions.jsonl"
    error_path = tmp_path / "errors.jsonl"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(dl, "DECISION_JSONL", jsonl_path)
    monkeypatch.setattr(dl, "DECISION_ERROR_LOG", error_path)

    bad_event = {
        "trade_id": "T1",
        "trace_id": "T1",
        "desk_id": "D1",
        "timestamp_epoch": 1700000000.0,
        "quote_age_sec": 1.0,
        "symbol": "NIFTY",
    }
    with pytest.raises(ValueError):
        dl.log_decision(bad_event)

    assert error_path.exists()
    content = error_path.read_text().strip()
    assert "decision_event_missing_fields" in content


def test_decision_logger_trace_id_default(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    jsonl_path = tmp_path / "decisions.jsonl"
    error_path = tmp_path / "errors.jsonl"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(dl, "DECISION_JSONL", jsonl_path)
    monkeypatch.setattr(dl, "DECISION_ERROR_LOG", error_path)

    ok_event = {
        "trade_id": "T2",
        "desk_id": "D1",
        "timestamp_epoch": 1700000001.0,
        "quote_age_sec": 1.0,
        "instrument_id": "NIFTY|2026-02-27|100|CE",
        "symbol": "NIFTY",
    }
    trade_id = dl.log_decision(ok_event)
    assert trade_id == "T2"
    data = json.loads(jsonl_path.read_text().splitlines()[-1])
    assert data.get("trace_id") == "T2"
