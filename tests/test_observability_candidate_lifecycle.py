from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from core.observability import (
    CandidateLifecycleEventEmitter,
    CandidateLifecycleEventError,
    ObservabilityContext,
    ObservabilityIds,
    ObservabilityJsonLogger,
    validate_event_payload,
)


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 7, 20, 4, tzinfo=timezone.utc)


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_05",
            cycle_id="cycle_obs_05_000001",
            trace_id="trace_obs_05",
        ),
        stage="runtime.cycle",
        execution_mode="PAPER",
        attributes={"strategy_id": "opening_drive", "symbol": "NIFTY"},
    )


def _emitter() -> CandidateLifecycleEventEmitter:
    return CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_obs_05")


def test_candidate_generated_event_has_candidate_identity_and_safety_fields() -> None:
    payload = _emitter().generated(
        timestamp=_timestamp(),
        option_type="CE",
        strike=22500,
    ).as_dict()

    assert payload["event"] == "candidate.generated"
    assert payload["stage"] == "candidate.generated"
    assert payload["decision"] == "generated"
    assert payload["run_id"] == "run_obs_05"
    assert payload["cycle_id"] == "cycle_obs_05_000001"
    assert payload["trace_id"] == "trace_obs_05"
    assert payload["span_id"].startswith("span_candidate.generated_")
    assert payload["candidate_id"] == "candidate_obs_05"
    assert payload["execution_mode"] == "PAPER"
    assert payload["strategy_id"] == "opening_drive"
    assert payload["symbol"] == "NIFTY"
    assert payload["option_type"] == "CE"
    assert payload["strike"] == 22500
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["source"] == "tradebot.observability.candidate_lifecycle"
    validate_event_payload(payload)


def test_candidate_progression_events_are_valid_non_action_payloads() -> None:
    emitter = _emitter()
    events = [
        emitter.normalized(timestamp=_timestamp(), normalized=True),
        emitter.scored(timestamp=_timestamp(), opportunity_score=0.72),
        emitter.ranked(timestamp=_timestamp(), rank=1),
        emitter.displayed(timestamp=_timestamp(), displayable=True),
        emitter.paper_ready(timestamp=_timestamp(), paper_ready=True),
        emitter.paper_submitted(timestamp=_timestamp(), paper_order_id="paper_1"),
    ]

    payloads = [event.as_dict() for event in events]

    assert [payload["event"] for payload in payloads] == [
        "candidate.normalized",
        "candidate.scored",
        "candidate.ranked",
        "candidate.displayed",
        "candidate.paper_ready",
        "candidate.paper_submitted",
    ]
    for payload in payloads:
        assert payload["candidate_id"] == "candidate_obs_05"
        assert payload["is_order_action"] is False
        assert payload["broker_api_called"] is False
        validate_event_payload(payload)


def test_blocked_downgraded_and_ignored_require_reason() -> None:
    emitter = _emitter()

    with pytest.raises(CandidateLifecycleEventError, match="blocked_requires_reason"):
        emitter.blocked(timestamp=_timestamp(), reason="")
    with pytest.raises(CandidateLifecycleEventError, match="downgraded_requires_reason"):
        emitter.downgraded(timestamp=_timestamp(), reason="  ")
    with pytest.raises(CandidateLifecycleEventError, match="ignored_requires_reason"):
        emitter.ignored_with_reason(timestamp=_timestamp(), reason="")


def test_blocked_event_serializes_reason_and_fallback_state() -> None:
    payload = _emitter().blocked(
        timestamp=_timestamp(),
        reason="FALLBACK_NOT_EXECUTABLE",
        fallback_state="recovered_fallback",
        displayable=True,
        executable=False,
    ).as_dict()

    assert payload["event"] == "candidate.blocked"
    assert payload["decision"] == "blocked"
    assert payload["reason"] == "FALLBACK_NOT_EXECUTABLE"
    assert payload["fallback_state"] == "recovered_fallback"
    assert payload["displayable"] is True
    assert payload["executable"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    validate_event_payload(payload)


def test_downgraded_and_ignored_events_serialize_reasons() -> None:
    emitter = _emitter()

    downgraded = emitter.downgraded(
        timestamp=_timestamp(),
        reason="LOW_SCORE_GAP",
        previous_rank=1,
        new_rank=4,
    ).as_dict()
    ignored = emitter.ignored_with_reason(
        timestamp=_timestamp(),
        reason="DUPLICATE_CANDIDATE",
    ).as_dict()

    assert downgraded["event"] == "candidate.downgraded"
    assert downgraded["reason"] == "LOW_SCORE_GAP"
    assert downgraded["previous_rank"] == 1
    assert downgraded["new_rank"] == 4
    assert ignored["event"] == "candidate.ignored"
    assert ignored["decision"] == "ignored"
    assert ignored["reason"] == "DUPLICATE_CANDIDATE"
    validate_event_payload(downgraded)
    validate_event_payload(ignored)


def test_candidate_id_is_required() -> None:
    with pytest.raises(CandidateLifecycleEventError, match="candidate_id_required"):
        CandidateLifecycleEventEmitter(_context(), candidate_id="")


def test_write_event_uses_json_logger_without_business_side_effects() -> None:
    stream = StringIO()
    logger = ObservabilityJsonLogger(stream)
    emitter = _emitter()

    payload = emitter.write_event(
        logger,
        emitter.generated(timestamp=_timestamp(), symbol="BANKNIFTY"),
    )

    written = json.loads(stream.getvalue())
    assert payload["event"] == "candidate.generated"
    assert written["event"] == "candidate.generated"
    assert written["candidate_id"] == "candidate_obs_05"
    assert written["symbol"] == "BANKNIFTY"
    assert written["is_order_action"] is False
    assert written["broker_api_called"] is False
    assert stream.getvalue().count("\n") == 1
