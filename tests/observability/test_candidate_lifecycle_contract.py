from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.observability import (
    CandidateLifecycleEventEmitter,
    CandidateLifecycleEventError,
    ObservabilityContext,
    ObservabilityIds,
    validate_event_payload,
)


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_13_lifecycle",
            cycle_id="cycle_obs_13_lifecycle_000001",
            trace_id="trace_obs_13_lifecycle",
            span_id="span_obs_13_lifecycle",
        ),
        stage="runtime.cycle",
        execution_mode="paper",
    )


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 7, 46, tzinfo=timezone.utc)


def test_candidate_lifecycle_events_include_required_identity_and_safety_fields() -> None:
    emitter = CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_obs_13_lifecycle")

    events = [
        emitter.generated(timestamp=_timestamp()).as_dict(),
        emitter.normalized(timestamp=_timestamp()).as_dict(),
        emitter.scored(timestamp=_timestamp(), score=0.91).as_dict(),
        emitter.ranked(timestamp=_timestamp(), rank=1).as_dict(),
        emitter.displayed(timestamp=_timestamp()).as_dict(),
        emitter.paper_ready(timestamp=_timestamp()).as_dict(),
        emitter.paper_submitted(timestamp=_timestamp()).as_dict(),
        emitter.blocked(timestamp=_timestamp(), reason="NO_TRADE_CHOP").as_dict(),
        emitter.downgraded(timestamp=_timestamp(), reason="LOW_CONFIDENCE").as_dict(),
        emitter.ignored_with_reason(timestamp=_timestamp(), reason="DUPLICATE_CANDIDATE").as_dict(),
    ]

    for event in events:
        validate_event_payload(event)
        assert event["candidate_id"] == "candidate_obs_13_lifecycle"
        assert event["trace_id"] == "trace_obs_13_lifecycle"
        assert event["is_order_action"] is False
        assert event["broker_api_called"] is False
        assert event["execution_mode"] == "paper"


def test_terminal_candidate_lifecycle_events_require_reason() -> None:
    emitter = CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_obs_13_lifecycle")

    with pytest.raises(CandidateLifecycleEventError, match="blocked_requires_reason"):
        emitter.blocked(timestamp=_timestamp(), reason="")

    with pytest.raises(CandidateLifecycleEventError, match="downgraded_requires_reason"):
        emitter.downgraded(timestamp=_timestamp(), reason="")

    with pytest.raises(CandidateLifecycleEventError, match="ignored_requires_reason"):
        emitter.ignored_with_reason(timestamp=_timestamp(), reason="")


def test_candidate_lifecycle_emitter_rejects_empty_candidate_id() -> None:
    with pytest.raises(CandidateLifecycleEventError, match="candidate_id_required"):
        CandidateLifecycleEventEmitter(_context(), candidate_id="")
