from __future__ import annotations

import json
from pathlib import Path

import pytest

from aixion_trade_intelligence.readiness import evaluate_canary_readiness


def write_config(tmp_path: Path, *, mode: str = "SHADOW") -> Path:
    evidence_root = tmp_path / "evidence"
    instrument_master = tmp_path / "instrument_master.json"
    exchange_rules = tmp_path / "exchange_rules.json"
    instrument_master.write_text("{}", encoding="utf-8")
    exchange_rules.write_text("{}", encoding="utf-8")
    measured_previous_session = tmp_path / "previous_session.bin"
    measured_previous_session.write_bytes(b"x" * 1024)
    config = {
        "mode": mode,
        "evidence_root": str(evidence_root),
        "storage": {
            "expected_session_bytes": measured_previous_session.stat().st_size,
            "safety_factor": 1.0,
        },
        "point_in_time_reference_files": [
            str(instrument_master),
            str(exchange_rules),
        ],
        "required_event_types": [
            "SESSION_STARTED",
            "SESSION_ENDED",
            "FEED_TRUTH_UPDATED",
            "STRATEGY_EVALUATED",
            "CANDIDATE_CREATED",
        ],
    }
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_readiness_passes_with_measured_storage_and_references(tmp_path):
    result = evaluate_canary_readiness(write_config(tmp_path))
    assert result.ready is True
    assert result.verdict == "READY_FOR_READ_ONLY_CANARY"
    assert result.checks["mode_boundary"]["live_order_authority"] is False


def test_readiness_refuses_live_mode(tmp_path):
    with pytest.raises(ValueError, match="paper_or_shadow"):
        evaluate_canary_readiness(write_config(tmp_path, mode="LIVE"))


def test_readiness_blocks_missing_reference(tmp_path):
    path = write_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["point_in_time_reference_files"].append(str(tmp_path / "missing.json"))
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_canary_readiness(path)
    assert result.ready is False
    assert result.verdict == "CANARY_BLOCKED"
    assert result.checks["point_in_time_references"]["passed"] is False


def test_readiness_rejects_unmeasured_storage_requirement(tmp_path):
    path = write_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["storage"]["expected_session_bytes"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="measured_positive"):
        evaluate_canary_readiness(path)


def test_readiness_requires_lifecycle_event_contract(tmp_path):
    path = write_config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["required_event_types"] = ["SESSION_STARTED"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_canary_readiness(path)
    assert result.ready is False
    assert result.checks["event_contract"]["passed"] is False
