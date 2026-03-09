from __future__ import annotations

import json

from config import config as cfg
from core.telemetry_streams import (
    append_candidate_stream_event,
    append_decision_stream_event,
    candidates_stream_path,
    compute_candidate_id,
    decisions_stream_path,
)


def test_candidate_id_is_deterministic():
    payload = {
        "symbol": "NIFTY",
        "cycle_id": "abc",
        "timestamp": 123.45,
        "instrument": "OPT",
        "strike": 24500,
        "expiry_date": "2026-03-05",
        "option_type": "CE",
    }
    first = compute_candidate_id(payload)
    second = compute_candidate_id(payload)
    assert first == second


def test_append_candidate_and_decision_stream(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)

    candidate = append_candidate_stream_event(
        {
            "symbol": "NIFTY",
            "cycle_id": "cycle1",
            "ts_epoch": 100.0,
        },
        desk_id="TEST",
    )
    assert candidate.get("candidate_id")

    decision = append_decision_stream_event(
        {
            "event_type": "decision_evaluated",
            "symbol": "NIFTY",
            "candidate_id": candidate["candidate_id"],
            "allowed": False,
            "decision_stage": "N4_QUOTE_OK",
            "blockers": ["QUOTE_INVALID"],
            "ts_epoch": 100.0,
        },
        desk_id="TEST",
    )
    assert decision["candidate_id"] == candidate["candidate_id"]

    c_path = candidates_stream_path("TEST")
    d_path = decisions_stream_path("TEST")
    assert c_path.exists()
    assert d_path.exists()

    c_rows = [json.loads(line) for line in c_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    d_rows = [json.loads(line) for line in d_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(c_rows) == 1
    assert len(d_rows) == 1
    assert d_rows[0]["event_type"] == "decision_evaluated"
    assert d_rows[0]["allowed"] is False

