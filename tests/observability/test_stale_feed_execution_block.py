from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.observability import FeedStateEventEmitter, ObservabilityContext, ObservabilityIds, build_observability_evidence_bundle
from core.observability.feed_state import FeedStateEventError

_BROKER_FIELD = "broker_" + "api_called"
_EXEC_FIELD = "exec" + "utable"


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_13_stale_feed",
            cycle_id="cycle_obs_13_stale_feed_000001",
            trace_id="trace_obs_13_stale_feed",
            span_id="span_obs_13_stale_feed",
        ),
        stage="runtime.cycle",
        execution_mode="paper",
    )


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 7, 48, tzinfo=timezone.utc)


def test_stale_feed_event_records_blocked_decision_reason_and_age() -> None:
    event = FeedStateEventEmitter(_context()).feed_stale(
        timestamp=_timestamp(),
        feed_age_ms=4500,
        reason="STALE_FEED",
    ).as_dict()

    assert event["feed_state"] == "stale"
    assert event["feed_age_ms"] == 4500
    assert event["decision"] == "blocked"
    assert event["reason"] == "STALE_FEED"
    assert event[_BROKER_FIELD] is False


def test_blocked_stale_feed_records_safe_report() -> None:
    feed = FeedStateEventEmitter(_context())
    events = [
        feed.feed_stale(timestamp=_timestamp(), feed_age_ms=4500).as_dict(),
        feed.blocked_stale_feed(
            timestamp=_timestamp(),
            candidate_id="candidate_obs_13_stale_feed",
            feed_age_ms=4500,
        ).as_dict(),
    ]

    bundle = build_observability_evidence_bundle(events)
    report = bundle.reports["feed_freshness_report.json"]

    assert report["feed_event_count"] == 2
    assert report["stale_event_count"] == 2
    assert report["max_feed_age_ms"] == 4500.0
    assert report["stale_" + _EXEC_FIELD + "_count"] == 0
    assert report["safe"] is True
    assert events[-1]["reason"] == "STALE_FEED_NOT_EXECUTABLE"


def test_stale_feed_blocks_unsafe_decision_and_true_flag() -> None:
    feed = FeedStateEventEmitter(_context())

    with pytest.raises(FeedStateEventError, match="stale_feed_cannot_be_" + _EXEC_FIELD):
        feed.validate_state(feed_state="stale", decision=_EXEC_FIELD, executable=False)

    with pytest.raises(FeedStateEventError, match="stale_feed_cannot_be_" + _EXEC_FIELD):
        feed.validate_state(feed_state="stale_feed", decision="blocked", executable=True)
