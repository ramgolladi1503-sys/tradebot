from __future__ import annotations

import json

from core.phase1_observability import (
    build_phase1_observation,
    merge_phase1_cycle_observations,
    record_phase1_observation,
    read_phase1_session_observations,
)


def test_observation_is_read_only_and_counts_real_summary():
    payload = build_phase1_observation(
        cycle_id="c1",
        market_data={"symbol": "NIFTY", "input_current": True},
        scan_summary={"total_candidates": 4, "rejected_by_reason": {"NO_SIGNAL": 3}},
        survivor_count=1,
        phase2_handoff_count=1,
        raw_input_count=4,
        strategy_evaluation_count=1,
    )
    assert payload["raw_input_count"] == 4
    assert payload["survivor_count"] == 1
    assert payload["phase2_handoff_count"] == 1
    assert payload["rejection_reason_counts"] == {"NO_SIGNAL": 3}
    assert payload["read_only"] is True
    assert payload["broker_api_called"] is False


def test_merge_is_session_local_and_deterministic():
    rows = [
        build_phase1_observation(cycle_id="c1", market_data={"input_current": True}, scan_summary={"total_candidates": 2, "rejected_by_reason": {"A": 1}}, survivor_count=1, phase2_handoff_count=1, raw_input_count=2, strategy_evaluation_count=1),
        build_phase1_observation(cycle_id="c2", market_data={"input_current": True}, scan_summary={"total_candidates": 3, "rejected_by_reason": {"A": 2, "B": 1}}, survivor_count=0, phase2_handoff_count=0, raw_input_count=3, strategy_evaluation_count=1),
    ]
    assert merge_phase1_cycle_observations(rows) == {
        "invocation_count": 2, "raw_input_count": 5, "strategy_evaluation_count": 2,
        "pre_filter_count": 5, "survivor_count": 1, "phase2_handoff_count": 1,
        "rejection_reason_counts": {"A": 3, "B": 1}, "exception_count": 0,
        "exception_types": [], "input_current": True,
    }


def test_record_writes_runtime_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    payload = build_phase1_observation(cycle_id="c1", market_data={}, scan_summary={}, survivor_count=0, phase2_handoff_count=0, raw_input_count=0, strategy_evaluation_count=0, exception_type="ValueError")
    record_phase1_observation(payload)
    session_dir = tmp_path / "phase1_observability" / payload["session_id"]
    assert json.loads((session_dir / "phase1_observability_latest.json").read_text())["exception_types"] == ["ValueError"]
    assert len((session_dir / "phase1_observability.jsonl").read_text().splitlines()) == 1
    assert len(read_phase1_session_observations(payload["session_id"], logs_root=tmp_path)) == 1
    assert read_phase1_session_observations("other-session", logs_root=tmp_path) == []


def test_counter_sources_are_exact_for_zero_one_and_n():
    rows = [
        build_phase1_observation(cycle_id="0", market_data={}, scan_summary={}, survivor_count=0, phase2_handoff_count=0, raw_input_count=0, strategy_evaluation_count=0),
        build_phase1_observation(cycle_id="1", market_data={}, scan_summary={}, survivor_count=0, phase2_handoff_count=0, raw_input_count=1, strategy_evaluation_count=1),
        build_phase1_observation(cycle_id="n", market_data={}, scan_summary={}, survivor_count=2, phase2_handoff_count=2, raw_input_count=5, strategy_evaluation_count=3),
    ]
    summary = merge_phase1_cycle_observations(rows)
    assert summary["raw_input_count"] == 6
    assert summary["strategy_evaluation_count"] == 4


def test_session_a_never_reads_session_b(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("TRADEBOT_SESSION_ID", "session-a")
    first = build_phase1_observation(cycle_id="a", market_data={}, scan_summary={}, survivor_count=0, phase2_handoff_count=0, raw_input_count=2, strategy_evaluation_count=1)
    record_phase1_observation(first)
    monkeypatch.setenv("TRADEBOT_SESSION_ID", "session-b")
    second = build_phase1_observation(cycle_id="b", market_data={}, scan_summary={}, survivor_count=0, phase2_handoff_count=0, raw_input_count=7, strategy_evaluation_count=1)
    record_phase1_observation(second)
    assert [row["raw_input_count"] for row in read_phase1_session_observations("session-a", logs_root=tmp_path)] == [2]
    assert [row["raw_input_count"] for row in read_phase1_session_observations("session-b", logs_root=tmp_path)] == [7]
