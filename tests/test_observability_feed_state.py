from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from core.observability import (
    FeedStateEventEmitter,
    FeedStateEventError,
    ObservabilityContext,
    ObservabilityIds,
    ObservabilityJsonLogger,
    validate_event_payload,
)


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 8, 10, 6, tzinfo=timezone.utc)


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_06",
            cycle_id="cycle_obs_06_000001",
            trace_id="trace_obs_06",
        ),
        stage="runtime.cycle",
        execution_mode="PAPER",
        attributes={"strategy_id": "opening_drive", "symbol": "NIFTY"},
    )


def _emitter() -> FeedStateEventEmitter:
    return FeedStateEventEmitter(_context())


def test_feed_fresh_event_is_valid_non_action_payload() -> None:
    payload = _emitter().feed_fresh(timestamp=_timestamp(), feed_age_ms=250).as_dict()

    assert payload["event"] == "feed.fresh"
    assert payload["stage"] == "feed.freshness_check"
    assert payload["decision"] == "fresh"
    assert payload["feed_age_ms"] == 250
    assert payload["feed_state"] == "fresh"
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    validate_event_payload(payload)


def test_feed_stale_event_is_blocked_with_reason() -> None:
    payload = _emitter().feed_stale(timestamp=_timestamp(), feed_age_ms=5000).as_dict()

    assert payload["event"] == "feed.stale"
    assert payload["decision"] == "blocked"
    assert payload["reason"] == "STALE_FEED"
    assert payload["feed_state"] == "stale"
    assert payload["feed_age_ms"] == 5000
    validate_event_payload(payload)


def test_quote_source_events_are_valid_and_non_action() -> None:
    emitter = _emitter()
    real = emitter.quote_real(timestamp=_timestamp(), candidate_id="candidate_obs_06").as_dict()
    missing = emitter.quote_missing(timestamp=_timestamp(), candidate_id="candidate_obs_06").as_dict()
    fallback = emitter.quote_fallback_used(timestamp=_timestamp(), candidate_id="candidate_obs_06").as_dict()

    assert real["event"] == "quote.real"
    assert real["quote_source"] == "real"
    assert missing["event"] == "quote.missing"
    assert missing["reason"] == "QUOTE_MISSING"
    assert fallback["event"] == "quote.fallback_used"
    assert fallback["quote_source"] == "fallback"
    assert fallback["fallback_state"] == "recovered_fallback"
    assert fallback["displayable"] is True
    assert fallback["executable"] is False
    for payload in (real, missing, fallback):
        assert payload["candidate_id"] == "candidate_obs_06"
        assert payload["is_order_action"] is False
        assert payload["broker_api_called"] is False
        validate_event_payload(payload)


def test_blocked_feed_state_events_preserve_candidate_id_and_reason() -> None:
    emitter = _emitter()

    fallback = emitter.blocked_fallback(timestamp=_timestamp(), candidate_id="candidate_obs_06").as_dict()
    stale = emitter.blocked_stale_feed(
        timestamp=_timestamp(),
        candidate_id="candidate_obs_06",
        feed_age_ms=6000,
    ).as_dict()

    assert fallback["event"] == "execution.blocked_fallback"
    assert fallback["reason"] == "FALLBACK_NOT_EXECUTABLE"
    assert fallback["candidate_id"] == "candidate_obs_06"
    assert fallback["executable"] is False
    assert stale["event"] == "execution.blocked_stale_feed"
    assert stale["reason"] == "STALE_FEED_NOT_EXECUTABLE"
    assert stale["candidate_id"] == "candidate_obs_06"
    assert stale["feed_state"] == "stale"
    assert stale["executable"] is False
    validate_event_payload(fallback)
    validate_event_payload(stale)


def test_unsafe_feed_state_flags_are_rejected() -> None:
    with pytest.raises(FeedStateEventError, match="fallback_state_cannot_be_executable"):
        _emitter().validate_state(fallback_state="recovered_fallback", decision="executable")
    with pytest.raises(FeedStateEventError, match="fallback_state_cannot_be_executable"):
        _emitter().quote_fallback_used(timestamp=_timestamp(), candidate_id="candidate_obs_06", executable=True)
    with pytest.raises(FeedStateEventError, match="stale_feed_cannot_be_executable"):
        _emitter().validate_state(feed_state="stale", executable=True)


def test_blocked_events_require_reason() -> None:
    with pytest.raises(FeedStateEventError, match="blocked_event_requires_reason"):
        _emitter().feed_stale(timestamp=_timestamp(), feed_age_ms=7000, reason="")
    with pytest.raises(FeedStateEventError, match="blocked_event_requires_reason"):
        _emitter().quote_missing(timestamp=_timestamp(), reason="")


def test_write_event_uses_json_logger_without_side_effects() -> None:
    stream = StringIO()
    logger = ObservabilityJsonLogger(stream)
    emitter = _emitter()

    payload = emitter.write_event(logger, emitter.feed_fresh(timestamp=_timestamp(), feed_age_ms=120))

    written = json.loads(stream.getvalue())
    assert payload["event"] == "feed.fresh"
    assert written["event"] == "feed.fresh"
    assert written["feed_age_ms"] == 120
    assert written["is_order_action"] is False
    assert written["broker_api_called"] is False
    assert stream.getvalue().count("\n") == 1
