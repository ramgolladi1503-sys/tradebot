from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.contracts import CanonicalEvent, EventValidationError
from aixion_trade_intelligence.publisher import FileEventPublisher
from aixion_trade_intelligence.report import write_analysis_bundle
from aixion_trade_intelligence.session import SessionAnalyzer
from aixion_trade_intelligence.storage import EventLogError, iter_events, verify_event_log


BASE = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)


def event(
    event_id: str,
    event_type: str,
    *,
    second: int,
    sequence: int,
    candidate_id: str = "",
    payload: dict | None = None,
    quality: str = "VALID",
) -> CanonicalEvent:
    event_time = BASE + timedelta(seconds=second)
    source_time = event_time - timedelta(milliseconds=15)
    receive_time = event_time - timedelta(milliseconds=5)
    parse_time = event_time - timedelta(milliseconds=2)
    persist_time = event_time
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version="1.0.0",
        session_id="20260805-NIFTY-LIVE-001",
        run_id="run-001",
        cycle_id=f"cycle-{second}",
        trace_id="trace-001",
        event_time=event_time,
        source_time=source_time,
        receive_time=receive_time,
        available_time=source_time,
        parse_time=parse_time,
        persist_time=persist_time,
        source_provider="TEST",
        source_component="fixture",
        authority_class="SOURCE_OBSERVED",
        data_quality_state=quality,
        instrument_key="NSE_INDEX|Nifty 50",
        strategy_id="fixture_strategy" if candidate_id else "",
        strategy_version="1.0.0" if candidate_id else "",
        candidate_id=candidate_id,
        producer_sequence=sequence,
        payload=payload or {},
    )


def complete_session() -> list[CanonicalEvent]:
    return [
        event("e-1", "SESSION_STARTED", second=0, sequence=1),
        event("e-2", "FEED_TRUTH_UPDATED", second=1, sequence=2, payload={"state": "FRESH"}),
        event("e-3", "STRATEGY_EVALUATED", second=2, sequence=3, candidate_id="c-1"),
        event("e-4", "SIGNAL_GENERATED", second=3, sequence=4, candidate_id="c-1"),
        event("e-5", "CANDIDATE_CREATED", second=4, sequence=5, candidate_id="c-1"),
        event("e-6", "CANDIDATE_RANKED", second=5, sequence=6, candidate_id="c-1"),
        event("e-7", "APPROVAL_REQUESTED", second=6, sequence=7, candidate_id="c-1"),
        event("e-8", "APPROVAL_DECIDED", second=7, sequence=8, candidate_id="c-1", payload={"decision": "REJECT"}),
        event("e-9", "OUTCOME_LABEL", second=30, sequence=9, candidate_id="c-1", payload={"horizon": "30s"}),
        event("e-10", "SESSION_ENDED", second=31, sequence=10),
    ]


def test_event_rejects_future_available_time():
    event_time = BASE
    with pytest.raises(EventValidationError, match="available_after_decision_time"):
        CanonicalEvent(
            event_id="bad",
            event_type="STRATEGY_EVALUATED",
            schema_version="1.0.0",
            session_id="s",
            run_id="r",
            event_time=event_time,
            receive_time=event_time,
            available_time=event_time + timedelta(seconds=1),
            parse_time=event_time,
            persist_time=event_time,
            source_provider="TEST",
            source_component="fixture",
            authority_class="SOURCE_OBSERVED",
            data_quality_state="VALID",
            payload={},
        )


def test_file_publisher_is_idempotent(tmp_path):
    publisher = FileEventPublisher(tmp_path, fsync=False)
    first = complete_session()[0]
    assert publisher.publish(first) is True
    assert publisher.publish(first) is False
    event_log = tmp_path / first.session_id / "events.jsonl"
    assert event_log.read_text(encoding="utf-8").count("\n") == 1


def test_payload_hash_detects_tampering(tmp_path):
    publisher = FileEventPublisher(tmp_path, fsync=False)
    first = complete_session()[0]
    publisher.publish(first)
    event_log = tmp_path / first.session_id / "events.jsonl"
    record = json.loads(event_log.read_text(encoding="utf-8"))
    record["payload"]["tampered"] = True
    event_log.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(EventLogError, match="invalid_event_at_line"):
        list(iter_events(event_log))


def test_complete_session_is_deterministic_and_diagnosable(tmp_path):
    publisher = FileEventPublisher(tmp_path, fsync=False)
    for item in complete_session():
        assert publisher.publish(item) is True
    event_log = tmp_path / "20260805-NIFTY-LIVE-001" / "events.jsonl"
    first_events = list(iter_events(event_log))
    second_events = list(iter_events(event_log))
    first = SessionAnalyzer().analyze(first_events)
    second = SessionAnalyzer().analyze(second_events)
    assert first.analysis_hash == second.analysis_hash
    assert first.manifest["verdict"] == "VALID_OFFLINE_SESSION_EVIDENCE"
    assert first.manifest["producer_sequence_gap_total"] == 0
    assert first.candidate_funnel["complete_candidate_to_outcome_count"] == 1
    assert first.outcome_readiness["ready_for_strategy_diagnosis"] is True
    assert first.outcome_readiness["ready_for_profitability_claim"] is False
    artifacts = write_analysis_bundle(first, tmp_path / "report")
    assert (tmp_path / "report" / "session_analysis.json").exists()
    assert (tmp_path / "report" / "session_report.md").exists()
    assert artifacts["analysis_hash"] == first.analysis_hash


def test_missing_session_end_fails_closed():
    analysis = SessionAnalyzer().analyze(complete_session()[:-1])
    assert analysis.manifest["valid"] is False
    assert analysis.manifest["verdict"] == "INCOMPLETE_SESSION"
    assert analysis.outcome_readiness["ready_for_strategy_diagnosis"] is False


def test_invalid_quality_event_fails_closed():
    rows = complete_session()
    rows[1] = event(
        "e-2",
        "FEED_TRUTH_UPDATED",
        second=1,
        sequence=2,
        payload={"state": "STALE"},
        quality="STALE",
    )
    analysis = SessionAnalyzer().analyze(rows)
    assert analysis.manifest["valid"] is False
    assert analysis.manifest["verdict"] == "INVALID_DATA_QUALITY"


def test_sequence_gap_is_detected():
    rows = complete_session()
    rows[4] = event("e-5", "CANDIDATE_CREATED", second=4, sequence=6, candidate_id="c-1")
    for index in range(5, len(rows)):
        original = rows[index]
        rows[index] = event(
            original.event_id,
            original.event_type,
            second=int((original.event_time - BASE).total_seconds()),
            sequence=(original.producer_sequence or 0) + 1,
            candidate_id=original.candidate_id,
            payload=dict(original.payload),
        )
    analysis = SessionAnalyzer().analyze(rows)
    assert analysis.manifest["producer_sequence_gap_total"] == 1
    assert analysis.manifest["verdict"] == "INVALID_SEQUENCE_COVERAGE"


def test_verify_event_log_requires_one_nonempty_session(tmp_path):
    publisher = FileEventPublisher(tmp_path, fsync=False)
    for item in complete_session():
        publisher.publish(item)
    event_log = tmp_path / "20260805-NIFTY-LIVE-001" / "events.jsonl"
    verification = verify_event_log(event_log)
    assert verification["valid"] is True
    assert verification["event_count"] == 10
