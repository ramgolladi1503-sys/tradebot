from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.session import SessionAnalyzer


BASE = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)


def _event(event_id: str, event_type: str, second: int, sequence: int, quality: str = "VALID") -> CanonicalEvent:
    event_time = BASE + timedelta(seconds=second)
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version="1.0.0",
        session_id="partial-session",
        run_id="run-1",
        event_time=event_time,
        source_time=event_time - timedelta(milliseconds=3),
        receive_time=event_time - timedelta(milliseconds=2),
        available_time=event_time - timedelta(milliseconds=3),
        parse_time=event_time - timedelta(milliseconds=1),
        persist_time=event_time,
        source_provider="TEST",
        source_component="fixture",
        authority_class="SOURCE_OBSERVED",
        data_quality_state=quality,
        producer_sequence=sequence,
        payload={},
    )


def test_partial_quality_fails_closed() -> None:
    rows = [
        _event("start", "SESSION_STARTED", 0, 1),
        _event("partial", "MARKET_SNAPSHOT", 1, 2, "PARTIAL"),
        _event("end", "SESSION_ENDED", 2, 3),
    ]
    analysis = SessionAnalyzer().analyze(rows)
    assert analysis.manifest["valid"] is False
    assert analysis.manifest["verdict"] == "PARTIAL_DATA_QUALITY"
    assert analysis.manifest["partial_quality_event_count"] == 1
    assert analysis.outcome_readiness["ready_for_strategy_diagnosis"] is False
