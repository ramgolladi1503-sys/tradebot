from __future__ import annotations

import json
from pathlib import Path

from scripts.seal_independent_confirmation_epoch_v3 import readiness


BASE = Path("research/independent_underlying_confirmation_v3/data_acquisition")


def test_250_session_and_365_day_gates_fail_empty_manifest():
    result = readiness({"sessions": []})

    assert result["eligible_sessions"] == 0
    assert result["session_gate_pass"] is False
    assert result["calendar_gate_pass"] is False


def test_instrument_resolution_is_exact_underlying():
    resolution = json.loads((BASE / "underlying_instrument_resolution.json").read_text())

    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        row = resolution["resolved"][symbol]
        assert row["resolution_status"] == "UNIQUE_EXACT_INDEX_MATCH"
        assert row["instrument_type"] == "INDEX"
        assert row["option_match"] is False


def test_readiness_waits_when_no_credentials_and_no_sessions():
    report = json.loads((BASE / "readiness_report.json").read_text())
    final = json.loads((BASE / "final_verdict.json").read_text())

    assert report["eligible_sessions"] >= 250
    assert report["session_gate_pass"] is True
    assert report["calendar_gate_pass"] is True
    assert final["FINAL_VERDICT"] == "INDEPENDENT_UNSEEN_EPOCH_SEALED_READY_FOR_EVALUATION"
    assert final["independent_epoch_opened"] is False


def test_sealed_not_opened_artifacts_present_when_ready():
    seal = json.loads((BASE / "seal_certificate.json").read_text())
    manifest = json.loads((BASE / "sealed_session_manifest.json").read_text())

    assert seal["sealed"] is True
    assert seal["opened"] is False
    assert len(manifest["sessions"]) >= 250
