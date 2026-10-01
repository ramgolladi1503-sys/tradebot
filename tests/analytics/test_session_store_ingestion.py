from __future__ import annotations

import json
from pathlib import Path

from core.analytics.store import (
    _int_event_from_strategy_observation_row,
    _int_event_from_trade_truth_row,
    discover_session_paths,
    load_session_events,
    load_trade_intent_events,
)


def test_strategy_observation_parses_into_rejected_event():
    row = {
        "applicability_state": "APPLICABLE",
        "broker_api_called": False,
        "confidence": None,
        "direction": "UNKNOWN",
        "is_order_action": False,
        "missing_or_stale_inputs": ["09:15_10:00_underlying_return", "15:14_fresh_observation"],
        "pulse_id": "7021db21cd023671a97ab7c58368a99dea80d70f11c24be7725370a5f2fbad3d",
        "qualification_state": "UNKNOWN",
        "read_only": True,
        "reason_code": "CAS_PRIMITIVE_0915_INVALID",
        "required_inputs": ["09:15_10:00_underlying_return", "15:14_fresh_observation"],
        "source_event_or_snapshot_reference": {"generic_signal_used_for_qualification": False},
        "strategy_id": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        "symbol": "NIFTY",
        "timestamp_epoch": 1790841503.883224,
        "timestamp_ist": "2026-10-01T13:28:23.883224+05:30",
    }
    event = _int_event_from_strategy_observation_row(row, source="session_obs:test")
    assert event is not None
    assert event.symbol == "NIFTY"
    assert event.intent == "rejected"
    assert event.reject_reason == "CAS_PRIMITIVE_0915_INVALID"
    assert len(event.gate_decisions) == 1
    assert event.gate_decisions[0].gate_name == "strategy_qualification"
    assert event.gate_decisions[0].passed is False
    assert event.metrics_snapshot["strategy_id"] == "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"
    assert event.metrics_snapshot["pulse_id"] == "7021db21cd023671a97ab7c58368a99dea80d70f11c24be7725370a5f2fbad3d"


def test_trade_truth_stream_parses_into_rejected_event():
    row = {
        "identity": {
            "candidate_id": "NONE",
            "expiry": None,
            "instrument": "NIFTY",
            "lot_size": None,
            "option_type": None,
            "parent_trace_id": None,
            "session_id": "meg-live-test",
            "strategy_id": "NONE",
            "strike": None,
            "trace_id": "f8242e0b556e4fc1c46faca7752e3ca3a12e9424a2a8f24a96a29899d94089c9",
            "truth_record_id": "truth_meg-live-test_1",
            "underlying": "NIFTY",
        },
        "decision": {
            "blockers": [],
            "candidate_generated": False,
            "candidate_score": None,
            "final_action": "OBSERVE",
            "governance_decision": "BLOCKED",
            "option_selection_reason": None,
            "rank": None,
            "ranking_reasons": ["NO_CANDIDATE"],
            "reason_codes": ["NO_CANDIDATE"],
            "risk_result": "NOT_APPLICABLE_NO_CANDIDATES",
        },
        "timing": {
            "decision_timestamp_epoch": 1790841488.280399,
        },
    }
    event = _int_event_from_trade_truth_row(row, source="session_truth:test")
    assert event is not None
    assert event.symbol == "NIFTY"
    assert event.intent == "rejected"
    assert event.reject_reason == "NO_CANDIDATE"
    assert len(event.gate_decisions) == 1
    assert event.gate_decisions[0].gate_name == "governance_decision"
    assert event.gate_decisions[0].passed is False
    assert event.metrics_snapshot["governance_decision"] == "BLOCKED"
    assert event.metrics_snapshot["trace_id"] == "f8242e0b556e4fc1c46faca7752e3ca3a12e9424a2a8f24a96a29899d94089c9"


def test_load_session_events_from_directory(tmp_path: Path):
    session_dir = tmp_path / "meg-live-test-run"
    session_dir.mkdir(parents=True)

    obs_file = session_dir / "strategy_observations.jsonl"
    obs_file.write_text(
        json.dumps(
            {
                "symbol": "BANKNIFTY",
                "strategy_id": "CAS_STRATEGY_TEST",
                "reason_code": "PREMARKET_DATA_MISSING",
                "pulse_id": "p12345",
                "timestamp_epoch": 1790841500.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    truth_file = session_dir / "trade_truth_stream.jsonl"
    truth_file.write_text(
        json.dumps(
            {
                "identity": {"underlying": "BANKNIFTY", "trace_id": "tr_999"},
                "decision": {
                    "governance_decision": "BLOCKED",
                    "reason_codes": ["FEED_STALE"],
                },
                "timing": {"decision_timestamp_epoch": 1790841505.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = load_session_events([session_dir])
    assert len(events) == 2
    assert events[0].symbol == "BANKNIFTY"
    assert events[0].reject_reason == "PREMARKET_DATA_MISSING"
    assert events[1].symbol == "BANKNIFTY"
    assert events[1].reject_reason == "FEED_STALE"

    all_events = load_trade_intent_events(
        session_paths=[session_dir],
        review_queue_paths=[],
        decision_telemetry_paths=[],
    )
    assert len(all_events) == 2


def test_discover_session_paths(tmp_path: Path):
    sessions_root = tmp_path / "sessions"
    date_dir = sessions_root / "session_2026-10-01" / "2026-10-01" / "run_abc"
    date_dir.mkdir(parents=True)

    paths = discover_session_paths(date_key="2026-10-01", session_dir=sessions_root)
    assert any(p == date_dir for p in paths)
