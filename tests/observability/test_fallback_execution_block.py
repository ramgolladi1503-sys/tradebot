from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.observability import FeedStateEventEmitter, ObservabilityContext, ObservabilityIds, build_observability_evidence_bundle
from core.observability.feed_state import FeedStateEventError


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_13_fallback",
            cycle_id="cycle_obs_13_fallback_000001",
            trace_id="trace_obs_13_fallback",
            span_id="span_obs_13_fallback",
        ),
        stage="runtime.cycle",
        execution_mode="paper",
    )


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 7, 47, tzinfo=timezone.utc)


def test_fallback_quote_is_displayable_but_not_executable() -> None:
    event = FeedStateEventEmitter(_context()).quote_fallback_used(
        timestamp=_timestamp(),
        candidate_id="candidate_obs_13_fallback",
    ).as_dict()

    assert event["fallback_state"] == "recovered_fallback"
    assert event["displayable"] is True
    assert event["executable"] is False
    assert event["broker_api_called"] is False


def test_blocked_fallback_records_terminal_reason_and_safe_report() -> None:
    feed = FeedStateEventEmitter(_context())
    events = [
        feed.quote_fallback_used(timestamp=_timestamp(), candidate_id="candidate_obs_13_fallback").as_dict(),
        feed.blocked_fallback(timestamp=_timestamp(), candidate_id="candidate_obs_13_fallback").as_dict(),
    ]

    bundle = build_observability_evidence_bundle(events)
    report = bundle.reports["fallback_safety_report.json"]

    assert report["fallback_event_count"] == 2
    assert report["fallback_candidate_count"] == 1
    assert report["fallback_executable_count"] == 0
    assert report["safe"] is True
    assert events[-1]["decision"] == "blocked"
    assert events[-1]["reason"] == "FALLBACK_NOT_EXECUTABLE"


def test_fallback_state_blocks_executable_decision_and_true_executable_flag() -> None:
    feed = FeedStateEventEmitter(_context())

    with pytest.raises(FeedStateEventError, match="fallback_state_cannot_be_executable"):
        feed.validate_state(fallback_state="recovered_fallback", decision="executable", executable=False)

    with pytest.raises(FeedStateEventError, match="fallback_state_cannot_be_executable"):
        feed.validate_state(fallback_state="fallback_recovered", decision="blocked", executable=True)
