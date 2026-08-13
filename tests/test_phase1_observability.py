from __future__ import annotations

import json

from core.phase1_observability import (
    build_phase1_observation,
    merge_phase1_cycle_observations,
    record_phase1_observation,
)


def test_observation_is_read_only_and_counts_real_summary():
    payload = build_phase1_observation(
        cycle_id="c1",
        market_data={"symbol": "NIFTY", "input_current": True},
        scan_summary={"total_candidates": 4, "rejected_by_reason": {"NO_SIGNAL": 3}},
        survivor_count=1,
        phase2_handoff_count=1,
    )
    assert payload["raw_input_count"] == 4
    assert payload["survivor_count"] == 1
    assert payload["phase2_handoff_count"] == 1
    assert payload["rejection_reason_counts"] == {"NO_SIGNAL": 3}
    assert payload["read_only"] is True
    assert payload["broker_api_called"] is False


def test_merge_is_session_local_and_deterministic():
    rows = [
        build_phase1_observation(cycle_id="c1", market_data={"input_current": True}, scan_summary={"total_candidates": 2, "rejected_by_reason": {"A": 1}}, survivor_count=1, phase2_handoff_count=1),
        build_phase1_observation(cycle_id="c2", market_data={"input_current": True}, scan_summary={"total_candidates": 3, "rejected_by_reason": {"A": 2, "B": 1}}, survivor_count=0, phase2_handoff_count=0),
    ]
    assert merge_phase1_cycle_observations(rows) == {
        "invocation_count": 2, "raw_input_count": 5, "strategy_evaluation_count": 2,
        "pre_filter_count": 5, "survivor_count": 1, "phase2_handoff_count": 1,
        "rejection_reason_counts": {"A": 3, "B": 1}, "exception_count": 0,
        "exception_types": [], "input_current": True,
    }


def test_record_writes_runtime_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    payload = build_phase1_observation(cycle_id="c1", market_data={}, scan_summary={}, survivor_count=0, phase2_handoff_count=0, exception_type="ValueError")
    record_phase1_observation(payload)
    assert json.loads((tmp_path / "phase1_observability_latest.json").read_text())["exception_types"] == ["ValueError"]
    assert len((tmp_path / "phase1_observability.jsonl").read_text().splitlines()) == 1
